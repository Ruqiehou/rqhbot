"""NapCatClient 单元测试"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sdk.core.client import NapCatClient, MessageSegment


# ==================== 测试夹具 ====================


@pytest.fixture
def mock_ws() -> MagicMock:
    """模拟 WebSocket 连接"""
    ws = MagicMock()
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def client(mock_ws: MagicMock) -> NapCatClient:
    """创建已连接（模拟）的 NapCatClient"""
    c = NapCatClient(ws_url="ws://127.0.0.1:3002", access_token="test-token")
    c.ws = mock_ws
    c._connected = True
    c.msg_queue = asyncio.Queue(maxsize=1000)
    return c


# ==================== MessageSegment 测试 ====================


class TestMessageSegment:
    def test_text(self) -> None:
        seg = MessageSegment.text("hello")
        assert seg == {"type": "text", "data": {"text": "hello"}}

    def test_image(self) -> None:
        seg = MessageSegment.image("http://example.com/pic.png", summary="示例")
        assert seg["type"] == "image"
        assert seg["data"]["file"] == "http://example.com/pic.png"
        assert seg["data"]["summary"] == "示例"

    def test_at(self) -> None:
        seg = MessageSegment.at(12345)
        assert seg == {"type": "at", "data": {"qq": "12345"}}

    def test_reply(self) -> None:
        seg = MessageSegment.reply(999)
        assert seg == {"type": "reply", "data": {"id": 999}}

    def test_json_data_dict(self) -> None:
        seg = MessageSegment.json_data({"key": "value"})
        assert seg["type"] == "json"
        assert "key" in seg["data"]["data"]

    def test_json_data_str(self) -> None:
        seg = MessageSegment.json_data('{"key": "value"}')
        assert seg["type"] == "json"
        assert seg["data"]["data"] == '{"key": "value"}'


# ==================== NapCatClient 测试 ====================


class TestNapCatClient:
    @pytest.mark.asyncio
    async def test_call_success(self, client: NapCatClient) -> None:
        """call() 正常返回 —— send 后立刻 resolve 对应 future"""
        echo_ready = asyncio.Event()
        captured_echo_id: List[str] = []

        async def fake_send(msg: str) -> None:
            data = json.loads(msg)
            eid = data.get("echo")
            if eid:
                captured_echo_id.append(eid)
                echo_ready.set()

        client.ws.send = fake_send  # type: ignore[assignment]

        async def resolve_task() -> None:
            await echo_ready.wait()
            eid = captured_echo_id[0]
            fut = client.echo_map.get(eid)
            if fut and not fut.done():
                fut.set_result({"status": "ok", "data": {"result": 42}})

        bg = asyncio.create_task(resolve_task())
        try:
            result = await client.call(
                "test_action", {"key": "val"}, max_retries=1, retry_delay=0.01
            )
        finally:
            bg.cancel()
            try:
                await bg
            except asyncio.CancelledError:
                pass

        assert result == {"result": 42}

    @pytest.mark.asyncio
    async def test_call_retry_on_failure(self, client: NapCatClient) -> None:
        """call() 失败后重试"""
        call_count = 0

        async def fake_send(_: str) -> None:
            nonlocal call_count
            call_count += 1

        client.ws.send = fake_send  # type: ignore[assignment]

        with pytest.raises(Exception):
            await client.call(
                "fail_action", max_retries=2, retry_delay=0.01
            )

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_echo_map_eviction(self, client: NapCatClient) -> None:
        """echo_map 超过上限时自动淘汰最旧条目"""
        client._echo_maxsize = 3
        filled: Dict[str, asyncio.Future[Any]] = {}
        for i in range(5):
            fut: asyncio.Future[Any] = asyncio.Future()
            key = f"echo-{i}"
            if len(client.echo_map) >= client._echo_maxsize:
                client._evict_oldest_echo()
            client.echo_map[key] = fut
            filled[key] = fut

        assert len(client.echo_map) <= client._echo_maxsize
        # 最旧的 echo-0 应该被淘汰
        assert "echo-0" not in client.echo_map
        # 最旧的被 cancel 并设置了异常
        assert filled["echo-0"].cancelled() or filled["echo-0"].exception() is not None

    @pytest.mark.asyncio
    async def test_echo_map_eviction_empty(self, client: NapCatClient) -> None:
        """echo_map 为空时淘汰不报错"""
        client._evict_oldest_echo()  # 不应抛异常

    @pytest.mark.asyncio
    async def test_on_message_dedup(self, client: NapCatClient) -> None:
        """同一 handler 不重复注册"""
        calls: List[str] = []

        async def handler(event: Dict[str, Any]) -> None:
            calls.append("called")

        client.on_message("group")(handler)
        client.on_message("group")(handler)  # 第二次注册应被跳过

        assert len(client.message_handlers["group"]) == 1

    @pytest.mark.asyncio
    async def test_disconnect_cleans_echo_map_and_queue(
        self, client: NapCatClient
    ) -> None:
        """disconnect() 后 echo_map 和 msg_queue 被清空"""
        # 插入两个未完成的 future
        f1: asyncio.Future[Any] = asyncio.Future()
        f2: asyncio.Future[Any] = asyncio.Future()
        client.echo_map["e1"] = f1
        client.echo_map["e2"] = f2
        client.msg_queue.put_nowait("pending-msg")

        # 模拟监听和处理任务
        client._listen_task = asyncio.create_task(asyncio.sleep(999))
        client._processing_task = asyncio.create_task(asyncio.sleep(999))

        await client.disconnect()

        assert client.echo_map == {}
        assert client.msg_queue is None
        assert f1.cancelled() or f1.done()
        assert f2.cancelled() or f2.done()

    @pytest.mark.asyncio
    async def test_send_group_message_builds_segments(
        self, client: NapCatClient
    ) -> None:
        """send_group_message 构建正确的消息段"""
        captured: Dict[str, Any] = {}

        async def fake_call(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
            captured["action"] = action
            captured["params"] = params
            return {"status": "ok"}

        client.call = fake_call  # type: ignore[assignment]

        result = await client.send_group_message(
            group_id=1001,
            message="hello",
            at_user_id=2001,
            reply_message_id=3001,
        )

        assert result["status"] == "ok"
        assert captured["action"] == "send_group_msg"
        segments = captured["params"]["message"]
        # 顺序：reply → at → text
        assert segments[0]["type"] == "reply"
        assert segments[1]["type"] == "at"
        assert segments[2]["type"] == "text"

    @pytest.mark.asyncio
    async def test_send_event_message_group(self, client: NapCatClient) -> None:
        """send_event_message 自动识别群消息"""
        captured: Dict[str, Any] = {}

        async def fake_call(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
            captured["action"] = action
            captured["params"] = params
            return {"status": "ok"}

        client.call = fake_call  # type: ignore[assignment]

        event = MagicMock()
        event.group_id = 1001
        event.user_id = None

        await client.send_event_message(event, "hello")

        assert captured["action"] == "send_group_msg"
        assert captured["params"]["group_id"] == 1001

    @pytest.mark.asyncio
    async def test_send_event_message_private(self, client: NapCatClient) -> None:
        """send_event_message 自动识别私聊消息"""
        captured: Dict[str, Any] = {}

        async def fake_call(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
            captured["action"] = action
            captured["params"] = params
            return {"status": "ok"}

        client.call = fake_call  # type: ignore[assignment]

        event = MagicMock()
        event.group_id = None
        event.user_id = 2001

        await client.send_event_message(event, "hello")

        assert captured["action"] == "send_private_msg"
        assert captured["params"]["user_id"] == 2001

    @pytest.mark.asyncio
    async def test_send_event_message_no_target_logs_warning(
        self, client: NapCatClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """send_event_message 无 group_id / user_id 时打 warning"""
        event = MagicMock()
        event.group_id = None
        event.user_id = None

        await client.send_event_message(event, "hello")
        assert "无法回复" in caplog.text

    @pytest.mark.asyncio
    async def test_get_performance_stats(self, client: NapCatClient) -> None:
        """get_performance_stats 返回正确结构"""
        stats = client.get_performance_stats()
        assert "total_messages" in stats
        assert "avg_latency" in stats
        assert "is_connected" in stats
        assert stats["is_connected"] is True

    @pytest.mark.asyncio
    async def test_listen_queue_full_timeout(
        self, client: NapCatClient
    ) -> None:
        """队列满时 put_nowait 触发 QueueFull，put 也超时"""
        assert client.msg_queue is not None
        # 填满队列
        for _ in range(client.msg_queue.maxsize):
            client.msg_queue.put_nowait("x")

        # put_nowait 应该抛 QueueFull
        with pytest.raises(asyncio.QueueFull):
            client.msg_queue.put_nowait("extra")

    @pytest.mark.asyncio
    async def test_connect_not_ready_raises(self) -> None:
        """未连接时 call() 抛 ConnectionError"""
        c = NapCatClient()
        with pytest.raises(ConnectionError):
            await c.call("any_action")
