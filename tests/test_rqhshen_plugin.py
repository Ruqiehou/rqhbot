from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from plugins.rqhshen.game import build_player_stats_msg, build_player_status_msg, get_help_text
from plugins.rqhshen.main import RqhshenPlugin
from sdk.core.events import GroupMessageEvent, Message


class DummyPlayer:
    username = "12345"
    current_realm_name = "练气期"
    exp = 10
    next_threshold = 100
    total_breakthroughs = 1
    total_exp_gained = 20


def test_rqhshen_has_no_private_handler() -> None:
    plugin = RqhshenPlugin()

    assert len(plugin._message_handlers["private"]) == 0
    assert len(plugin._message_handlers["group"]) == 1


def test_rqhshen_text_builders() -> None:
    player = DummyPlayer()

    assert "修仙插件帮助" in get_help_text()
    assert "修仙统计" in build_player_stats_msg(player)
    assert "修炼状态" in build_player_status_msg(player)


@pytest.mark.asyncio
async def test_rqhshen_group_help_route() -> None:
    plugin = RqhshenPlugin()
    plugin.api = MagicMock()
    plugin.api.send_group_message = AsyncMock()

    event = GroupMessageEvent(
        group_id=1001,
        user_id=12345,
        message=Message(plain_text="帮助"),
    )

    await plugin.rqhbase_group(event)

    plugin.api.send_group_message.assert_awaited_once()
    args, kwargs = plugin.api.send_group_message.await_args
    assert args[0] == 1001
    assert "修仙插件帮助" in args[1]
