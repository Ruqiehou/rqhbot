"""
RqhBot SDK —— 主入口模块
提供完整的机器人开发功能：连接、事件、API、插件系统、配置管理
"""

from __future__ import annotations

from .bot_client import BotClient
from .config import Config, setup_logging
from .core import (
    BaseEvent,
    EventBus,
    FriendRecallNotice,
    FriendRequestEvent,
    GroupBanNotice,
    GroupDecreaseNotice,
    GroupIncreaseNotice,
    GroupMessageEvent,
    GroupRecallNotice,
    GroupRequestEvent,
    Message,
    NapCatClient,
    NoticeEvent,
    OneBotClient,
    PokeNotice,
    PrivateMessageEvent,
    RequestEvent,
)
from .pluginsystem import (
    HotReloadPluginManager,
    PluginBase,
    PluginManager,
    filter_registry,
    group_server,
    message_filter,
    private_server,
)

__version__: str = "3.8.0"

__all__: list[str] = [
    "BaseEvent",
    "BotClient",
    "Config",
    "EventBus",
    "FriendRecallNotice",
    "FriendRequestEvent",
    "GroupBanNotice",
    "GroupDecreaseNotice",
    "GroupIncreaseNotice",
    "GroupMessageEvent",
    "GroupRecallNotice",
    "GroupRequestEvent",
    "HotReloadPluginManager",
    "Message",
    "NapCatClient",
    "NoticeEvent",
    "OneBotClient",
    "PluginBase",
    "PluginManager",
    "PokeNotice",
    "PrivateMessageEvent",
    "RequestEvent",
    "__version__",
    "filter_registry",
    "group_server",
    "message_filter",
    "private_server",
    "setup_logging",
]
