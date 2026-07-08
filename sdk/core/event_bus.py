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
        # 快照：冻结当前处理器列表，防止分发过程中变更
        handlers = list(self._handlers.get(type(event), []))
        if not handlers:
            return

        tasks = [
            asyncio.create_task(self._run_handler(handler, event))
            for handler in handlers
        ]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"EventBus handler error [{type(event).__name__}]: {r}")

    async def _run_handler(self, handler: Handler, event: BaseEvent) -> None:
        """运行处理器并捕获异常"""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"EventBus handler error [{type(event).__name__}][{handler.__name__}]: {e}", exc_info=True)
