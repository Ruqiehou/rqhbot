"""
masu — AI 聊天插件接口
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from sdk.core.events import GroupMessageEvent, PrivateMessageEvent
from sdk.pluginsystem import PluginBase, filter_registry

from .logic import DEFAULT_CONFIG, MasuChatService

logger = logging.getLogger("masu")


class MasuPlugin(PluginBase):
    """AI 聊天插件"""

    def __init__(self):
        super().__init__()
        self.name = "masu"
        self.version = "1.0.0"
        self.description = "AI 聊天 — 基于 OpenAI API 的多轮对话"
        self.author = "RqhBot Team"
        self.enabled = True

        self.plugin_dir = Path(__file__).parent
        self._config: Dict[str, Any] = {}
        self._chat: Optional[MasuChatService] = None

    async def on_load(self, api, event_bus, plugin_dir=None):
        await super().on_load(api, event_bus, plugin_dir)
        if plugin_dir:
            self.plugin_dir = Path(plugin_dir)

        self._config = await self.load_config("config.json")
        if not self._config:
            self._config = dict(DEFAULT_CONFIG)
            await self.save_config(self._config, "config.json")

        self._chat = MasuChatService(self.api, self._config)
        logger.info(f"插件已加载，模型: {self._config.get('model', 'unknown')}")

    async def on_unload(self):
        if self._chat is not None:
            self._chat.clear()
        await super().on_unload()

    @filter_registry.group_server(regex=r"(?i)^(masu|玛苏|ai)\s+")
    async def handle_group_keyword(self, event: GroupMessageEvent):
        """关键词触发群聊"""
        if not self._config.get("enable_group", True):
            return
        await self._handle_chat(event, event.message.plain_text.strip(), event.group_id)

    @filter_registry.group_server
    async def handle_group_mention(self, event: GroupMessageEvent):
        """@ 触发群聊"""
        if not self._config.get("enable_group", True):
            return
        if self._config.get("group_trigger", "keyword") == "keyword":
            return

        text = event.message.plain_text.strip()
        mentions = [
            seg for seg in event.message.segments
            if seg.get("type") == "at"
            and str(seg.get("data", {}).get("qq", "")) == str(event.self_id)
        ]
        if not mentions:
            return

        text = re.sub(r"\[CQ:at,qq=\d+\]", "", text).strip()
        if not text:
            return
        await self._handle_chat(event, text, event.group_id)

    @filter_registry.private_server
    async def handle_private(self, event: PrivateMessageEvent):
        """私聊直接触发 AI 对话"""
        if not self._config.get("enable_private", True):
            return
        text = event.message.plain_text.strip()
        if not text:
            return
        await self._handle_chat(event, text, None)

    async def _handle_chat(
        self,
        event: Any,
        text: str,
        group_id: Optional[int],
    ) -> None:
        if self._chat is None:
            return
        await self._chat.handle_chat(event, text, group_id)
