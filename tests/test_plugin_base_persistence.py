"""回归测试：PluginBase 持久化原子性、卸载清理幂等性、PluginManager 生命周期任务追踪

覆盖以下已确认缺陷：
  1. save_config / safe_save_data 失败时截断目标文件，旧数据被破坏（静默数据丢失）
  2. 子类 on_unload 抛异常时 EventBus 订阅泄漏（重复回复）
  3. 旧版 PluginManager 的 on_load / on_unload 以游离任务执行：加载可在注销后完成、
     加载失败的任务异常无人取回且插件残留在注册表
  4. PluginBase.sync_run 调用不存在的 self.run_in_executor
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from unittest.mock import MagicMock

import pytest

from sdk.core.event_bus import EventBus
from sdk.pluginsystem.plugin_base import PluginBase, PluginManager


class _PlainPlugin(PluginBase):
    """最简插件，不重写任何生命周期方法"""


def _handler_count(bus: EventBus) -> int:
    return sum(len(handlers) for handlers in bus._handlers.values())


# ==================== 缺陷 1：持久化写入必须原子 ====================


async def test_save_config_failure_keeps_previous_content(tmp_path) -> None:
    """序列化失败时磁盘上必须仍是上一次的完整内容"""
    plugin = _PlainPlugin()
    plugin._plugin_dir = tmp_path
    assert await plugin.save_config({"good": 1}) is True
    before = (tmp_path / "config.json").read_text(encoding="utf-8")

    assert await plugin.save_config({"good": 1, "bad": object()}) is False

    assert (tmp_path / "config.json").read_text(encoding="utf-8") == before
    assert json.loads(before) == {"good": 1}


async def test_failed_save_does_not_poison_load_config(tmp_path) -> None:
    """保存失败后 load_config 仍必须读到旧配置，而不是回退为空字典"""
    plugin = _PlainPlugin()
    plugin._plugin_dir = tmp_path
    (tmp_path / "config.json").write_text(json.dumps({"keep": True}), encoding="utf-8")

    assert await plugin.save_config({"bad": object()}) is False

    assert await plugin.load_config() == {"keep": True}


async def test_safe_save_data_failure_keeps_previous_content(tmp_path) -> None:
    """safe_save_data 序列化失败时同样不能破坏旧数据"""
    plugin = _PlainPlugin()
    plugin._plugin_dir = tmp_path
    assert await plugin.safe_save_data({"a": 1}, "data.json") is True
    before = (tmp_path / "data.json").read_text(encoding="utf-8")

    assert await plugin.safe_save_data({"a": 1, "b": object()}, "data.json") is False

    assert (tmp_path / "data.json").read_text(encoding="utf-8") == before
    assert await plugin.safe_load_data("data.json", {"default": True}) == {"a": 1}


async def test_failed_save_leaves_no_temp_files(tmp_path) -> None:
    """失败的写入不能留下临时文件"""
    plugin = _PlainPlugin()
    plugin._plugin_dir = tmp_path
    assert await plugin.save_config({"ok": 1}) is True

    assert await plugin.save_config({"bad": object()}) is False

    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json"]


async def test_atomic_write_keeps_old_content_when_replace_fails(tmp_path, monkeypatch) -> None:
    """原子替换失败时必须保留完整旧内容，且清理临时文件"""
    plugin = _PlainPlugin()
    plugin._plugin_dir = tmp_path
    assert await plugin.save_config({"good": 1}) is True

    def boom(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)

    assert await plugin.save_config({"good": 2}) is False
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {"good": 1}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json"]


# ==================== 缺陷 2：on_unload 抛异常也必须清理订阅 ====================


class _RaisingUnloadPlugin(PluginBase):
    async def on_unload(self) -> None:
        raise RuntimeError("unload boom")


class _SuperThenRaisePlugin(PluginBase):
    async def on_unload(self) -> None:
        await super().on_unload()
        raise RuntimeError("late boom")


async def test_raising_on_unload_still_releases_subscriptions() -> None:
    """子类 on_unload 抛异常时，实例的 EventBus 订阅仍必须被清除"""
    plugin = _RaisingUnloadPlugin()
    bus = EventBus()
    await PluginBase.on_load(plugin, None, bus)
    assert _handler_count(bus) == 4

    with pytest.raises(RuntimeError, match="unload boom"):
        await plugin.on_unload()

    assert _handler_count(bus) == 0


async def test_super_then_raise_releases_subscriptions_once() -> None:
    """先调用 super().on_unload() 再抛异常时，清理仍必须完整且幂等"""
    plugin = _SuperThenRaisePlugin()
    bus = EventBus()
    await PluginBase.on_load(plugin, None, bus)

    with pytest.raises(RuntimeError, match="late boom"):
        await plugin.on_unload()

    assert _handler_count(bus) == 0


async def test_unload_cleanup_is_idempotent() -> None:
    """重复卸载不得报错，也不得残留订阅"""
    plugin = _PlainPlugin()
    bus = EventBus()
    await PluginBase.on_load(plugin, None, bus)

    await plugin.on_unload()
    await plugin.on_unload()

    assert _handler_count(bus) == 0


async def test_reload_after_unload_resubscribes_cleanly() -> None:
    """卸载后再次加载必须重新订阅，且卸载仍能清空"""
    plugin = _RaisingUnloadPlugin()
    bus = EventBus()
    await PluginBase.on_load(plugin, None, bus)
    with pytest.raises(RuntimeError):
        await plugin.on_unload()
    assert _handler_count(bus) == 0

    await PluginBase.on_load(plugin, None, bus)
    assert _handler_count(bus) == 4


# ==================== 缺陷 3：PluginManager 生命周期任务必须被追踪 ====================


async def test_unregister_cancels_in_flight_load() -> None:
    """注销必须能取消仍在进行中的加载，加载不得在注销完成后重新订阅"""
    bus = EventBus()
    manager = PluginManager(MagicMock(), bus)
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowLoadPlugin(PluginBase):
        async def on_load(self, api, event_bus, plugin_dir=None):
            started.set()
            await release.wait()
            await super().on_load(api, event_bus, plugin_dir)

    plugin = _SlowLoadPlugin()
    assert manager.register_plugin(plugin) is True
    await started.wait()
    assert _handler_count(bus) == 0

    assert manager.unregister_plugin(plugin.name) is True

    release.set()
    await asyncio.sleep(0.05)

    assert _handler_count(bus) == 0
    assert plugin.name.lower() not in manager.plugins


async def test_failing_on_load_is_retrieved_and_unregistered() -> None:
    """on_load 抛异常的任务异常必须被取回，插件不得残留在注册表"""
    bus = EventBus()
    manager = PluginManager(MagicMock(), bus)

    class _BrokenLoadPlugin(PluginBase):
        async def on_load(self, *args):
            raise ValueError("load boom")

    assert manager.register_plugin(_BrokenLoadPlugin()) is True

    await asyncio.sleep(0.05)

    assert "brokenloadplugin" not in manager.plugins
    # 名字已释放：同名插件必须能够重新注册
    assert manager.register_plugin(_BrokenLoadPlugin()) is True


async def test_partially_loaded_plugin_releases_subscriptions_on_failure() -> None:
    """on_load 订阅后抛异常时，已注册的订阅必须被清理"""
    bus = EventBus()
    manager = PluginManager(MagicMock(), bus)

    class _HalfLoadPlugin(PluginBase):
        async def on_load(self, api, event_bus, plugin_dir=None):
            await super().on_load(api, event_bus, plugin_dir)
            raise RuntimeError("late load boom")

    assert manager.register_plugin(_HalfLoadPlugin()) is True

    await asyncio.sleep(0.05)

    assert _handler_count(bus) == 0
    assert "halfloadplugin" not in manager.plugins


def test_register_unregister_without_running_loop_keeps_sync_contract() -> None:
    """无事件循环时 register/unregister 不得抛异常，仍然同步返回并登记插件"""
    manager = PluginManager(MagicMock(), EventBus())
    plugin = _PlainPlugin()

    assert manager.register_plugin(plugin) is True
    assert plugin.name.lower() in manager.plugins
    assert manager.unregister_plugin(plugin.name) is True
    assert plugin.name.lower() not in manager.plugins


# ==================== 缺陷 4：sync_run 必须真正可用 ====================


async def test_sync_run_executes_function_in_executor() -> None:
    """sync_run 包装的同步函数必须能执行，并运行在插件线程池中"""
    plugin = _PlainPlugin()
    caller_thread = threading.get_ident()

    def work(a: int, b: int) -> tuple[int, int]:
        return a + b, threading.get_ident()

    wrapped = plugin.sync_run(work)
    result, worker_thread = await wrapped(2, 3)

    assert result == 5
    assert worker_thread != caller_thread
    await plugin.on_unload()
