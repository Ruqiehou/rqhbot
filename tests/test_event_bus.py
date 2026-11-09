"""事件总线测试"""

from __future__ import annotations

import pytest

from sdk.core.event_bus import EventBus
from sdk.core.events import GroupMessageEvent


@pytest.mark.asyncio
async def test_subscribe_and_publish() -> None:
    """测试订阅和发布"""
    bus = EventBus()
    received: list[GroupMessageEvent] = []

    async def handler(event: GroupMessageEvent) -> None:
        received.append(event)

    bus.subscribe(GroupMessageEvent, handler)

    event = GroupMessageEvent(group_id=1001, user_id=2001)
    await bus.publish(event)

    assert len(received) == 1
    assert received[0].group_id == 1001


@pytest.mark.asyncio
async def test_unsubscribe() -> None:
    """测试取消订阅"""
    bus = EventBus()
    received: list[GroupMessageEvent] = []

    async def handler(event: GroupMessageEvent) -> None:
        received.append(event)

    bus.subscribe(GroupMessageEvent, handler)
    bus.unsubscribe(GroupMessageEvent, handler)

    event = GroupMessageEvent(group_id=1001)
    await bus.publish(event)

    assert len(received) == 0


@pytest.mark.asyncio
async def test_multiple_handlers() -> None:
    """测试多个处理器"""
    bus = EventBus()
    results: list[str] = []

    async def handler1(event: GroupMessageEvent) -> None:
        results.append("h1")

    async def handler2(event: GroupMessageEvent) -> None:
        results.append("h2")

    bus.subscribe(GroupMessageEvent, handler1)
    bus.subscribe(GroupMessageEvent, handler2)

    await bus.publish(GroupMessageEvent())

    assert "h1" in results
    assert "h2" in results


@pytest.mark.asyncio
async def test_handler_error_does_not_break_others() -> None:
    """测试处理器异常不影响其他处理器"""
    bus = EventBus()
    received: list[str] = []

    async def bad_handler(event: GroupMessageEvent) -> None:
        raise ValueError("test error")

    async def good_handler(event: GroupMessageEvent) -> None:
        received.append("ok")

    bus.subscribe(GroupMessageEvent, bad_handler)
    bus.subscribe(GroupMessageEvent, good_handler)

    await bus.publish(GroupMessageEvent())

    assert "ok" in received


@pytest.mark.asyncio
async def test_no_handlers() -> None:
    """测试无处理器时不报错"""
    bus = EventBus()
    await bus.publish(GroupMessageEvent())  # Should not raise
