# ==================== 系统必要导入 ====================
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

from sdk.core.events import GroupMessageEvent
from sdk.pluginsystem import PluginBase, filter_registry

# ==================== 功能自主导入 ====================
from . import game
from .game import (
    RANK_KEYWORDS,
    STATS_KEYWORDS,
    CULTIVATE_KEYWORDS,
    get_help_text,
    build_player_stats_msg,
    build_player_status_msg,
)

logger = logging.getLogger("rqhshen")

DATA_DIR = Path(__file__).parent / "data"


class RqhshenPlugin(PluginBase):
    """Rqhshen修仙插件 - 开灵、打坐、突破、排行榜等功能"""

    def __init__(self):
        super().__init__()
        self.name = "rqhshen"
        self.version = "2.0.0"
        self.cultivation_system = game.CultivationSystem()
        self.allowed_groups = set()
        self.admin_users = set()
        self.config: Dict[str, Any] = {}

    async def on_load(self, api, event_bus, plugin_dir=None):
        await super().on_load(api, event_bus, plugin_dir)
        logger.info(f"已加载, v{self.version}")
        self.config = await self.load_config()
        os.makedirs(DATA_DIR, exist_ok=True)

    async def on_unload(self):
        logger.info("卸载中")

    # ==================== 统一消息入口 ====================

    @filter_registry.group_server
    async def rqhbase_group(self, event: GroupMessageEvent):
        await self._route(event, event.message.plain_text.strip())

    async def _route(self, event: Any, text: str) -> None:
        """统一路由 —— 减少群/私聊重复代码"""
        # 帮助
        if any(kw in text for kw in ["帮助"]) and "帮助" in text:
            await self.reply_with_event(event, get_help_text())
            return

        # 排行榜
        if any(kw in text for kw in RANK_KEYWORDS) and ("排行榜" in text or "榜单" in text):
            try:
                result = self.cultivation_system.get_ranking(10)
                await self.reply_with_event(event, result)
            except Exception as e:
                await self.reply_with_event(event, f"查询排行榜失败: {e}")
            return

        # 统计
        if any(kw in text for kw in STATS_KEYWORDS) and ("统计" in text or "数据" in text):
            try:
                player = self.cultivation_system.load_player(event.user_id, str(event.user_id))
                await self.reply_with_event(event, build_player_stats_msg(player))
            except Exception as e:
                await self.reply_with_event(event, f"查询统计失败: {e}")
            return

        # 修炼
        if not any(kw in text for kw in CULTIVATE_KEYWORDS):
            return

        user_id = event.user_id
        username = str(user_id)

        try:
            if "开灵" in text:
                player = self.cultivation_system.load_player(user_id, username)
                result = player.open_soul()
                self.cultivation_system.save_player(player)
                await self.reply_with_event(event, result)
            elif "打坐" in text:
                player = self.cultivation_system.load_player(user_id, username)
                result = player.meditate()
                self.cultivation_system.save_player(player)
                await self.reply_with_event(event, result)
            elif "突破" in text:
                player = self.cultivation_system.load_player(user_id, username)
                result = player.attempt_breakthrough()
                self.cultivation_system.save_player(player)
                await self.reply_with_event(event, result)
            elif "修炼" in text or "修行" in text or "修仙" in text:
                player = self.cultivation_system.load_player(user_id, username)
                await self.reply_with_event(event, build_player_status_msg(player))
        except Exception as e:
            logger.error(f"修炼处理失败: {e}", exc_info=True)
            await self.reply_with_event(event, f"操作失败: {e}")
