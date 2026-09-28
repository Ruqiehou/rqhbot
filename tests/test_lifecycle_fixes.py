"""回归测试：连接关闭状态、断开清理、插件卸载与消息段修正"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock

from plugins.pintu.main import PintuPlugin
from plugins.rqhmain.main import RqhmainPlugin
from plugins.rqhshen.main import RqhshenPlugin
from plugins.rqhwenda import main as wenda
from plugins.rqhwenda.answer_manager import AnswerManager
from sdk.bot_client import BotClient
from sdk.core.client import NapCatClient
from sdk.core.event_bus import EventBus
from sdk.pluginsystem import PluginBase
from sdk.pluginsystem.plugin_manager import HotReloadPluginManager


class _NormallyClosedSocket:
    """模拟 websockets 正常关闭：async for 以 StopAsyncIteration 结束"""

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


async def test_normal_close_marks_client_disconnected() -> None:
    """正常关闭（1000/1001）后必须更新连接状态，否则 run_frontend 永远等待"""
    client = NapCatClient()
    client.ws = _NormallyClosedSocket()
    client.msg_queue = asyncio.Queue()
    client._connected = True

    await client._listen_messages()

    assert client.connected is False


async def test_disconnect_cleans_up_after_connection_lost() -> None:
    """异常断线已将 _connected 置为 False，但残留资源仍必须被清理"""
    client = NapCatClient()
    client._connected = False
    client.ws = AsyncMock()
    client.msg_queue = asyncio.Queue()
    client.echo_map["pending"] = asyncio.get_running_loop().create_future()
    client._processing_task = asyncio.create_task(asyncio.sleep(30))
    client._listen_task = asyncio.create_task(asyncio.sleep(30))

    await client.disconnect()

    assert client.echo_map == {}
    assert client.msg_queue is None
    assert client.ws is None
    assert client._processing_task is None
    assert client._listen_task is None


async def test_run_frontend_unloads_plugins_on_exit() -> None:
    """机器人退出时必须停止文件监控并卸载插件"""
    bot = BotClient()
    bot.client.connect = AsyncMock(return_value=False)
    bot.client.disconnect = AsyncMock()
    bot.hot_reload_manager.unload_all_plugins = AsyncMock()
    bot.stop_file_watcher = MagicMock()

    await bot.run_frontend(load_plugins=False)

    bot.stop_file_watcher.assert_called_once()
    bot.hot_reload_manager.unload_all_plugins.assert_awaited_once()


def test_clean_submodules_keeps_similar_plugin_names() -> None:
    """清理 demo 的模块缓存时不能误删 plugins.demo_extra"""
    saved = {}
    for name in ("plugins.demo", "plugins.demo.helper", "plugins.demo_extra"):
        saved[name] = sys.modules.get(name)
        sys.modules[name] = types.ModuleType(name)
    try:
        HotReloadPluginManager._clean_submodules("demo")

        assert "plugins.demo" not in sys.modules
        assert "plugins.demo.helper" not in sys.modules
        assert "plugins.demo_extra" in sys.modules
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


async def test_rqhmain_unload_releases_event_subscriptions() -> None:
    plugin = RqhmainPlugin()
    bus = EventBus()
    await PluginBase.on_load(plugin, None, bus)
    assert sum(len(v) for v in bus._handlers.values()) == 4

    await plugin.on_unload()

    assert sum(len(v) for v in bus._handlers.values()) == 0


async def test_rqhshen_unload_releases_event_subscriptions() -> None:
    plugin = RqhshenPlugin()
    bus = EventBus()
    await PluginBase.on_load(plugin, None, bus)
    assert sum(len(v) for v in bus._handlers.values()) == 4

    await plugin.on_unload()

    assert sum(len(v) for v in bus._handlers.values()) == 0


async def test_wenda_unload_persists_dirty_answers(tmp_path, monkeypatch) -> None:
    """卸载时必须把脏数据落盘，否则刚提示成功的修改会丢失"""
    manager = AnswerManager(str(tmp_path / "precise.json"), str(tmp_path / "fuzzy.json"))
    assert manager.add_precise_answer("问题", "答案")
    assert manager.dirty
    monkeypatch.setattr(wenda, "answer_manager", manager)

    plugin = wenda.RqhWendaPlugin()
    await plugin.on_unload()

    assert not manager.dirty
    saved = json.loads((tmp_path / "precise.json").read_text(encoding="utf-8"))
    assert saved == {"问题": "答案"}


async def test_pintu_score_uses_real_at_segments() -> None:
    """得分榜必须发送真正的 at 消息段，而不是字面 CQ 码"""
    plugin = PintuPlugin()
    plugin.api = MagicMock()
    plugin.api.send_group_message_segments = AsyncMock()
    session = plugin.game.get_session(1001)
    session.active = True
    session.scores = {"123": 2}

    await plugin._send_score(1001)

    segments = plugin.api.send_group_message_segments.await_args.args[1]
    assert {"type": "at", "data": {"qq": "123"}} in segments
    assert all("[CQ:at" not in json.dumps(seg, ensure_ascii=False) for seg in segments)
