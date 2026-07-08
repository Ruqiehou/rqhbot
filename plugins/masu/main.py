"""
masu — AI 聊天插件

基于 OpenAI API 的多轮对话插件，支持群聊和私聊。
使用内存管理会话上下文，支持关键词触发或 @ 触发。
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from sdk.core.events import GroupMessageEvent, PrivateMessageEvent
from sdk.pluginsystem import PluginBase, filter_registry

logger = logging.getLogger(__name__)

# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = (
    "你是一个友好的 QQ 机器人助手，名叫 Masu。"
    "请用中文回复，保持简洁有趣，适当使用表情。"
)

# 会话超时时间（秒）
SESSION_TIMEOUT = 1800  # 30 分钟


class Session:
    """单次会话上下文"""

    def __init__(self, user_id: int, group_id: Optional[int] = None):
        self.user_id = user_id
        self.group_id = group_id
        self.messages: List[Dict[str, str]] = []
        self.created_at = time.time()
        self.last_active = time.time()

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.last_active = time.time()
        # 保留最近 20 轮对话，防止上下文过长
        if len(self.messages) > 40:
            self.messages = self.messages[-40:]

    def is_expired(self) -> bool:
        return time.time() - self.last_active > SESSION_TIMEOUT

    def reset(self) -> None:
        self.messages.clear()
        self.last_active = time.time()


class RateLimiter:
    """简单的内存限速器"""

    def __init__(self, max_calls: int = 10, window: float = 60.0):
        self.max_calls = max_calls
        self.window = window
        self.records: Dict[str, List[float]] = {}

    def check(self, key: str) -> bool:
        now = time.time()
        records = self.records.setdefault(key, [])
        # 清理过期记录
        self.records[key] = [t for t in records if now - t < self.window]
        if len(self.records[key]) >= self.max_calls:
            return False
        self.records[key].append(now)
        return True


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
        self._sessions: Dict[str, Session] = {}
        self._rate_limiter = RateLimiter(max_calls=20, window=60.0)
        self._config: Dict[str, Any] = {}

        # 触发关键词
        self._trigger_prefixes: List[str] = ["masu", "玛苏", "AI", "ai", "机器人", "@"]

    async def on_load(self, api, event_bus, plugin_dir=None):
        await super().on_load(api, event_bus, plugin_dir)
        if plugin_dir:
            self.plugin_dir = Path(plugin_dir)
        self._config = await self.load_config("config.json")

        if not self._config:
            self._config = {
                "api_key": "",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-3.5-turbo",
                "system_prompt": DEFAULT_SYSTEM_PROMPT,
                "temperature": 0.8,
                "max_tokens": 500,
                "enable_group": True,
                "enable_private": True,
                "group_trigger": "mention",  # mention / keyword / all
                "group_trigger_keywords": ["masu", "玛苏", "AI"],
            }
            await self.save_config(self._config, "config.json")

        logger.info(f"[masu] 插件已加载，模型: {self._config.get('model', 'unknown')}")

    async def on_unload(self):
        self._sessions.clear()
        await super().on_unload()

    # ---- 群聊 ----

    @filter_registry.group_server(regex=r"(?i)^(masu|玛苏|ai)\s+")
    async def handle_group_keyword(self, event: GroupMessageEvent):
        """关键词触发群聊"""
        if not self._config.get("enable_group", True):
            return
        text = event.message.plain_text.strip()
        await self._handle_chat(event, text, group_id=event.group_id)

    @filter_registry.group_server
    async def handle_group_mention(self, event: GroupMessageEvent):
        """@ 触发群聊"""
        if not self._config.get("enable_group", True):
            return
        trigger = self._config.get("group_trigger", "keyword")
        if trigger == "keyword":
            return

        text = event.message.plain_text.strip()
        # 检查是否被 @
        mentions = [
            seg for seg in event.message.segments
            if seg.get("type") == "at" and str(seg.get("data", {}).get("qq", "")) == str(event.self_id)
        ]
        if not mentions:
            return

        # 去掉 @ 前缀
        text = re.sub(r"\[CQ:at,qq=\d+\]", "", text).strip()
        if not text:
            return
        await self._handle_chat(event, text, group_id=event.group_id)

    # ---- 私聊 ----

    @filter_registry.private_server
    async def handle_private(self, event: PrivateMessageEvent):
        """私聊直接触发 AI 对话"""
        if not self._config.get("enable_private", True):
            return
        text = event.message.plain_text.strip()
        if not text:
            return
        await self._handle_chat(event, text, group_id=None)

    # ---- 核心 ----

    async def _handle_chat(
        self,
        event: Any,
        text: str,
        group_id: Optional[int],
    ) -> None:
        """处理 AI 对话请求"""
        user_id = event.user_id
        session_key = f"{user_id}:{group_id}" if group_id else f"private:{user_id}"

        # 限速检查
        if not self._rate_limiter.check(str(user_id)):
            await self.api.send_event_message(
                event, "请求太频繁了，请稍后再试 >_<",
            )
            return

        # 清理命令前缀
        cleaned = self._clean_text(text)
        if not cleaned:
            return

        # 特殊命令
        if cleaned in ("重置", "clear", "reset", "清空"):
            if session_key in self._sessions:
                self._sessions[session_key].reset()
            await self.api.send_event_message(event, "好的，已重置对话历史 ~")
            return

        # 获取或创建会话
        session = self._sessions.get(session_key)
        if session is None or session.is_expired():
            session = Session(user_id, group_id)
            session.add_message("system", self._config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
            self._sessions[session_key] = session

        session.add_message("user", cleaned)

        # 清理过期会话
        self._cleanup_sessions()

        # 调用 API
        reply = await self._call_api(session.messages)
        if reply:
            session.add_message("assistant", reply)
            await self.api.send_event_message(event, reply)
        else:
            await self.api.send_event_message(event, "抱歉，我现在有点卡住，请稍后再试 ~")

    async def _call_api(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """调用 OpenAI 兼容 API"""
        api_key = self._config.get("api_key", "") or self._get_env_key()
        if not api_key:
            logger.warning("[masu] 未配置 API Key")
            return None

        base_url = self._config.get("base_url", "https://api.openai.com/v1")
        model = self._config.get("model", "gpt-3.5-turbo")

        try:
            import aiohttp

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "messages": messages,
                "temperature": self._config.get("temperature", 0.8),
                "max_tokens": self._config.get("max_tokens", 500),
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        logger.error(f"[masu] API 调用失败 [{resp.status}]: {error_body}")
                        return None
                    data = await resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        return None
                    return choices[0].get("message", {}).get("content", "").strip()

        except ImportError:
            logger.error("[masu] 缺少 aiohttp 依赖，请执行: pip install aiohttp")
            return None
        except Exception as e:
            logger.error(f"[masu] API 调用异常: {e}", exc_info=True)
            return None

    def _get_env_key(self) -> str:
        """从环境变量读取 API Key"""
        import os
        return os.environ.get("OPENAI_API_KEY", "")

    def _clean_text(self, text: str) -> str:
        """清理触发前缀，提取有效查询"""
        for prefix in self._trigger_prefixes:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()
                break
        return text

    def _cleanup_sessions(self) -> None:
        """清理过期会话"""
        now = time.time()
        expired = [
            k for k, v in self._sessions.items()
            if now - v.last_active > SESSION_TIMEOUT
        ]
        for k in expired:
            del self._sessions[k]
