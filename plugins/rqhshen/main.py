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
        # 必须调用基类清理：退订 EventBus、取消后台任务、关闭线程池。
        # 否则显式卸载或热重载后，旧实例仍会响应消息，重载后重复回复
        await super().on_unload()

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

        # 排行榜（排行榜 / 榜单 / 排名 / 修仙排行 都要能命中）
        if any(kw in text for kw in RANK_KEYWORDS):
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
            if "飞升" in text:
                player = self.cultivation_system.load_player(user_id, username)
                result = player.attempt_ascension()
                self.cultivation_system.save_player(player)
                await self.reply_with_event(event, result)
            elif "挑战" in text or "攻击" in text:
                await self._handle_battle(event, text)
            elif "开灵" in text:
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

    async def _handle_battle(self, event: Any, text: str) -> None:
        """处理 挑战/攻击 <QQ号或道号>

        先解析目标再校验自身状态：目标不存在时应明确回复"未找到玩家"，
        而不是把未开灵等无关原因抛给玩家。
        """
        raw = text.replace("挑战", " ").replace("攻击", " ")
        tokens = raw.split()
        if not tokens:
            await self.reply_with_event(
                event, "请在指令后跟上对方的 QQ 号或道号，例如：挑战 123456"
            )
            return

        target_ref = tokens[0]
        system = self.cultivation_system

        if target_ref.isdigit():
            target = system.load_player(int(target_ref), target_ref)
        else:
            target = system.find_player_by_username(target_ref)

        if target is None:
            await self.reply_with_event(event, f"未找到玩家：{target_ref}")
            return

        me = system.load_player(event.user_id, str(event.user_id))
        if me.qq_id == target.qq_id:
            await self.reply_with_event(event, "道友不可对自己出手。")
            return

        result = me.attack(target) if "攻击" in text else me.battle(target)

        system.save_player(me)
        system.save_player(target)
        await self.reply_with_event(event, result)
