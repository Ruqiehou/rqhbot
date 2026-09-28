"""EventBus 分发的回归测试

覆盖已确认缺陷：``EventBus.publish`` 使用 ``type(event)`` 精确匹配，
导致订阅基类（NoticeEvent / RequestEvent）的处理器永远收不到具体子类事件
（PokeNotice / GroupIncreaseNotice / FriendRequestEvent ...）。

同时锁定必须保持的语义：快照分发、去重、单个处理器异常不影响其他处理器。
"""

from __future__ import annotations

from typing import List

from sdk.core.event_bus import EventBus
from sdk.core.events import (
    BaseEvent,
    FriendRequestEvent,
    GroupIncreaseNotice,
    GroupMessageEvent,
    NoticeEvent,
    PokeNotice,
    RequestEvent,
)


class TestMroDispatch:
    """沿 MRO 分发"""

    async def test_base_notice_subscription_receives_subclass(self) -> None:
        """订阅 NoticeEvent 应收到 PokeNotice"""
        bus = EventBus()
        received: List[BaseEvent] = []

        async def handler(event: NoticeEvent) -> None:
            received.append(event)

        bus.subscribe(NoticeEvent, handler)
        event = PokeNotice(target_id=999, user_id=1)
        await bus.publish(event)

        assert received == [event]

    async def test_base_notice_subscription_receives_group_increase(self) -> None:
        bus = EventBus()
        received: List[BaseEvent] = []

        async def handler(event: NoticeEvent) -> None:
            received.append(event)

        bus.subscribe(NoticeEvent, handler)
        await bus.publish(GroupIncreaseNotice(user_id=1, group_id=2))

        assert len(received) == 1
        assert isinstance(received[0], GroupIncreaseNotice)

    async def test_base_request_subscription_receives_subclass(self) -> None:
        """订阅 RequestEvent 应收到 FriendRequestEvent"""
        bus = EventBus()
        received: List[BaseEvent] = []

        async def handler(event: RequestEvent) -> None:
            received.append(event)

        bus.subscribe(RequestEvent, handler)
        event = FriendRequestEvent(user_id=1, comment="hi")
        await bus.publish(event)

        assert received == [event]

    async def test_concrete_subscription_still_works(self) -> None:
        bus = EventBus()
        received: List[BaseEvent] = []

        async def handler(event: PokeNotice) -> None:
            received.append(event)

        bus.subscribe(PokeNotice, handler)
        await bus.publish(PokeNotice(target_id=5))

        assert len(received) == 1

    async def test_handler_for_two_matching_classes_runs_once(self) -> None:
        """同一处理器同时订阅子类和基类时只运行一次（去重）"""
        bus = EventBus()
        calls: List[str] = []

        async def handler(event: NoticeEvent) -> None:
            calls.append("called")

        bus.subscribe(PokeNotice, handler)
        bus.subscribe(NoticeEvent, handler)
        await bus.publish(PokeNotice())

        assert calls == ["called"]

    async def test_unrelated_base_handler_not_called(self) -> None:
        """NoticeEvent 的订阅者不应收到 GroupMessageEvent"""
        bus = EventBus()
        received: List[BaseEvent] = []

        async def handler(event: NoticeEvent) -> None:
            received.append(event)

        bus.subscribe(NoticeEvent, handler)
        await bus.publish(GroupMessageEvent(group_id=1))

        assert received == []

    async def test_concrete_and_base_both_run(self) -> None:
        bus = EventBus()
        calls: List[str] = []

        async def concrete_handler(event: PokeNotice) -> None:
            calls.append("concrete")

        async def base_handler(event: NoticeEvent) -> None:
            calls.append("base")

        bus.subscribe(PokeNotice, concrete_handler)
        bus.subscribe(NoticeEvent, base_handler)
        await bus.publish(PokeNotice())

        assert sorted(calls) == ["base", "concrete"]

    async def test_unsubscribe_base_stops_subclass_delivery(self) -> None:
        """unsubscribe 基类后，子类事件不再送达"""
        bus = EventBus()
        received: List[BaseEvent] = []

        async def handler(event: NoticeEvent) -> None:
            received.append(event)

        bus.subscribe(NoticeEvent, handler)
        bus.unsubscribe(NoticeEvent, handler)
        await bus.publish(PokeNotice())

        assert received == []

    async def test_unsubscribe_concrete_keeps_base(self) -> None:
        """unsubscribe 子类不影响基类订阅"""
        bus = EventBus()
        received: List[BaseEvent] = []

        async def concrete_handler(event: PokeNotice) -> None:
            received.append("concrete")

        async def base_handler(event: NoticeEvent) -> None:
            received.append("base")

        bus.subscribe(PokeNotice, concrete_handler)
        bus.subscribe(NoticeEvent, base_handler)
        bus.unsubscribe(PokeNotice, concrete_handler)
        await bus.publish(PokeNotice())

        assert received == ["base"]

    async def test_unsubscribe_during_dispatch_does_not_affect_inflight(self) -> None:
        """分发过程中的 unsubscribe 不影响本次分发（快照语义）"""
        bus = EventBus()
        calls: List[str] = []

        async def second(event: NoticeEvent) -> None:
            calls.append("second")

        async def first(event: NoticeEvent) -> None:
            calls.append("first")
            bus.unsubscribe(NoticeEvent, second)

        bus.subscribe(NoticeEvent, first)
        bus.subscribe(NoticeEvent, second)

        await bus.publish(PokeNotice())

        assert sorted(calls) == ["first", "second"]

    async def test_subscribe_during_dispatch_does_not_affect_inflight(self) -> None:
        """分发过程中的 subscribe 不影响本次分发（快照语义）"""
        bus = EventBus()
        calls: List[str] = []

        async def late(event: NoticeEvent) -> None:
            calls.append("late")

        async def first(event: NoticeEvent) -> None:
            calls.append("first")
            bus.subscribe(NoticeEvent, late)

        bus.subscribe(NoticeEvent, first)
        await bus.publish(PokeNotice())

        assert calls == ["first"]

    async def test_raising_handler_does_not_prevent_others(self) -> None:
        """一个抛异常的子类处理器不影响其他处理器"""
        bus = EventBus()
        received: List[str] = []

        async def bad_handler(event: NoticeEvent) -> None:
            raise ValueError("boom")

        async def good_handler(event: NoticeEvent) -> None:
            received.append("ok")

        bus.subscribe(NoticeEvent, bad_handler)
        bus.subscribe(NoticeEvent, good_handler)
        bus.subscribe(PokeNotice, good_handler)  # 同时匹配两个类，去重后仍应只跑一次

        await bus.publish(PokeNotice())

        assert received == ["ok"]

    async def test_base_exception_handler_does_not_prevent_others(self) -> None:
        """非 Exception 的 BaseException 也不影响其他处理器（守卫）"""
        bus = EventBus()
        received: List[str] = []

        class Boom(BaseException):
            pass

        async def bad_handler(event: NoticeEvent) -> None:
            raise Boom("boom")

        async def good_handler(event: NoticeEvent) -> None:
            received.append("ok")

        bus.subscribe(NoticeEvent, bad_handler)
        bus.subscribe(NoticeEvent, good_handler)

        await bus.publish(PokeNotice())

        assert received == ["ok"]

    async def test_no_handlers_on_subclass_path_is_noop(self) -> None:
        bus = EventBus()
        await bus.publish(PokeNotice())  # 不应抛异常
        await bus.publish(FriendRequestEvent())  # 不应抛异常
