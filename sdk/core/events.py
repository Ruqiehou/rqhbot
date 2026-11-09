"""
事件类定义
定义各种机器人事件的数据结构，所有字段均为强类型声明
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Any

if sys.version_info >= (3, 11):
    from typing import Self
else:  # pragma: no cover - Python 3.10 兼容
    from typing_extensions import Self

from .emoji_map import get_face_name

logger = logging.getLogger(__name__)

# ---- 类型别名 ----
MessageSegmentData = dict[str, Any]
SenderInfo = dict[str, Any]
EventData = dict[str, Any]

# ---- 外部输入安全转换 ----


def _as_int(value: Any, default: int = 0) -> int:
    """把外部输入安全转换为 int，缺失或非法时回退默认值"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    """确保字段是字典，非法值降级为空字典"""
    return value if isinstance(value, dict) else {}


# ---- CQ 码解析 ----
_CQ_PATTERN = re.compile(r"\[CQ:([a-zA-Z0-9_]+)((?:,[^,\]]*)?)\]")


def _cq_unescape(text: str) -> str:
    return (
        text.replace("&#91;", "[")
        .replace("&#93;", "]")
        .replace("&#44;", ",")
        .replace("&amp;", "&")
    )


def _parse_cq_string(raw: str) -> list[MessageSegmentData] | None:
    """把 CQ 码字符串转换为消息段数组；不含 CQ 码时返回 None"""
    if "[CQ:" not in raw:
        return None

    segments: list[MessageSegmentData] = []
    pos = 0
    for match in _CQ_PATTERN.finditer(raw):
        if match.start() > pos:
            text = _cq_unescape(raw[pos:match.start()])
            if text:
                segments.append({"type": "text", "data": {"text": text}})

        data: dict[str, Any] = {}
        for part in match.group(2).split(",")[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                data[key] = _cq_unescape(value)
        segments.append({"type": match.group(1), "data": data})
        pos = match.end()

    if pos < len(raw):
        text = _cq_unescape(raw[pos:])
        if text:
            segments.append({"type": "text", "data": {"text": text}})
    return segments


# ---- 消息解析缓存 ----
# 同一条消息在不同事件中会被反复解析（如撤回、引用、历史消息），
# 以 raw_message（CQ 码）为键缓存解析结果，命中时直接复制，避免逐段解析。
_MESSAGE_CACHE: dict[str, Message] = {}
_MESSAGE_CACHE_MAXSIZE: int = 512


@dataclass
class Message:
    """消息内容"""
    plain_text: str = ""
    raw_message: str = ""
    segments: list[MessageSegmentData] = field(default_factory=list)
    face_ids: list[int] = field(default_factory=list)        # 表情 ID 列表
    face_names: list[str] = field(default_factory=list)      # 表情名称列表
    has_dice: bool = False                                    # 是否含骰子
    has_rps: bool = False                                     # 是否含猜拳
    has_poke: bool = False                                    # 是否含戳一戳
    has_sticker: bool = False                                 # 是否含收藏表情包
    at_user_ids: list[int] = field(default_factory=list)     # 被 @ 的用户列表
    has_reply: bool = False                                   # 是否含回复消息
    reply_message_id: int = 0                                 # 回复的消息 ID
    has_image: bool = False                                   # 是否含图片
    has_video: bool = False                                   # 是否含视频
    has_record: bool = False                                  # 是否含语音
    has_file: bool = False                                    # 是否含文件
    has_forward: bool = False                                 # 是否含合并转发
    has_music: bool = False                                   # 是否含音乐卡片
    has_json: bool = False                                    # 是否含 JSON 卡片
    has_xml: bool = False                                     # 是否含 XML
    has_markdown: bool = False                                # 是否含 Markdown

    @classmethod
    def _copy_from(cls, other: Message) -> Self:
        """从缓存中的 Message 生成独立副本

        缓存对象会被多个事件共享，复制可变字段（列表）可避免某个处理器
        修改 segments / at_user_ids 时污染后续事件。
        """
        return cls(
            plain_text=other.plain_text,
            raw_message=other.raw_message,
            segments=list(other.segments),
            face_ids=list(other.face_ids),
            face_names=list(other.face_names),
            has_dice=other.has_dice,
            has_rps=other.has_rps,
            has_poke=other.has_poke,
            has_sticker=other.has_sticker,
            at_user_ids=list(other.at_user_ids),
            has_reply=other.has_reply,
            reply_message_id=other.reply_message_id,
            has_image=other.has_image,
            has_video=other.has_video,
            has_record=other.has_record,
            has_file=other.has_file,
            has_forward=other.has_forward,
            has_music=other.has_music,
            has_json=other.has_json,
            has_xml=other.has_xml,
            has_markdown=other.has_markdown,
        )

    @classmethod
    def from_raw(cls, value: Any, raw_message: str = "") -> Self:
        """解析消息（带 LRU 缓存）

        仅当消息为数组格式且提供 raw_message 时走缓存；其余情况直接解析。
        """
        cache_key: str | None = None
        if raw_message and isinstance(value, list):
            try:
                fingerprint = hashlib.sha256(
                    json.dumps(
                        value, sort_keys=True, ensure_ascii=False, default=str
                    ).encode("utf-8")
                ).hexdigest()
            except (TypeError, ValueError):
                fingerprint = ""
            if fingerprint:
                # raw_message 可能重复（如相同文本），拼上结构指纹避免串消息
                cache_key = f"{raw_message}\x00{fingerprint}"

        if cache_key is not None:
            cached = _MESSAGE_CACHE.get(cache_key)
            if cached is not None:
                # 命中后移至末尾，实现 LRU 语义
                _MESSAGE_CACHE.pop(cache_key)
                _MESSAGE_CACHE[cache_key] = cached
                return cls._copy_from(cached)

        message = cls._parse(value, raw_message)

        if cache_key is not None:
            if len(_MESSAGE_CACHE) >= _MESSAGE_CACHE_MAXSIZE:
                # 淘汰最久未使用的条目
                _MESSAGE_CACHE.pop(next(iter(_MESSAGE_CACHE)), None)
            # 缓存中存副本，保证调用方拿到的对象不会被缓存复用
            _MESSAGE_CACHE[cache_key] = cls._copy_from(message)

        return message

    @classmethod
    def _parse(cls, value: Any, raw_message: str = "") -> Self:
        if isinstance(value, list):
            text_parts: list[str] = []
            segments: list[MessageSegmentData] = []
            face_ids: list[int] = []
            face_names: list[str] = []
            at_user_ids: list[int] = []
            has_sticker = False
            has_reply = False
            reply_message_id = 0
            has_image = False
            has_video = False
            has_record = False
            has_file = False
            has_forward = False
            has_music = False
            has_json = False
            has_xml = False
            has_markdown = False

            for item in value:
                if not isinstance(item, dict):
                    text_parts.append(str(item))
                    continue

                segments.append(item)
                seg_type = item.get("type", "")
                seg_data = item.get("data", {})
                if not isinstance(seg_data, dict):
                    # 部分实现会下发 "data": null 等非法值，降级为空数据而非丢弃整条消息
                    seg_data = {}

                # 单个畸形/异常段不得让整条消息消失：逐段容错，失败仅跳过该段的解析
                try:
                    if seg_type == "text":
                        text_parts.append(str(seg_data.get("text", "")))
                    elif seg_type == "face":
                        face_id = _as_int(seg_data.get("id", 0))
                        name = get_face_name(face_id)
                        face_ids.append(face_id)
                        face_names.append(name)
                        text_parts.append(f"[表情:{name}]")
                    elif seg_type == "dice":
                        text_parts.append("[骰子]")
                    elif seg_type == "rps":
                        text_parts.append("[猜拳]")
                    elif seg_type == "poke":
                        text_parts.append("[戳一戳]")
                    elif seg_type == "image":
                        sub_type = _as_int(seg_data.get("sub_type") or 0)
                        has_image = True
                        if sub_type == 1:
                            has_sticker = True
                            summary = seg_data.get("summary") or "表情包"
                            text_parts.append(f"[表情包:{summary}]")
                        else:
                            file_name = seg_data.get("file", "图片")
                            text_parts.append(f"[图片:{file_name}]")
                    elif seg_type == "at":
                        qq = seg_data.get("qq", 0)
                        if str(qq) == "all":
                            # @全体成员：不是某个用户 ID，仅渲染，不加入 at_user_ids
                            text_parts.append("[CQ:at,qq=all]")
                        else:
                            at_id = _as_int(qq)
                            at_user_ids.append(at_id)
                            text_parts.append(f"[CQ:at,qq={at_id}]")
                    elif seg_type == "reply":
                        has_reply = True
                        reply_message_id = _as_int(seg_data.get("id", 0))
                        text_parts.append(f"[回复:{reply_message_id}]")
                    elif seg_type == "video":
                        has_video = True
                        file_name = seg_data.get("file", "视频")
                        text_parts.append(f"[视频:{file_name}]")
                    elif seg_type == "record":
                        has_record = True
                        text_parts.append("[语音]")
                    elif seg_type == "file":
                        has_file = True
                        file_name = seg_data.get("file_name") or seg_data.get("file", "文件")
                        text_parts.append(f"[文件:{file_name}]")
                    elif seg_type == "forward":
                        has_forward = True
                        text_parts.append("[合并转发]")
                    elif seg_type == "node":
                        has_forward = True
                        name = seg_data.get("name", "未知")
                        text_parts.append(f"[转发节点:{name}]")
                    elif seg_type == "music":
                        has_music = True
                        title = seg_data.get("title", "音乐")
                        text_parts.append(f"[音乐:{title}]")
                    elif seg_type == "json":
                        has_json = True
                        text_parts.append("[JSON卡片]")
                    elif seg_type == "xml":
                        has_xml = True
                        text_parts.append("[XML消息]")
                    elif seg_type == "markdown":
                        has_markdown = True
                        text_parts.append("[Markdown]")
                except Exception as e:
                    logger.warning(f"解析消息段失败，已跳过该段 [{seg_type}]: {e}", exc_info=True)

            plain_text = "".join(text_parts)
            return cls(
                plain_text=plain_text,
                raw_message=raw_message or plain_text,
                segments=segments,
                face_ids=face_ids,
                face_names=face_names,
                at_user_ids=at_user_ids,
                has_dice="[骰子]" in plain_text,
                has_rps="[猜拳]" in plain_text,
                has_poke="[戳一戳]" in plain_text,
                has_sticker=has_sticker,
                has_reply=has_reply,
                reply_message_id=reply_message_id,
                has_image=has_image,
                has_video=has_video,
                has_record=has_record,
                has_file=has_file,
                has_forward=has_forward,
                has_music=has_music,
                has_json=has_json,
                has_xml=has_xml,
                has_markdown=has_markdown,
            )

        text = str(value or raw_message or "")
        cq_segments = _parse_cq_string(text)
        if cq_segments:
            return cls._parse(cq_segments, raw_message or text)
        return cls(plain_text=text, raw_message=raw_message or text)

    def get_plain_text(self) -> str:
        """获取纯文本消息"""
        return self.plain_text or self.raw_message


@dataclass
class BaseEvent:
    """基础事件类 —— 所有事件的公共字段"""
    time: int = 0
    self_id: int = 0
    post_type: str = ""

    @classmethod
    def from_dict(cls, data: EventData) -> Self:
        """从字典创建事件实例

        Args:
            data: 事件原始数据字典

        Returns:
            事件实例
        """
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class GroupMessageEvent(BaseEvent):
    """群消息事件"""
    message_type: str = "group"
    sub_type: str = ""
    message_id: int = 0
    group_id: int = 0
    user_id: int = 0
    user_name: str = ""
    message: Message = field(default_factory=Message)
    raw_message: str = ""
    font: int = 0
    sender: SenderInfo = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: EventData) -> Self:
        """从字典创建群消息事件实例

        Args:
            data: 事件原始数据字典

        Returns:
            GroupMessageEvent 实例
        """
        raw_message: str = str(data.get("raw_message", ""))
        msg = Message.from_raw(data.get("message", raw_message), raw_message)

        snd: SenderInfo = _as_dict(data.get("sender"))
        uname: str = str(snd.get("card", "") or snd.get("nickname", ""))

        return cls(
            time=_as_int(data.get("time")),
            self_id=_as_int(data.get("self_id")),
            post_type=str(data.get("post_type", "message")),
            message_type=str(data.get("message_type", "group")),
            sub_type=str(data.get("sub_type", "")),
            message_id=_as_int(data.get("message_id")),
            group_id=_as_int(data.get("group_id")),
            user_id=_as_int(data.get("user_id")),
            user_name=uname,
            message=msg,
            raw_message=str(data.get("raw_message", "")),
            font=_as_int(data.get("font")),
            sender=snd,
        )


@dataclass
class PrivateMessageEvent(BaseEvent):
    """私聊消息事件"""
    message_type: str = "private"
    sub_type: str = ""
    message_id: int = 0
    user_id: int = 0
    user_name: str = ""
    message: Message = field(default_factory=Message)
    raw_message: str = ""
    font: int = 0

    @classmethod
    def from_dict(cls, data: EventData) -> Self:
        """从字典创建私聊消息事件实例

        Args:
            data: 事件原始数据字典

        Returns:
            PrivateMessageEvent 实例
        """
        raw_message: str = str(data.get("raw_message", ""))
        msg = Message.from_raw(data.get("message", raw_message), raw_message)

        snd: SenderInfo = _as_dict(data.get("sender"))
        uname: str = str(
            data.get("user_name", "")
            or snd.get("card", "")
            or snd.get("nickname", "")
        )

        return cls(
            time=_as_int(data.get("time")),
            self_id=_as_int(data.get("self_id")),
            post_type=str(data.get("post_type", "message")),
            message_type=str(data.get("message_type", "private")),
            sub_type=str(data.get("sub_type", "")),
            message_id=_as_int(data.get("message_id")),
            user_id=_as_int(data.get("user_id")),
            user_name=uname,
            message=msg,
            raw_message=str(data.get("raw_message", "")),
            font=_as_int(data.get("font")),
        )


@dataclass
class NoticeEvent(BaseEvent):
    """通知事件基类"""
    notice_type: str = ""
    user_id: int = 0
    group_id: int = 0

    @classmethod
    def from_dict(cls, data: EventData) -> NoticeEvent:
        notice_type = str(data.get("notice_type", ""))
        raw_subtype = str(data.get("sub_type", ""))
        _map: dict[str, type[NoticeEvent]] = {
            "group_increase": GroupIncreaseNotice,
            "group_decrease": GroupDecreaseNotice,
            "group_ban":      GroupBanNotice,
            "group_recall":   GroupRecallNotice,
            "friend_recall":  FriendRecallNotice,
            "group_admin":    GroupAdminNotice,
            "group_upload":   GroupUploadNotice,
            "group_card":     GroupCardNotice,
            "friend_add":     FriendAddNotice,
            "essence_msg":    EssenceMsgNotice,
        }
        if notice_type == "notify" and raw_subtype == "poke":
            target: type[NoticeEvent] = PokeNotice
        else:
            target = _map.get(notice_type, NoticeEvent)
        return target._build(data)

    @classmethod
    def _build(cls, data: EventData) -> Self:
        return cls(
            time=_as_int(data.get("time")),
            self_id=_as_int(data.get("self_id")),
            post_type=str(data.get("post_type", "notice")),
            notice_type=str(data.get("notice_type", "")),
            user_id=_as_int(data.get("user_id")),
            group_id=_as_int(data.get("group_id")),
        )


@dataclass
class GroupIncreaseNotice(NoticeEvent):
    """群成员增加"""
    notice_type: str = "group_increase"
    sub_type: str = ""
    operator_id: int = 0

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            sub_type=str(data.get("sub_type", "")),
            operator_id=_as_int(data.get("operator_id")),
        )


@dataclass
class GroupDecreaseNotice(NoticeEvent):
    """群成员减少"""
    notice_type: str = "group_decrease"
    sub_type: str = ""
    operator_id: int = 0

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            sub_type=str(data.get("sub_type", "")),
            operator_id=_as_int(data.get("operator_id")),
        )


@dataclass
class GroupBanNotice(NoticeEvent):
    """群禁言"""
    notice_type: str = "group_ban"
    sub_type: str = ""
    operator_id: int = 0
    duration: int = 0

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            sub_type=str(data.get("sub_type", "")),
            operator_id=_as_int(data.get("operator_id")),
            duration=_as_int(data.get("duration")),
        )


@dataclass
class GroupRecallNotice(NoticeEvent):
    """群消息撤回"""
    notice_type: str = "group_recall"
    operator_id: int = 0
    message_id: int = 0

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            operator_id=_as_int(data.get("operator_id")),
            message_id=_as_int(data.get("message_id")),
        )


@dataclass
class FriendRecallNotice(NoticeEvent):
    """好友消息撤回"""
    notice_type: str = "friend_recall"
    message_id: int = 0

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            message_id=_as_int(data.get("message_id")),
        )


@dataclass
class PokeNotice(NoticeEvent):
    """戳一戳通知"""
    notice_type: str = "notify"
    target_id: int = 0

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            target_id=_as_int(data.get("target_id")),
        )


@dataclass
class GroupAdminNotice(NoticeEvent):
    """群管理员变更"""
    notice_type: str = "group_admin"
    sub_type: str = ""

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            sub_type=str(data.get("sub_type", "")),
        )


@dataclass
class GroupUploadNotice(NoticeEvent):
    """群文件上传"""
    notice_type: str = "group_upload"
    file: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            file=data.get("file", {}),
        )


@dataclass
class GroupCardNotice(NoticeEvent):
    """群成员名片修改"""
    notice_type: str = "group_card"
    card_new: str = ""
    card_old: str = ""

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            card_new=str(data.get("card_new", "")),
            card_old=str(data.get("card_old", "")),
        )


@dataclass
class FriendAddNotice(NoticeEvent):
    """好友添加"""
    notice_type: str = "friend_add"

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(**{k: v for k, v in base.__dict__.items()})


@dataclass
class EssenceMsgNotice(NoticeEvent):
    """精华消息变更"""
    notice_type: str = "essence_msg"
    sub_type: str = ""
    message_id: int = 0

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = NoticeEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            sub_type=str(data.get("sub_type", "")),
            message_id=_as_int(data.get("message_id")),
        )


@dataclass
class MetaEvent(BaseEvent):
    """元事件基类（心跳、生命周期等）"""

    meta_event_type: str = ""
    sub_type: str = ""

    @classmethod
    def from_dict(cls, data: EventData) -> MetaEvent:
        meta_event_type = str(data.get("meta_event_type", ""))
        _map: dict[str, type[MetaEvent]] = {
            "heartbeat": HeartbeatEvent,
            "lifecycle": LifecycleEvent,
        }
        target: type[MetaEvent] = _map.get(meta_event_type, MetaEvent)
        return target._build(data)

    @classmethod
    def _build(cls, data: EventData) -> Self:
        return cls(
            time=_as_int(data.get("time")),
            self_id=_as_int(data.get("self_id")),
            post_type=str(data.get("post_type", "meta_event")),
            meta_event_type=str(data.get("meta_event_type", "")),
            sub_type=str(data.get("sub_type", "")),
        )


@dataclass
class HeartbeatEvent(MetaEvent):
    """心跳事件"""

    meta_event_type: str = "heartbeat"
    status: dict[str, Any] = field(default_factory=dict)
    interval: int = 0

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = MetaEvent._build(data)
        status = _as_dict(data.get("status"))
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            status=status,
            interval=_as_int(data.get("interval") or status.get("interval")),
        )


@dataclass
class LifecycleEvent(MetaEvent):
    """生命周期事件（连接建立 / 启用 / 禁用）"""

    meta_event_type: str = "lifecycle"
    sub_type: str = ""

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = MetaEvent._build(data)
        return cls(**{k: v for k, v in base.__dict__.items()})


@dataclass
class RequestEvent(BaseEvent):
    """请求事件基类（好友申请、群邀请等）"""
    request_type: str = ""
    user_id: int = 0
    comment: str = ""
    flag: str = ""

    @classmethod
    def from_dict(cls, data: EventData) -> RequestEvent:
        request_type = str(data.get("request_type", ""))
        _map: dict[str, type[RequestEvent]] = {
            "friend": FriendRequestEvent,
            "group":  GroupRequestEvent,
        }
        target: type[RequestEvent] = _map.get(request_type, RequestEvent)
        return target._build(data)

    @classmethod
    def _build(cls, data: EventData) -> Self:
        return cls(
            time=_as_int(data.get("time")),
            self_id=_as_int(data.get("self_id")),
            post_type=str(data.get("post_type", "request")),
            request_type=str(data.get("request_type", "")),
            user_id=_as_int(data.get("user_id")),
            comment=str(data.get("comment", "")),
            flag=str(data.get("flag", "")),
        )


@dataclass
class FriendRequestEvent(RequestEvent):
    """好友申请"""
    request_type: str = "friend"

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = RequestEvent._build(data)
        return cls(**{k: v for k, v in base.__dict__.items()})


@dataclass
class GroupRequestEvent(RequestEvent):
    """群邀请 / 加群申请"""
    request_type: str = "group"
    group_id: int = 0
    sub_type: str = ""

    @classmethod
    def _build(cls, data: EventData) -> Self:
        base = RequestEvent._build(data)
        return cls(
            **{k: v for k, v in base.__dict__.items()},
            group_id=_as_int(data.get("group_id")),
            sub_type=str(data.get("sub_type", "")),
        )
