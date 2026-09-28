"""回归测试：call() 重试策略、断开时 pending future 语义、队列 drain

覆盖的确认缺陷：
1. call() 对非幂等的 send_* 动作自动重试 → 重复发消息 + 长时间阻塞
2. disconnect() 用 future.cancel() 注入 CancelledError，绕过 ConnectionError 处理
3. 关闭时处理循环退出但不 drain 已入队消息 → 静默丢消息
4. 重试循环未重新检查连接状态 → AttributeError 而非 ConnectionError
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List
from unittest.mock import AsyncMock

import pytest

from sdk.core.client import NapCatClient


# ==================== 夹具 ====================


@pytest.fixture
def client() -> NapCatClient:
    """已连接（模拟）的 NapCatClient，call 超时被调小以便快速测试"""
    c = NapCatClient(ws_url="ws://127.0.0.1:3002", access_token="test-token")
    c.ws = AsyncMock()
    c._connected = True
    c.msg_queue = asyncio.Queue(maxsize=1000)
    c._call_timeout = 0.05
    return c


class _ScriptedSocket:
    """可控的 websocket 替身：按脚本 yield 消息，之后结束 async for"""

    def __init__(self, messages: List[str]) -> None:
        self._messages = list(messages)
        self._first_yield = asyncio.Event()

    def __aiter__(self) -> "_ScriptedSocket":
        return self

    async def __anext__(self) -> str:
        if not self._messages:
            raise StopAsyncIteration
        msg = self._messages.pop(0)
        self._first_yield.set()
        return msg


# ==================== 缺陷 1：send_* 不得自动重试 ====================


async def test_send_action_not_retried(client: NapCatClient) -> None:
    """send_group_msg 超时后绝不能重发（否则用户收到重复消息）"""
    sends: List[Dict[str, Any]] = []

    async def fake_send(payload: str) -> None:
        sends.append(json.loads(payload))

    client.ws.send = fake_send  # type: ignore[assignment]

    with pytest.raises(TimeoutError):
        await client.call("send_group_msg", {"group_id": 1}, max_retries=3, retry_delay=0.01)

    assert len(sends) == 1, f"非幂等动作被重试了 {len(sends)} 次"

    # 超时后 echo_map 必须清理干净
    assert client.echo_map == {}


async def test_send_private_action_not_retried(client: NapCatClient) -> None:
    """send_private_msg / send_msg 同样不得重试"""
    for action in ("send_private_msg", "send_msg", "send_group_file"):
        count = 0

        async def fake_send(_: str) -> None:
            nonlocal count
            count += 1

        client.ws.send = fake_send  # type: ignore[assignment]
        with pytest.raises(TimeoutError):
            await client.call(action, {}, max_retries=3, retry_delay=0.01)
        assert count == 1, f"{action} 被重试了 {count} 次"


async def test_idempotent_action_still_retried(client: NapCatClient) -> None:
    """查询类动作仍保留重试能力"""
    count = 0

    async def fake_send(_: str) -> None:
        nonlocal count
        count += 1

    client.ws.send = fake_send  # type: ignore[assignment]

    with pytest.raises(TimeoutError):
        await client.call("get_login_info", max_retries=3, retry_delay=0.01)

    assert count == 3


# ==================== 缺陷 2：断开 → ConnectionError 而非 CancelledError ====================


async def test_disconnect_fails_pending_call_with_connection_error(
    client: NapCatClient,
) -> None:
    """disconnect() 必须用 ConnectionError 结束 pending call，而不是注入 CancelledError"""
    client._call_timeout = 5.0
    started = asyncio.Event()

    async def fake_send(_: str) -> None:
        started.set()

    client.ws.send = fake_send  # type: ignore[assignment]

    task = asyncio.create_task(client.call("get_login_info", max_retries=1))
    await started.wait()
    # 确保 future 已注册
    for _ in range(50):
        if client.echo_map:
            break
        await asyncio.sleep(0)

    await client.disconnect()

    with pytest.raises(ConnectionError):
        await task


async def test_disconnect_leaves_externally_cancelled_future_alone(
    client: NapCatClient,
) -> None:
    """被外部取消的 future 保持 cancelled 状态，不能改写成 ConnectionError"""
    fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
    client.echo_map["ext"] = fut
    fut.cancel()

    await client.disconnect()

    assert fut.cancelled()


# ==================== 缺陷 3：关闭时 drain 已入队消息 ====================


async def test_process_messages_drains_queue_after_disconnect(
    client: NapCatClient,
) -> None:
    """socket 关闭后，已入队的消息必须被处理而不是静默丢弃"""
    processed: List[Dict[str, Any]] = []
    done = asyncio.Event()

    async def handler(data: Dict[str, Any]) -> None:
        processed.append(data)
        done.set()

    client.message_handlers["message"] = [handler]

    for i in range(3):
        client.msg_queue.put_nowait(json.dumps({"post_type": "message", "i": i}))

    task = asyncio.create_task(client._process_messages())
    for _ in range(50):
        if processed:
            break
        await asyncio.sleep(0)

    # 模拟 socket 关闭：接收循环 finally 置 False（此时队列里还有消息）
    client._connected = False

    await asyncio.wait_for(done.wait(), timeout=2.0)
    await asyncio.wait_for(task, timeout=2.0)

    assert len(processed) == 3, f"只处理了 {len(processed)}/3 条队列消息"


async def test_process_messages_stops_when_queue_empty(client: NapCatClient) -> None:
    """drain 完成后处理循环必须退出，不能挂死"""
    client._connected = False
    task = asyncio.create_task(client._process_messages())
    await asyncio.wait_for(task, timeout=2.0)


# ==================== 缺陷 4：重试前重新检查连接 ====================


async def test_retry_after_midflight_disconnect_raises_connection_error(
    client: NapCatClient,
) -> None:
    """第一次尝试中连接被断开，重试必须抛 ConnectionError 而非 AttributeError"""
    calls = 0

    async def fake_send(_: str) -> None:
        nonlocal calls
        calls += 1
        # 模拟发送过程中连接异常断开
        client.ws = None
        client._connected = False

    client.ws.send = fake_send  # type: ignore[assignment]

    with pytest.raises(ConnectionError):
        await client.call("get_login_info", max_retries=3, retry_delay=0.01)

    assert calls == 1


# ==================== 缺陷 1 附带：超时可覆盖/可调用 ====================


async def test_call_timeout_accepts_callable(client: NapCatClient) -> None:
    """_call_timeout 支持 callable，便于测试与运行时调整"""
    client._call_timeout = lambda: 0.05
    asserts = 0

    async def fake_send(_: str) -> None:
        nonlocal asserts
        asserts += 1

    client.ws.send = fake_send  # type: ignore[assignment]

    with pytest.raises(TimeoutError):
        await client.call("send_group_msg", {}, max_retries=1)

    assert asserts == 1
