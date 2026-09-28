"""Message.from_raw 解析的回归测试

覆盖以下已确认缺陷：
- @全体成员 段（``{"type": "at", "data": {"qq": "all"}}``）导致 ``int("all")`` 抛 ValueError，
  整条消息被丢弃。
- ``"data": null`` 段导致 AttributeError，整条消息被丢弃。
- image 段的 ``sub_type: null`` 导致 TypeError，整条消息被丢弃。

核心保证：单个异常/畸形段永远不能让整条消息消失。
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from sdk.core.events import GroupMessageEvent, Message


def _text(segments: List[Dict[str, Any]]) -> str:
    return Message.from_raw(segments).plain_text


class TestAtAll:
    """@全体成员 段"""

    def test_at_all_does_not_raise(self) -> None:
        """at-all 段不应抛异常"""
        msg = Message.from_raw([{"type": "at", "data": {"qq": "all"}}])
        assert msg.plain_text != ""

    def test_at_all_rendered_and_not_a_user_id(self) -> None:
        """at-all 应被渲染，但不是某个用户 ID"""
        msg = Message.from_raw([{"type": "at", "data": {"qq": "all"}}])
        assert "[CQ:at,qq=all]" in msg.plain_text
        assert msg.at_user_ids == []

    def test_at_all_does_not_drop_surrounding_text(self) -> None:
        """含 at-all 的消息，其余内容必须保留"""
        segments = [
            {"type": "text", "data": {"text": "重要通知"}},
            {"type": "at", "data": {"qq": "all"}},
            {"type": "text", "data": {"text": " 请查收"}},
        ]
        msg = Message.from_raw(segments)
        assert msg.plain_text == "重要通知[CQ:at,qq=all] 请查收"
        assert msg.at_user_ids == []
        assert len(msg.segments) == 3

    def test_normal_at_format_unchanged(self) -> None:
        """普通 at 段的 plain_text 格式保持不变（插件依赖该格式）"""
        msg = Message.from_raw([{"type": "at", "data": {"qq": 12345}}])
        assert "[CQ:at,qq=12345]" in msg.plain_text
        assert msg.at_user_ids == [12345]

    def test_mixed_at_all_and_normal_at(self) -> None:
        """at-all 与普通 at 混合"""
        segments = [
            {"type": "at", "data": {"qq": "all"}},
            {"type": "at", "data": {"qq": "67890"}},
        ]
        msg = Message.from_raw(segments)
        assert "[CQ:at,qq=all]" in msg.plain_text
        assert "[CQ:at,qq=67890]" in msg.plain_text
        assert msg.at_user_ids == [67890]

    def test_string_numeric_at(self) -> None:
        """字符串形式的普通 at（OneBot 常以字符串下发）"""
        msg = Message.from_raw([{"type": "at", "data": {"qq": "13579"}}])
        assert msg.at_user_ids == [13579]
        assert "[CQ:at,qq=13579]" in msg.plain_text


class TestGroupMessageEventAtAll:
    """端到端：GroupMessageEvent.from_dict 不应吞掉含 at-all 的群消息"""

    def test_from_dict_with_at_all(self) -> None:
        data = {
            "time": 1716182400,
            "self_id": 123456,
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "message_id": 10001,
            "group_id": 1001,
            "user_id": 2001,
            "message": [
                {"type": "at", "data": {"qq": "all"}},
                {"type": "text", "data": {"text": "全体禁言"}},
            ],
            "raw_message": "[CQ:at,qq=all]全体禁言",
            "sender": {"user_id": 2001, "nickname": "TestUser", "card": ""},
        }
        event = GroupMessageEvent.from_dict(data)
        assert event.group_id == 1001
        assert event.user_id == 2001
        assert "全体禁言" in event.message.plain_text
        assert event.message.at_user_ids == []


class TestMalformedSegments:
    """畸形段不得丢弃整条消息"""

    def test_null_data_segment(self) -> None:
        """data 为 null 的段"""
        segments = [
            {"type": "text", "data": {"text": "before"}},
            {"type": "text", "data": None},
            {"type": "text", "data": {"text": "after"}},
        ]
        msg = Message.from_raw(segments)
        assert msg.plain_text == "beforeafter"

    def test_missing_data_key(self) -> None:
        segments = [
            {"type": "text", "data": {"text": "a"}},
            {"type": "text"},
            {"type": "text", "data": {"text": "b"}},
        ]
        msg = Message.from_raw(segments)
        assert msg.plain_text == "ab"

    def test_image_sub_type_null(self) -> None:
        """image 段的 sub_type 为 null"""
        segments = [
            {"type": "text", "data": {"text": "看"}},
            {"type": "image", "data": {"file": "x.jpg", "sub_type": None}},
            {"type": "text", "data": {"text": "图"}},
        ]
        msg = Message.from_raw(segments)
        assert msg.plain_text == "看[图片:x.jpg]图"
        assert msg.has_image is True

    def test_non_numeric_face_id_does_not_drop_message(self) -> None:
        """face 段的 id 非数字时，其余内容仍然保留"""
        segments = [
            {"type": "text", "data": {"text": "hi"}},
            {"type": "face", "data": {"id": "not-a-number"}},
            {"type": "text", "data": {"text": "there"}},
        ]
        msg = Message.from_raw(segments)
        assert "hi" in msg.plain_text
        assert "there" in msg.plain_text

    def test_unknown_segment_type_does_not_drop_message(self) -> None:
        segments = [
            {"type": "text", "data": {"text": "a"}},
            {"type": "totally-unknown", "data": {"x": 1}},
            {"type": "text", "data": {"text": "b"}},
        ]
        msg = Message.from_raw(segments)
        assert msg.plain_text == "ab"
        assert len(msg.segments) == 3

    def test_null_segment_item(self) -> None:
        msg = Message.from_raw([None, {"type": "text", "data": {"text": "ok"}}])
        assert "ok" in msg.plain_text

    @pytest.mark.parametrize("bad_data", [None, 0, "", [], "not-a-dict"])
    def test_various_bad_data_values(self, bad_data: Any) -> None:
        segments = [
            {"type": "text", "data": {"text": "start"}},
            {"type": "face", "data": bad_data},
            {"type": "text", "data": {"text": "end"}},
        ]
        msg = Message.from_raw(segments)
        assert "start" in msg.plain_text
        assert "end" in msg.plain_text
