"""
RqhBot SDK —— 核心模块
提供客户端连接、API 调用、事件模型等基础能力
"""

from __future__ import annotations

from .client import NapCatClient, OneBotClient
from .event_bus import EventBus
from .events import (
    BaseEvent,
    EssenceMsgNotice,
    FriendAddNotice,
    FriendRecallNotice,
    FriendRequestEvent,
    GroupAdminNotice,
    GroupBanNotice,
    GroupCardNotice,
    GroupDecreaseNotice,
    GroupIncreaseNotice,
    GroupMessageEvent,
    GroupRecallNotice,
    GroupRequestEvent,
    GroupUploadNotice,
    HeartbeatEvent,
    LifecycleEvent,
    Message,
    MetaEvent,
    NoticeEvent,
    PokeNotice,
    PrivateMessageEvent,
    RequestEvent,
)
from .messages import MessageSegment
from .settings import ClientSettings

__all__: list[str] = [
    "BaseEvent",
    "ClientSettings",
    "EssenceMsgNotice",
    "EventBus",
    "FriendAddNotice",
    "FriendRecallNotice",
    "FriendRequestEvent",
    "GroupAdminNotice",
    "GroupBanNotice",
    "GroupCardNotice",
    "GroupDecreaseNotice",
    "GroupIncreaseNotice",
    "GroupMessageEvent",
    "GroupRecallNotice",
    "GroupRequestEvent",
    "GroupUploadNotice",
    "HeartbeatEvent",
    "LifecycleEvent",
    "Message",
    "MessageSegment",
    "MetaEvent",
    "NapCatClient",
    "NoticeEvent",
    "OneBotClient",
    "PokeNotice",
    "PrivateMessageEvent",
    "RequestEvent",
]
