# ==================== 系统必要导入 ====================
from __future__ import annotations

import logging
import os
from pathlib import Path

from sdk.core.events import GroupMessageEvent, PrivateMessageEvent
from sdk.pluginsystem import PluginBase, filter_registry

# ==================== 功能自主导入 ====================
from . import game

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
        self.config = {}
        
        # 关键词优先级：高优先级在前
        self.rank_keywords = ["排行榜", "榜单", "排名"]
        self.stats_keywords = ["统计", "数据", "修为", "境界", "等级"]
        self.cultivate_keywords = ["开灵", "打坐", "突破", "修炼", "修行", "修仙"]
        self.help_keywords = ["帮助", "使用说明", "功能"]
        
    # ==================== 必要加载函数 ====================
    async def on_load(self, api, event_bus, plugin_dir=None):
        """插件加载时调用"""
        await super().on_load(api, event_bus, plugin_dir)
        logger.info(f"已加载, v{self.version}")
        
        self.config = await self.load_config()
        logger.info(f"配置已加载: {self.config}")
        
        os.makedirs(DATA_DIR, exist_ok=True)
        
    async def on_unload(self):
        """插件卸载时调用"""
        logger.info(f"卸载中")
        
    # ==================== 其他功能函数 ====================
        
    @filter_registry.group_server
    async def rqhbase_group(self, event: GroupMessageEvent):
        raw_message = event.message.plain_text.strip()
        text = raw_message

        # 帮助
        if any(kw in text for kw in self.help_keywords) and "帮助" in text:
            await self.reply_with_event(event, self._get_help_text())
            return

        # 排行榜
        if any(kw in text for kw in self.rank_keywords) and ("排行榜" in text or "榜单" in text):
            try:
                result = self.cultivation_system.get_ranking(10)
                await self.reply_with_event(event, result)
            except Exception as e:
                await self.reply_with_event(event, f"查询排行榜失败: {e}")
            return

        # 统计
        if any(kw in text for kw in self.stats_keywords) and ("统计" in text or "数据" in text):
            try:
                user_id = event.user_id
                username = str(user_id)
                player = self.cultivation_system.load_player(user_id, username)
                msg = (
                    f"📊 修仙统计\n\n"
                    f"👤 用户: {username}\n"
                    f"境界: {player.current_realm_name}\n"
                    f"当前修为: {player.exp}\n"
                    f"下境界所需: {player.next_threshold if player.next_threshold != float('inf') else 'MAX'}\n"
                    f"总突破次数: {player.total_breakthroughs}\n"
                    f"总获得修为: {player.total_exp_gained}"
                )
                await self.reply_with_event(event, msg)
            except Exception as e:
                await self.reply_with_event(event, f"查询统计失败: {e}")
            return

        # 修炼
        if not any(kw in text for kw in self.cultivate_keywords):
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
                msg = (
                    f"✨ 修炼状态\n\n"
                    f"👤 用户: {username}\n"
                    f"境界: {player.current_realm_name}\n"
                    f"修为: {player.exp}/{player.next_threshold if player.next_threshold != float('inf') else 'MAX'}\n"
                    f"总突破: {player.total_breakthroughs} 次\n"
                    f"总修为: {player.total_exp_gained}"
                )
                await self.reply_with_event(event, msg)
        except Exception as e:
            logger.error(f"修炼处理失败: {e}", exc_info=True)
            await self.reply_with_event(event, f"操作失败: {e}")
                    
    @filter_registry.private_server
    async def rqhbase_private(self, event: PrivateMessageEvent):
        raw_message = event.message.plain_text.strip()
        text = raw_message

        if any(kw in text for kw in self.help_keywords) and "帮助" in text:
            await self.reply_with_event(event, self._get_help_text())
            return

        if any(kw in text for kw in self.rank_keywords) and ("排行榜" in text or "榜单" in text):
            try:
                result = self.cultivation_system.get_ranking(10)
                await self.reply_with_event(event, result)
            except Exception as e:
                await self.reply_with_event(event, f"查询排行榜失败: {e}")
            return

        if any(kw in text for kw in self.stats_keywords) and ("统计" in text or "数据" in text):
            try:
                user_id = event.user_id
                username = str(user_id)
                player = self.cultivation_system.load_player(user_id, username)
                msg = (
                    f"📊 修仙统计\n\n"
                    f"👤 用户: {username}\n"
                    f"境界: {player.current_realm_name}\n"
                    f"当前修为: {player.exp}\n"
                    f"下境界所需: {player.next_threshold if player.next_threshold != float('inf') else 'MAX'}\n"
                    f"总突破次数: {player.total_breakthroughs}\n"
                    f"总获得修为: {player.total_exp_gained}"
                )
                await self.reply_with_event(event, msg)
            except Exception as e:
                await self.reply_with_event(event, f"查询统计失败: {e}")
            return

        if not any(kw in text for kw in self.cultivate_keywords):
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
                msg = (
                    f"✨ 修炼状态\n\n"
                    f"👤 用户: {username}\n"
                    f"境界: {player.current_realm_name}\n"
                    f"修为: {player.exp}/{player.next_threshold if player.next_threshold != float('inf') else 'MAX'}\n"
                    f"总突破: {player.total_breakthroughs} 次\n"
                    f"总修为: {player.total_exp_gained}"
                )
                await self.reply_with_event(event, msg)
        except Exception as e:
            logger.error(f"修炼处理失败: {e}", exc_info=True)
            await self.reply_with_event(event, f"操作失败: {e}")

    def _get_help_text(self) -> str:
        return """📜 修仙插件帮助

✨ 修仙功能
- 开灵 - 踏入仙途，开始修仙
- 打坐 - 闭目修炼，增加修为
- 突破 - 尝试突破境界
- 修炼 - 查看修炼状态

🏆 排行榜功能
- 排行榜 - 查看修仙排行榜
- 榜单 - 查看修仙榜单

📊 统计功能
- 统计 - 查看您的修仙统计
- 数据 - 查看修仙数据
- 境界 - 查看当前境界
- 修为 - 查看当前修为

使用方法：直接发送对应关键词即可
"""