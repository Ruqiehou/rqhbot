"""测试配置"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_api() -> MagicMock:
    """模拟 NapCatClient"""
    api = MagicMock()
    api.send_group_message = AsyncMock(return_value={"status": "ok"})
    api.send_private_message = AsyncMock(return_value={"status": "ok"})
    api.call = AsyncMock(return_value={"status": "ok", "data": {}})
    return api


@pytest.fixture
def sample_group_message_data() -> dict[str, Any]:
    """示例群消息数据"""
    return {
        "time": 1716182400,
        "self_id": 123456,
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": 10001,
        "group_id": 1001,
        "user_id": 2001,
        "message": [
            {"type": "text", "data": {"text": "hello"}},
        ],
        "raw_message": "hello",
        "font": 14,
        "sender": {
            "user_id": 2001,
            "nickname": "TestUser",
            "card": "",
            "role": "member",
        },
    }


@pytest.fixture
def sample_private_message_data() -> dict[str, Any]:
    """示例私聊消息数据"""
    return {
        "time": 1716182400,
        "self_id": 123456,
        "post_type": "message",
        "message_type": "private",
        "sub_type": "friend",
        "message_id": 20001,
        "user_id": 2001,
        "message": [
            {"type": "text", "data": {"text": "hi"}},
        ],
        "raw_message": "hi",
        "font": 14,
        "sender": {
            "user_id": 2001,
            "nickname": "TestUser",
        },
    }
