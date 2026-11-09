"""
OneBot 客户端

``OneBotClient`` 现在是「传输 + API 封装」的组合门面：

- 连接 / 重连 / 收发 / echo 匹配 → :mod:`sdk.core.transport`
- OneBot 动作封装 → :mod:`sdk.core.api`
- 事件分发与处理器调度 → 本模块

运行参数通过 ``ClientSettings`` 注入，核心层不再读取全局 config_manager。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from sdk.adapter import BackendSpec, get_backend
from sdk.core.api import APIMixin
from sdk.core.interfaces import EventHandler, IClient
from sdk.core.messages import MessageSegment
from sdk.core.settings import ClientSettings
from sdk.core.transport import TransportMixin

logger = logging.getLogger(__name__)

# ---- 类型别名 ----
Decorator = Callable[[EventHandler], EventHandler]


class OneBotClient(TransportMixin, APIMixin, IClient):
    """OneBot 11 客户端 —— 支持 NapCat / SnowLuma 后端，实现 IClient Protocol

    Args:
        ws_url: WebSocket 地址，缺省取 ``settings.ws_url`` 或后端默认值
        access_token: 访问令牌，缺省取 ``settings.access_token``
        backend: 后端名称（napcat / snowluma）
        settings: 运行参数快照；None 时只从环境变量读取
            （需要读取 config.yaml 请传入 ``ClientSettings.from_config(config)``）
    """

    def __init__(
        self,
        ws_url: str | None = None,
        access_token: str | None = None,
        backend: str | None = None,
        settings: ClientSettings | None = None,
    ) -> None:
        self.backend: BackendSpec = get_backend(backend)
        self.settings: ClientSettings = settings or ClientSettings.from_env()
        raw_url: str = ws_url or self.settings.ws_url or self.backend.default_ws_uri
        self.ws_url: str = raw_url
        self.access_token: str = (
            access_token if access_token is not None else self.settings.access_token
        )

        # ---- 事件处理器注册表 ----
        self.message_handlers: dict[str, list[EventHandler]] = {}

        # ---- 处理器并发控制 ----
        self._handler_semaphore: asyncio.Semaphore = asyncio.Semaphore(64)
        self._session_locks: dict[str, asyncio.Lock] = {}

        # ---- 连接相关状态（见 TransportMixin）----
        self._init_transport_state()

    # ======================== 事件注册 ========================

    def on_message(self, message_type: str) -> Decorator:
        """装饰器：注册消息事件处理器

        Args:
            message_type: 消息类型（'group' / 'private' / 'notice' / 'request'）

        Returns:
            装饰器函数
        """
        def decorator(func: EventHandler) -> EventHandler:
            handlers = self.message_handlers.setdefault(message_type, [])
            if func not in handlers:
                handlers.append(func)
            else:
                logger.debug("处理器 %s 已注册到 %s，跳过重复注册", func.__name__, message_type)
            return func
        return decorator

    # ======================== 事件分发 ========================

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """处理下行消息：先匹配 API 响应，再分发给事件处理器"""
        # API 响应（含 echo）由传输层完成对应的 Future
        if self._resolve_echo(data):
            return

        post_type = data.get("post_type")
        message_type = data.get("message_type")

        event_types = []
        if post_type:
            event_types.append(post_type)
        if message_type and message_type != post_type:
            event_types.append(message_type)

        seen: set[int] = set()
        for event_type in event_types:
            for handler in self.message_handlers.get(event_type, []):
                handler_id = id(handler)
                if handler_id in seen:
                    continue
                seen.add(handler_id)
                try:
                    task = asyncio.create_task(self._run_handler(handler, data))
                    task.add_done_callback(self._on_handler_task_done)
                except Exception as e:
                    logger.error(f"创建处理器任务失败: {e}", exc_info=True)

    @staticmethod
    def _session_key(data: dict[str, Any]) -> str:
        """提取会话标识，用于保证同一会话内的处理器串行执行"""
        group_id = data.get("group_id")
        if group_id is not None:
            return f"group:{group_id}"
        user_id = data.get("user_id")
        if user_id is not None:
            return f"private:{user_id}"
        return "global"

    async def _run_handler(
        self, handler: EventHandler, data: dict[str, Any]
    ) -> None:
        """在并发上限内执行处理器，并保证同一会话内顺序执行"""
        async with self._handler_semaphore:
            lock = self._session_locks.setdefault(
                self._session_key(data), asyncio.Lock()
            )
            async with lock:
                await handler(data)

    @staticmethod
    def _on_handler_task_done(task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f"消息处理器异常: {exc}", exc_info=exc)


# 向后兼容别名：早期版本仅支持 NapCat，客户端名为 NapCatClient
NapCatClient = OneBotClient

# 兼容旧导入路径：MessageSegment 已迁至 sdk.core.messages
__all__: list[str] = ["MessageSegment", "NapCatClient", "OneBotClient"]
