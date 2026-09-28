from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Type, TypeVar

from sdk.core.events import BaseEvent

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=BaseEvent)
Handler = Callable[[Any], Awaitable[None]]


class EventBus:
    """事件总线 —— 所有模块通过它发布/订阅事件，互不直接依赖"""

    def __init__(self) -> None:
        self._handlers: Dict[Type[BaseEvent], List[Handler]] = {}

    def subscribe(self, event_type: Type[E], handler: Callable[[E], Awaitable[None]]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: Type[E], handler: Callable[[E], Awaitable[None]]) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: BaseEvent) -> None:
        # 沿 MRO 分发：既触发具体类型的订阅者，也触发其基类（如 NoticeEvent / RequestEvent）的订阅者。
        # 快照：先收集并去重，冻结本次分发的处理器列表，分发过程中的订阅/退订不影响本次分发。
        handlers: List[Handler] = []
        for event_cls in type(event).__mro__:
            for handler in self._handlers.get(event_cls, []):
                if handler not in handlers:
                    handlers.append(handler)
        if not handlers:
            return

        tasks = [
            asyncio.create_task(self._run_handler(handler, event))
            for handler in handlers
        ]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, BaseException):
                    logger.error(f"EventBus handler error [{type(event).__name__}]: {r}")

    async def _run_handler(self, handler: Handler, event: BaseEvent) -> None:
        """运行处理器并捕获异常"""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"EventBus handler error [{type(event).__name__}][{handler.__name__}]: {e}", exc_info=True)
