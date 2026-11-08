"""
消息段构建工具

OneBot 11 的 message 字段支持数组（消息段）格式，这里提供各类型消息段的
构造方法，供发送富文本消息时组合使用。
"""

from __future__ import annotations

import json
from typing import Any

from sdk.core.interfaces import MessageSegmentType


class MessageSegment:
    """消息段构建器 —— 用于构建 OneBot 11 数组格式的消息

    OneBot 11（NapCat / SnowLuma 等）的 message 支持数组格式：
    ```python
    [
        {"type": "text", "data": {"text": "你好，"}},
        {"type": "image", "data": {"file": "https://example.com/pic.png"}},
        {"type": "text", "data": {"text": "这是图片！"}},
    ]
    ```
    """

    @staticmethod
    def text(content: str) -> MessageSegmentType:
        """文字消息段"""
        return {"type": "text", "data": {"text": content}}

    @staticmethod
    def image(file: str, summary: str = "") -> MessageSegmentType:
        """图片消息段
        Args:
            file: 图片路径（本地路径或 URL）
            summary: 图片简介（可选，用于加载失败时显示）
        """
        data: dict[str, Any] = {"file": file}
        if summary:
            data["summary"] = summary
        return {"type": "image", "data": data}

    @staticmethod
    def at(qq: int | str) -> MessageSegmentType:
        """@某人消息段"""
        return {"type": "at", "data": {"qq": str(qq)}}

    @staticmethod
    def reply(message_id: int) -> MessageSegmentType:
        """回复消息段"""
        return {"type": "reply", "data": {"id": message_id}}

    @staticmethod
    def face(face_id: int) -> MessageSegmentType:
        """QQ 表情消息段 (face id)"""
        return {"type": "face", "data": {"id": face_id}}

    @staticmethod
    def dice() -> MessageSegmentType:
        """骰子消息段"""
        return {"type": "dice", "data": {}}

    @staticmethod
    def rps() -> MessageSegmentType:
        """猜拳消息段"""
        return {"type": "rps", "data": {}}

    @staticmethod
    def json_data(data: dict[str, Any] | str) -> MessageSegmentType:
        """JSON 卡片消息段"""
        if isinstance(data, dict):
            data = json.dumps(data, ensure_ascii=False)
        return {"type": "json", "data": {"data": data}}

    @staticmethod
    def video(file: str) -> MessageSegmentType:
        """视频消息段"""
        return {"type": "video", "data": {"file": file}}

    @staticmethod
    def record(file: str, magic: bool = False) -> MessageSegmentType:
        """语音消息段"""
        data: dict[str, Any] = {"file": file}
        if magic:
            data["magic"] = True
        return {"type": "record", "data": data}

    @staticmethod
    def file(file: str, file_name: str = "") -> MessageSegmentType:
        """文件消息段"""
        data: dict[str, Any] = {"file": file}
        if file_name:
            data["file_name"] = file_name
        return {"type": "file", "data": data}

    @staticmethod
    def forward(
        res_id: str = "", news: list[dict[str, Any]] | None = None
    ) -> MessageSegmentType:
        """合并转发消息段"""
        data: dict[str, Any] = {}
        if res_id:
            data["id"] = res_id
        if news:
            data["news"] = news
        return {"type": "forward", "data": data}

    @staticmethod
    def node(name: str, uin: int, content: list[MessageSegmentType]) -> MessageSegmentType:
        """合并转发节点"""
        return {
            "type": "node",
            "data": {
                "name": name,
                "uin": str(uin),
                "content": content,
            },
        }

    @staticmethod
    def music(
        type_: str,
        id_: str = "",
        url: str = "",
        title: str = "",
        content: str = "",
        image: str = "",
    ) -> MessageSegmentType:
        """音乐卡片消息段

        Args:
            type_: 平台类型（qq / 163 / kugou / mfeel / bilibili）
            id_: 音乐平台的歌曲 ID
            url: 点击后跳转的链接
            title: 标题
            content: 简介
            image: 封面图
        """
        data: dict[str, Any] = {"type": type_}
        if id_:
            data["id"] = id_
        if url:
            data["url"] = url
        if title:
            data["title"] = title
        if content:
            data["content"] = content
        if image:
            data["image"] = image
        return {"type": "music", "data": data}

    @staticmethod
    def markdown(content: str) -> MessageSegmentType:
        """Markdown 消息段"""
        return {"type": "markdown", "data": {"content": content}}

    @staticmethod
    def mface(emoji_id: str, emoji_type: int = 0) -> MessageSegmentType:
        """表情商店表情消息段"""
        data: dict[str, Any] = {"emoji_id": emoji_id}
        if emoji_type:
            data["emoji_type"] = emoji_type
        return {"type": "mface", "data": data}

    @staticmethod
    def xml(data: str) -> MessageSegmentType:
        """XML 消息段"""
        return {"type": "xml", "data": {"data": data}}


__all__: list[str] = ["MessageSegment"]
