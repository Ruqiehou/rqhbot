"""回归测试：HotReloadPluginManager 的并发生命周期、在途加载与配置回退

覆盖四类已确认缺陷：
  1. 并发 reload/load 会对同一插件重复注册（事件订阅翻倍 -> 机器人重复回复）
  2. 在途 load 对 unload_all_plugins 不可见，关机后插件才注册自己
  3. 并发 unload 抛 KeyError 打断关机；unload 被取消时跳过登记清理
  4. 仅有 config.json 的插件清单被忽略（enabled:false 无效、priority/依赖被丢弃）

事件总线订阅数是可观察的公共副作用：PluginBase.on_load 每次订阅 4 个事件。
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from unittest.mock import MagicMock

import pytest

from sdk.core.event_bus import EventBus
from sdk.pluginsystem.plugin_manager import HotReloadPluginManager


# ==================== 工具 ====================


def _handler_count(bus: EventBus) -> int:
    return sum(len(handlers) for handlers in bus._handlers.values())


def _live_instances(bus: EventBus) -> set[int]:
    """事件总线上仍然订阅着的插件实例（用 id 区分不同实例）"""
    instances: set[int] = set()
    for handlers in bus._handlers.values():
        for handler in handlers:
            instances.add(id(getattr(handler, "__self__", handler)))
    return instances


def _install_hooks(name: str, **attrs: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _write_plugin(root, plugin_name: str, source: str):
    plugin_dir = root / plugin_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "main.py").write_text(source, encoding="utf-8")
    return plugin_dir


_PLAIN_PLUGIN = """
from sdk.pluginsystem import PluginBase


class PlainPlugin(PluginBase):
    pass
"""

_GATED_LOAD_PLUGIN = """
import asyncio
import {hooks} as hooks

from sdk.pluginsystem import PluginBase


class GatedLoadPlugin(PluginBase):
    async def on_load(self, api, event_bus, plugin_dir=None):
        await super().on_load(api, event_bus, plugin_dir)
        hooks.arrived += 1
        two_arrived = getattr(hooks, "two_arrived", None)
        if two_arrived is not None and hooks.arrived >= 2:
            two_arrived.set()
        if hooks.gate is not None:
            await hooks.gate.wait()
"""

_GATED_UNLOAD_PLUGIN = """
import asyncio
import {hooks} as hooks

from sdk.pluginsystem import PluginBase


class GatedUnloadPlugin(PluginBase):
    async def on_unload(self):
        # 先退订事件总线，再在取消点等待，方便观察取消后的清理
        await super().on_unload()
        hooks.unload_started += 1
        hooks.started_event.set()
        if hooks.gate is not None:
            await hooks.gate.wait()
        hooks.unload_done += 1
"""

_POISON_UNLOAD_PLUGIN = """
import asyncio

from sdk.pluginsystem import PluginBase


class PoisonUnloadPlugin(PluginBase):
    async def on_unload(self):
        raise asyncio.CancelledError()
"""


# ==================== DEFECT 1：并发 reload/load 重复注册 ====================


async def test_concurrent_reload_registers_single_instance(tmp_path) -> None:
    """两个并发的 reload_plugin 不能让同一插件留下两个存活实例"""
    hooks = _install_hooks(
        "_pm_hooks_raceplug",
        gate=None,
        arrived=0,
        two_arrived=None,
    )
    _write_plugin(
        tmp_path,
        "raceplug",
        _GATED_LOAD_PLUGIN.replace("{hooks}", "_pm_hooks_raceplug"),
    )
    manager = HotReloadPluginManager(tmp_path)
    bus = EventBus()
    api = MagicMock()

    assert await manager.load_plugin("raceplug", api, bus) is True
    assert _handler_count(bus) == 4

    gate = asyncio.Event()
    two_arrived = asyncio.Event()
    # 先清空首次加载的计数，再让后续所有 on_load 卡在 gate 上
    hooks.arrived = 0
    hooks.gate = gate
    hooks.two_arrived = two_arrived

    first = asyncio.create_task(manager.reload_plugin("raceplug", api, bus))
    second = asyncio.create_task(manager.reload_plugin("raceplug", api, bus))

    # 未修复时两次 on_load 会同时进入；已修复时同一插件的生命周期被串行化，
    # 因此这里只等待一个有限的超时，随后统一放行。
    try:
        await asyncio.wait_for(two_arrived.wait(), timeout=1.0)
    except asyncio.TimeoutError:
        pass

    gate.set()
    results = await asyncio.gather(first, second)

    assert results == [True, True]
    assert _handler_count(bus) == 4, "并发 reload 后事件订阅应仍为 4 条（无孤儿实例）"
    assert len(_live_instances(bus)) == 1, "事件总线上只能有一个存活插件实例"
    assert set(manager.plugins) == {"raceplug"}
    assert len(manager.plugins) == 1


# ==================== DEFECT 2：在途 load 对 unload_all 不可见 ====================


async def test_unload_all_cancels_inflight_load(tmp_path) -> None:
    """关机时在途的 load_plugin 必须被取消并清理干净"""
    hooks = _install_hooks("_pm_hooks_slowload", gate=None, arrived=0)
    _write_plugin(
        tmp_path,
        "slowload",
        _GATED_LOAD_PLUGIN.replace("{hooks}", "_pm_hooks_slowload"),
    )
    manager = HotReloadPluginManager(tmp_path)
    bus = EventBus()
    api = MagicMock()

    gate = asyncio.Event()
    hooks.gate = gate

    load_task = asyncio.create_task(manager.load_plugin("slowload", api, bus))
    for _ in range(1000):
        if hooks.arrived >= 1:
            break
        await asyncio.sleep(0.001)
    assert hooks.arrived == 1, "on_load 应已进入并卡在 gate 上"
    assert manager.plugins == {}, "在途加载此时尚未登记进 plugins"

    await manager.unload_all_plugins()

    gate.set()
    cancelled = False
    try:
        await load_task
    except asyncio.CancelledError:
        cancelled = True

    assert manager.plugins == {}, "关机后不应有插件完成注册"
    assert _handler_count(bus) == 0, "被取消的加载不得留下事件订阅"
    assert not manager._loading
    assert cancelled, "在途加载应被取消而不是完成注册"


# ==================== DEFECT 3：并发 unload / 取消 unload ====================


async def test_concurrent_unload_never_raises_keyerror(tmp_path) -> None:
    """两个并发的 unload_plugin 都不能抛 KeyError"""
    hooks = _install_hooks(
        "_pm_hooks_slowunload",
        gate=None,
        unload_started=0,
        unload_done=0,
        started_event=asyncio.Event(),
    )
    _write_plugin(
        tmp_path,
        "slowunload",
        _GATED_UNLOAD_PLUGIN.replace("{hooks}", "_pm_hooks_slowunload"),
    )
    manager = HotReloadPluginManager(tmp_path)
    bus = EventBus()
    api = MagicMock()

    assert await manager.load_plugin("slowunload", api, bus) is True
    assert _handler_count(bus) == 4

    gate = asyncio.Event()
    hooks.gate = gate

    first = asyncio.create_task(manager.unload_plugin("slowunload"))
    second = asyncio.create_task(manager.unload_plugin("slowunload"))
    await asyncio.wait_for(hooks.started_event.wait(), timeout=1.0)
    await asyncio.sleep(0.05)  # 让第二个 unload 也走到登记检查
    gate.set()

    results = await asyncio.gather(first, second, return_exceptions=True)

    errors = [r for r in results if isinstance(r, BaseException)]
    assert errors == [], f"并发卸载不应抛出异常: {errors!r}"
    assert "slowunload" not in manager.plugins
    assert _handler_count(bus) == 0
    assert hooks.unload_started == 1, "on_unload 只能被调用一次"


async def test_cancelled_unload_still_cleans_registry(tmp_path) -> None:
    """unload 被取消时仍必须完成登记清理，且后续 unload 幂等"""
    hooks = _install_hooks(
        "_pm_hooks_cancelunload",
        gate=None,
        unload_started=0,
        unload_done=0,
        started_event=asyncio.Event(),
    )
    _write_plugin(
        tmp_path,
        "cancelunload",
        _GATED_UNLOAD_PLUGIN.replace("{hooks}", "_pm_hooks_cancelunload"),
    )
    manager = HotReloadPluginManager(tmp_path)
    bus = EventBus()
    api = MagicMock()

    assert await manager.load_plugin("cancelunload", api, bus) is True

    gate = asyncio.Event()
    hooks.gate = gate

    task = asyncio.create_task(manager.unload_plugin("cancelunload"))
    await asyncio.wait_for(hooks.started_event.wait(), timeout=1.0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert "cancelunload" not in manager.plugins, "取消后仍须从登记表移除"
    assert _handler_count(bus) == 0
    assert hooks.unload_started == 1

    # 幂等：再次卸载不得重复调用 on_unload
    gate.set()
    await manager.unload_plugin("cancelunload")
    assert hooks.unload_started == 1


async def test_unload_all_continues_after_plugin_failure(tmp_path) -> None:
    """一个插件的 on_unload 出错不能阻止其余插件卸载"""
    _write_plugin(tmp_path, "apoison", _POISON_UNLOAD_PLUGIN)
    _write_plugin(tmp_path, "zhealthy", _PLAIN_PLUGIN)
    manager = HotReloadPluginManager(tmp_path)
    bus = EventBus()
    api = MagicMock()

    assert await manager.load_plugin("apoison", api, bus) is True
    assert await manager.load_plugin("zhealthy", api, bus) is True
    assert _handler_count(bus) == 8

    await manager.unload_all_plugins()

    assert manager.plugins == {}, "卸载中途出错后其余插件也必须被卸载"
    assert _handler_count(bus) == 0


# ==================== DEFECT 4：config.json 清单回退 ====================


def test_plugin_json_wins_over_config_json(tmp_path) -> None:
    """plugin.json 存在时保持原行为，绝不读取 config.json"""
    plugin_dir = _write_plugin(tmp_path, "manifestprio", _PLAIN_PLUGIN)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"enabled": True, "priority": 5, "version": "1.2.3"}),
        encoding="utf-8",
    )
    (plugin_dir / "config.json").write_text(
        json.dumps({"enabled": False, "priority": 99, "version": "9.9.9"}),
        encoding="utf-8",
    )
    manager = HotReloadPluginManager(tmp_path)

    config = manager._load_plugin_config("manifestprio")

    assert config["enabled"] is True
    assert config["priority"] == 5
    assert config["version"] == "1.2.3"


async def test_config_json_manifest_disables_plugin(tmp_path) -> None:
    """只有 config.json 的清单式插件，enabled:false 必须生效"""
    plugin_dir = _write_plugin(tmp_path, "legacyoff", _PLAIN_PLUGIN)
    (plugin_dir / "config.json").write_text(
        json.dumps(
            {
                "name": "legacyoff",
                "version": "2.0.0",
                "description": "legacy manifest",
                "author": "rqh",
                "enabled": False,
                "priority": 7,
            }
        ),
        encoding="utf-8",
    )
    manager = HotReloadPluginManager(tmp_path)
    bus = EventBus()

    assert await manager.load_plugin("legacyoff", MagicMock(), bus) is False
    assert manager.plugins == {}
    assert _handler_count(bus) == 0

    config = manager._load_plugin_config("legacyoff")
    assert config["enabled"] is False
    assert config["priority"] == 7
    assert config["version"] == "2.0.0"


def test_plain_config_json_not_treated_as_manifest(tmp_path) -> None:
    """普通数据型 config.json（如 {"admins": []}）不得被当作插件清单"""
    plugin_dir = _write_plugin(tmp_path, "plainconf", _PLAIN_PLUGIN)
    (plugin_dir / "config.json").write_text(
        json.dumps({"admins": [], "name": "some-data"}),
        encoding="utf-8",
    )
    manager = HotReloadPluginManager(tmp_path)

    config = manager._load_plugin_config("plainconf")

    assert config["enabled"] is True
    assert config["priority"] == 100
    assert "admins" not in config
