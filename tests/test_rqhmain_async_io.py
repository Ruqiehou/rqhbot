"""回归测试：rqhmain 异步 I/O 与帮助指令路由

DEFECT 1：异步处理器内联 blocking requests.get 冻结整个事件循环。
DEFECT 2：help.md 记录的 帮助/使用说明/功能 触发词没有任何回复。

所有 HTTP 层都被替换为本地桩，不产生真实网络请求。
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from plugins.rqhmain import main as rqhmain_main
from plugins.rqhmain.main import RqhmainPlugin


def _event(text: str, user_id: int = 2, group_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        message=SimpleNamespace(plain_text=text),
        group_id=group_id,
        user_id=user_id,
    )


def _reply_text(mock_api) -> str:
    call = mock_api.send_group_message.await_args
    if call is None:
        return ""
    return call.kwargs.get("message", "")


class _Heartbeat:
    """并发心跳协程：统计事件循环在处理器运行期间调度了多少次。"""

    def __init__(self, interval: float = 0.01) -> None:
        self.ticks = 0
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            self.ticks += 1

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        assert self._task is not None
        self._task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await self._task


# ==================== DEFECT 1：事件循环阻塞 ====================


async def test_weather_does_not_block_event_loop(monkeypatch, mock_api) -> None:
    """天气查询里的同步 HTTP 必须移到线程，否则心跳协程被饿死。"""
    calls: list[str] = []

    class BlockingWeatherAPI:
        def query_weather(self, city: str, info_type: str = "weather"):
            calls.append(city)
            time.sleep(0.3)  # 模拟 requests.get 的同步阻塞
            return {"success": True, "city": city, "data": {"temp": "20"}}

    monkeypatch.setattr(rqhmain_main, "WeatherAPI", BlockingWeatherAPI)
    plugin = RqhmainPlugin()
    plugin.api = mock_api

    heartbeat = _Heartbeat()
    heartbeat.start()
    await plugin.rqhbase_group(_event("天气 北京"))
    await heartbeat.stop()

    assert calls == ["北京"]
    # 0.3s 的阻塞期间，10ms 心跳应能跑约 30 次；被阻塞时只有 0~1 次。
    assert heartbeat.ticks >= 10, f"事件循环被阻塞，心跳仅 {heartbeat.ticks} 次"
    mock_api.send_group_message.assert_awaited()
    await plugin.on_unload()


async def test_news_does_not_block_event_loop(monkeypatch, mock_api) -> None:
    """新闻查询里的同步 HTTP 必须移到线程，否则心跳协程被饿死。"""
    calls: list[int] = []

    class BlockingNewsAPI:
        def get_news(self):
            calls.append(1)
            time.sleep(0.3)
            return {"title": "60秒", "content": ["新闻一"]}

    monkeypatch.setattr(rqhmain_main, "NewsAPI", BlockingNewsAPI)
    plugin = RqhmainPlugin()
    plugin.api = mock_api

    heartbeat = _Heartbeat()
    heartbeat.start()
    await plugin.rqhbase_group(_event("新闻"))
    await heartbeat.stop()

    assert len(calls) == 1
    assert heartbeat.ticks >= 10, f"事件循环被阻塞，心跳仅 {heartbeat.ticks} 次"
    mock_api.send_group_message.assert_awaited()
    await plugin.on_unload()


async def test_weather_failure_replies_friendly(monkeypatch, mock_api) -> None:
    """网络失败必须返回原有友好错误文案，而不是抛出未处理异常。"""
    class FailingWeatherAPI:
        def query_weather(self, city: str, info_type: str = "weather"):
            raise RuntimeError("connection reset")

    monkeypatch.setattr(rqhmain_main, "WeatherAPI", FailingWeatherAPI)
    plugin = RqhmainPlugin()
    plugin.api = mock_api

    await plugin.rqhbase_group(_event("天气 北京"))

    text = _reply_text(mock_api)
    assert "查询天气时出错" in text
    await plugin.on_unload()


async def test_weather_api_error_result_replies_friendly(monkeypatch, mock_api) -> None:
    """API 自身返回 success=False 时同样给出友好错误文案。"""
    class ErrorWeatherAPI:
        def query_weather(self, city: str, info_type: str = "weather"):
            return {"success": False, "city": city, "error": "timeout"}

    monkeypatch.setattr(rqhmain_main, "WeatherAPI", ErrorWeatherAPI)
    plugin = RqhmainPlugin()
    plugin.api = mock_api

    await plugin.rqhbase_group(_event("天气 北京"))

    text = _reply_text(mock_api)
    assert "查询 北京 天气失败" in text
    assert "timeout" in text
    await plugin.on_unload()


async def test_news_failure_replies_friendly(monkeypatch, mock_api) -> None:
    """新闻接口返回 None 时保留原有友好提示。"""
    class EmptyNewsAPI:
        def get_news(self):
            return None

    monkeypatch.setattr(rqhmain_main, "NewsAPI", EmptyNewsAPI)
    plugin = RqhmainPlugin()
    plugin.api = mock_api

    await plugin.rqhbase_group(_event("新闻"))

    assert _reply_text(mock_api) == "获取新闻失败，请稍后重试"
    await plugin.on_unload()


async def test_weather_cooldown_limits_repeat_requests(monkeypatch, mock_api) -> None:
    """同一用户短时间内重复请求只应真正查询一次，避免排队耗尽事件循环。"""
    calls: list[str] = []

    class CountingWeatherAPI:
        def query_weather(self, city: str, info_type: str = "weather"):
            calls.append(city)
            return {"success": True, "city": city, "data": {"temp": "20"}}

    monkeypatch.setattr(rqhmain_main, "WeatherAPI", CountingWeatherAPI)
    plugin = RqhmainPlugin()
    plugin.api = mock_api

    await plugin.rqhbase_group(_event("天气 北京"))
    await plugin.rqhbase_group(_event("天气 北京"))

    assert calls == ["北京"]
    assert mock_api.send_group_message.await_count == 2
    assert "频繁" in _reply_text(mock_api)
    await plugin.on_unload()


async def test_news_cooldown_is_per_user(monkeypatch, mock_api) -> None:
    """限流应按用户隔离，其他用户不应被一起拦截。"""
    calls: list[int] = []

    class CountingNewsAPI:
        def get_news(self):
            calls.append(1)
            return None

    monkeypatch.setattr(rqhmain_main, "NewsAPI", CountingNewsAPI)
    plugin = RqhmainPlugin()
    plugin.api = mock_api

    await plugin.rqhbase_group(_event("新闻", user_id=10))
    await plugin.rqhbase_group(_event("新闻", user_id=11))

    assert len(calls) == 2
    await plugin.on_unload()


# ==================== DEFECT 2：帮助指令路由 ====================


@pytest.mark.parametrize("trigger", ["帮助", "使用说明", "功能", "指南"])
async def test_help_triggers_reply(monkeypatch, mock_api, trigger: str) -> None:
    """help.md 记录的触发词必须都能得到帮助回复。"""
    plugin = RqhmainPlugin()
    plugin.api = mock_api

    await plugin.rqhbase_group(_event(trigger))

    mock_api.send_group_message.assert_awaited_once()
    assert "使用指南" in _reply_text(mock_api)
    await plugin.on_unload()


async def test_help_trigger_works_in_private_chat(mock_api) -> None:
    plugin = RqhmainPlugin()
    plugin.api = mock_api

    await plugin.rqhbase_private(_event("使用说明", group_id=None))

    mock_api.send_private_message.assert_awaited_once()
    assert "使用指南" in mock_api.send_private_message.await_args.kwargs["message"]
    await plugin.on_unload()


async def test_unrelated_message_gets_no_reply(mock_api) -> None:
    """无关消息不能被帮助路由劫持。"""
    plugin = RqhmainPlugin()
    plugin.api = mock_api

    await plugin.rqhbase_group(_event("你好呀"))

    mock_api.send_group_message.assert_not_awaited()
    await plugin.on_unload()
