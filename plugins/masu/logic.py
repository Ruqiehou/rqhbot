from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("masu")

DEFAULT_SYSTEM_PROMPT = (
    "你是一个友好的 QQ 机器人助手，名叫 Masu。"
    "请用中文回复，保持简洁有趣，适当使用表情。"
)

SESSION_TIMEOUT = 1800
RESET_COMMANDS = ("重置", "clear", "reset", "清空")
TRIGGER_PREFIXES = ["masu", "玛苏", "AI", "ai", "机器人", "@"]

DEFAULT_CONFIG: Dict[str, Any] = {
    "api_key": "",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-3.5-turbo",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "temperature": 0.8,
    "max_tokens": 500,
    "enable_group": True,
    "enable_private": True,
    "group_trigger": "mention",
    "group_trigger_keywords": ["masu", "玛苏", "AI"],
}


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
        self.records[key] = [t for t in records if now - t < self.window]
        if len(self.records[key]) >= self.max_calls:
            return False
        self.records[key].append(now)
        return True


class MasuChatService:
    def __init__(self, api: Any, config: Dict[str, Any]) -> None:
        self.api = api
        self.config = config
        self.sessions: Dict[str, Session] = {}
        self.rate_limiter = RateLimiter(max_calls=20, window=60.0)

    def update_config(self, config: Dict[str, Any]) -> None:
        self.config = config

    def clear(self) -> None:
        self.sessions.clear()

    async def handle_chat(
        self,
        event: Any,
        text: str,
        group_id: Optional[int],
    ) -> None:
        user_id = event.user_id
        session_key = f"{user_id}:{group_id}" if group_id else f"private:{user_id}"

        if not self.rate_limiter.check(str(user_id)):
            await self.api.send_event_message(event, "请求太频繁了，请稍后再试 >_<")
            return

        cleaned = clean_text(text)
        if not cleaned:
            return

        if cleaned in RESET_COMMANDS:
            session = self.sessions.get(session_key)
            if session is not None:
                session.reset()
            await self.api.send_event_message(event, "好的，已重置对话历史 ~")
            return

        session = self.sessions.get(session_key)
        if session is None or session.is_expired():
            session = Session(user_id, group_id)
            session.add_message("system", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
            self.sessions[session_key] = session

        session.add_message("user", cleaned)
        self.cleanup_sessions()

        reply = await call_openai_compatible_api(session.messages, self.config)
        if reply:
            session.add_message("assistant", reply)
            await self.api.send_event_message(event, reply)
            return

        await self.api.send_event_message(event, "抱歉，我现在有点卡住，请稍后再试 ~")

    def cleanup_sessions(self) -> None:
        now = time.time()
        expired = [
            key for key, session in self.sessions.items()
            if now - session.last_active > SESSION_TIMEOUT
        ]
        for key in expired:
            del self.sessions[key]


async def call_openai_compatible_api(
    messages: List[Dict[str, str]],
    config: Dict[str, Any],
) -> Optional[str]:
    api_key = config.get("api_key", "") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("未配置 API Key")
        return None

    base_url = config.get("base_url", "https://api.openai.com/v1")
    model = config.get("model", "gpt-3.5-turbo")

    try:
        import aiohttp

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": config.get("temperature", 0.8),
            "max_tokens": config.get("max_tokens", 500),
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
                    logger.error(f"API 调用失败 [{resp.status}]: {error_body}")
                    return None
                data = await resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return None
                return choices[0].get("message", {}).get("content", "").strip()

    except ImportError:
        logger.error("缺少 aiohttp 依赖，请执行: pip install aiohttp")
        return None
    except Exception as e:
        logger.error(f"API 调用异常: {e}", exc_info=True)
        return None


def clean_text(text: str) -> str:
    for prefix in TRIGGER_PREFIXES:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
            break
    return text
