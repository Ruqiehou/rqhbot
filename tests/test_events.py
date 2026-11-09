"""事件模型测试"""

from __future__ import annotations

from typing import Any

from sdk.core.events import (
    BaseEvent,
    GroupMessageEvent,
    Message,
    PrivateMessageEvent,
)


class TestMessage:
    """Message 类测试"""

    def test_from_raw_list(self) -> None:
        """测试从消息段列表创建 Message"""
        segments = [
            {"type": "text", "data": {"text": "hello"}},
            {"type": "text", "data": {"text": " world"}},
        ]
        msg = Message.from_raw(segments)
        assert msg.plain_text == "hello world"
        assert len(msg.segments) == 2

    def test_from_raw_string(self) -> None:
        """测试从字符串创建 Message"""
        msg = Message.from_raw("test message")
        assert msg.plain_text == "test message"

    def test_from_raw_empty(self) -> None:
        """测试从空值创建 Message"""
        msg = Message.from_raw(None)
        assert msg.plain_text == ""

    def test_from_raw_with_face(self) -> None:
        """测试包含表情的消息"""
        segments = [
            {"type": "text", "data": {"text": "hi"}},
            {"type": "face", "data": {"id": 14}},
        ]
        msg = Message.from_raw(segments)
        assert len(msg.face_ids) == 1
        assert msg.face_ids[0] == 14

    def test_from_raw_with_image(self) -> None:
        """测试包含图片的消息"""
        segments = [
            {"type": "text", "data": {"text": "look"}},
            {"type": "image", "data": {"file": "test.jpg"}},
        ]
        msg = Message.from_raw(segments)
        assert "[图片:test.jpg]" in msg.plain_text

    def test_from_raw_with_sticker(self) -> None:
        """测试包含表情包的消息"""
        segments = [
            {
                "type": "image",
                "data": {"file": "sticker.png", "sub_type": 1, "summary": "doge"},
            },
        ]
        msg = Message.from_raw(segments)
        assert msg.has_sticker is True
        assert "[表情包:doge]" in msg.plain_text

    def test_get_plain_text(self) -> None:
        """测试获取纯文本"""
        msg = Message(plain_text="hello", raw_message="raw")
        assert msg.get_plain_text() == "hello"

    def test_get_plain_text_fallback(self) -> None:
        """测试纯文本为空时回退到 raw_message"""
        msg = Message(plain_text="", raw_message="raw")
        assert msg.get_plain_text() == "raw"


class TestBaseEvent:
    """BaseEvent 测试"""

    def test_from_dict(self) -> None:
        """测试从字典创建事件"""
        data = {"time": 100, "self_id": 1, "post_type": "message"}
        event = BaseEvent.from_dict(data)
        assert event.time == 100
        assert event.self_id == 1
        assert event.post_type == "message"

    def test_from_dict_extra_keys_ignored(self) -> None:
        """测试忽略未知字段"""
        data = {"time": 100, "unknown_field": "value"}
        event = BaseEvent.from_dict(data)
        assert event.time == 100
        assert not hasattr(event, "unknown_field")


class TestGroupMessageEvent:
    """GroupMessageEvent 测试"""

    def test_from_dict(self, sample_group_message_data: dict[str, Any]) -> None:
        """测试从字典创建群消息事件"""
        event = GroupMessageEvent.from_dict(sample_group_message_data)
        assert event.group_id == 1001
        assert event.user_id == 2001
        assert event.user_name == "TestUser"
        assert event.message.plain_text == "hello"

    def test_from_dict_with_card(self) -> None:
        """测试优先使用 card 作为用户名"""
        data = {
            "group_id": 1001,
            "user_id": 2001,
            "message": "test",
            "sender": {"nickname": "Nick", "card": "CardName"},
        }
        event = GroupMessageEvent.from_dict(data)
        assert event.user_name == "CardName"


class TestPrivateMessageEvent:
    """PrivateMessageEvent 测试"""

    def test_from_dict(self, sample_private_message_data: dict[str, Any]) -> None:
        """测试从字典创建私聊消息事件"""
        event = PrivateMessageEvent.from_dict(sample_private_message_data)
        assert event.user_id == 2001
        assert event.user_name == "TestUser"
        assert event.message.plain_text == "hi"
