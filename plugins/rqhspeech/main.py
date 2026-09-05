"""
RqhSpeech 发言统计插件 - SDK 对接层

只负责 SDK 生命周期和消息路由，核心逻辑在 command_handler.py
"""

from __future__ import annotations

import logging
from datetime import datetime

from sdk.core.events import GroupMessageEvent, PrivateMessageEvent
from sdk.pluginsystem import PluginBase, filter_registry

from .data_manager import (
    user_manager,
    log_manager,
    save_user_data,
    user_exists,
    check_and_handle_week_transition,
)
from .speech_config import SpeechConfig
from .command_handler import CommandHandler

logger = logging.getLogger("rqhspeech")


class RqhSpeechPlugin(PluginBase):
    """RqhSpeech 发言统计插件 - 发言日榜、周榜、月榜、用户统计等功能"""

    def __init__(self) -> None:
        super().__init__()
        self.name = "rqhspeech"
        self.version = "5.0.0"
        self.cmd_handler: CommandHandler = None  # type: ignore

    async def on_load(self, api, event_bus, plugin_dir=None) -> None:
        await super().on_load(api, event_bus, plugin_dir)
        # 初始化命令处理器
        self.cmd_handler = CommandHandler(self.reply_with_event)
        logger.info(f"已加载 (v{self.version})")

    async def on_unload(self) -> None:
        await super().on_unload()
        logger.info("卸载中")

    # ==================== 消息处理 ====================

    @filter_registry.group_server
    async def rqhbase_group(self, event: GroupMessageEvent) -> None:
        """处理群消息"""
        text = event.message.plain_text.strip()
        group_id = str(event.group_id)
        user_id = str(event.user_id)
        username = event.user_name or str(user_id)

        # 白名单检查
        if not SpeechConfig.is_allowed_group(group_id):
            return

        # 自动注册
        if not user_exists(user_id):
            user_data = user_manager.create_user(user_id, username)
            save_user_data(user_id, user_data)
            logger.info(f"自动注册新用户: {username}({user_id})")

        # 记录发言
        await user_manager.update_user_message(user_id, group_id)

        # 日志
        user_data = self._load_and_log(user_id, username, group_id)

        # 命令路由
        await self._route_command(event, text, user_id, group_id)

    @filter_registry.private_server
    async def rqhbase_private(self, event: PrivateMessageEvent) -> None:
        """处理私聊消息"""
        text = event.message.plain_text.strip()
        user_id = str(event.user_id)
        username = event.user_name or str(user_id)
        group_id = "0"

        if not user_exists(user_id):
            user_data = user_manager.create_user(user_id, username)
            save_user_data(user_id, user_data)

        await self._route_command(event, text, user_id, group_id)

    # ==================== 辅助方法 ====================

    def _load_and_log(self, user_id: str, username: str, group_id: str):
        """加载用户数据并记录日志"""
        from .data_manager import load_user_data
        user_data = load_user_data(user_id)
        if user_data:
            user_data, week_key = check_and_handle_week_transition(user_data)
            if week_key in user_data.get("weekly_stats", {}):
                week_data = user_data["weekly_stats"][week_key]
                if group_id in week_data:
                    gd = week_data[group_id]
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    daily_count = gd["每日明细"].get(today_str, 0)
                    week_total = gd["累计数据"].get("总发言数", 0)
                    log_manager.log_message(user_id, username, group_id, daily_count, week_total)
        return user_data

    # ==================== 命令路由 ====================

    async def _route_command(self, event, text: str, user_id: str, group_id: str) -> None:
        """命令路由 - 转发到 command_handler"""
        cmd = self.cmd_handler

        if text == "注册":
            await cmd.handle_register(event, user_id, event.user_name or user_id)
        elif text == "发言日榜":
            await cmd.handle_daily_rank(event, group_id)
        elif text.startswith("历史日榜"):
            await cmd.handle_history_rank(event, group_id, text)
        elif text == "我的发言":
            await cmd.handle_my_stats(event, user_id, group_id)
        elif text == "发言周榜":
            await cmd.handle_weekly_rank(event, group_id)
        elif text.startswith("历史周榜"):
            await cmd.handle_history_weekly_rank(event, group_id, text)
        elif text == "发言月榜":
            await cmd.handle_monthly_rank(event, group_id)
        elif text.startswith("历史月榜"):
            await cmd.handle_history_monthly_rank(event, group_id, text)
        elif text == "发言季榜":
            await cmd.handle_seasonal_rank(event, group_id)
        elif text == "发言年榜":
            await cmd.handle_yearly_rank(event, group_id)
        elif text.startswith("历史年榜"):
            await cmd.handle_history_yearly_rank(event, group_id, text)
        elif text.startswith("设置用户名"):
            await cmd.handle_set_username(event, user_id, text)
        elif text.startswith("查询发言") or text.startswith("查发言"):
            await cmd.handle_query_user(event, group_id, text)
        elif text.startswith("删除用户"):
            await cmd.handle_delete_user(event, user_id, text)
        elif text == "自动归档":
            await cmd.handle_auto_archive(event, user_id)
        elif text.startswith("加白名单") or text.startswith("加入白名单"):
            await cmd.handle_add_group(event, user_id, text)
        elif text.startswith("移除白名单") or text.startswith("移出白名单"):
            await cmd.handle_remove_group(event, user_id, text)
        elif text == "查看白名单":
            await cmd.handle_view_whitelist(event, user_id)
        elif text.startswith("切换白名单模式"):
            await cmd.handle_toggle_whitelist(event, user_id)
        elif text == "修复数据":
            await cmd.handle_repair_data(event, user_id)
        elif text == "帮助":
            await self.reply_with_event(event, CommandHandler.get_help_text())
