import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from sdk.core.events import GroupMessageEvent, PrivateMessageEvent
from sdk.pluginsystem import PluginBase, filter_registry

logger = logging.getLogger("theme_diary")


class ThemeDiaryPlugin(PluginBase):
    """主题日记插件 - 将收到的消息按主题写入插件目录下的每日 Markdown 日记。"""

    def __init__(self):
        super().__init__()
        self.name = "theme_diary"
        self.version = "1.0.0"
        self.description = "主题日记日志插件 - 将收到的消息按主题写入每日 Markdown 日记"
        self.author = "rqh"
        self.enabled = True
        self.plugin_dir = Path(__file__).parent
        self.diary_dir = self.plugin_dir / "diaries"
        self._write_lock = asyncio.Lock()
        self.topic_keywords: Dict[str, Tuple[str, ...]] = {
            "AI与模型": ("模型", "ai", "AI", "gpt", "GPT", "qwen", "Qwen", "deepseek", "DeepSeek", "api", "API"),
            "代码与开发": ("代码", "bug", "Bug", "插件", "函数", "报错", "修复", "开发", "github", "GitHub"),
            "群聊日常": ("早", "晚安", "吃", "睡", "摸鱼", "聊天", "日常"),
            "图片与表情": ("[图片", "[表情", "表情包", "骰子", "猜拳", "戳一戳"),
        }

    async def on_load(self, api, event_bus, plugin_dir=None):
        await super().on_load(api, event_bus, plugin_dir)
        if plugin_dir:
            self.plugin_dir = Path(plugin_dir)
            self.diary_dir = self.plugin_dir / "diaries"
        self.diary_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"已加载，日记目录: {self.diary_dir}")

    @filter_registry.group_server
    async def log_group_message(self, event: GroupMessageEvent):
        await self._write_event(
            source="群聊",
            user_id=str(event.user_id),
            user_name=event.user_name or str(event.user_id),
            content=event.message.plain_text.strip(),
            group_id=str(event.group_id),
        )

    @filter_registry.private_server
    async def log_private_message(self, event: PrivateMessageEvent):
        await self._write_event(
            source="私聊",
            user_id=str(event.user_id),
            user_name=event.user_name or str(event.user_id),
            content=event.message.plain_text.strip(),
            group_id=None,
        )

    async def _write_event(self, source: str, user_id: str, user_name: str, content: str, group_id: str = None):
        if not content:
            return

        now = datetime.now()
        topic = self._detect_topic(content)
        diary_file = self.diary_dir / f"{now.strftime('%Y-%m-%d')}.md"
        entry = self._format_entry(now, topic, source, user_id, user_name, content, group_id)

        async with self._write_lock:
            is_new_file = not diary_file.exists()
            with open(diary_file, "a", encoding="utf-8") as f:
                if is_new_file:
                    f.write(f"# {now.strftime('%Y-%m-%d')} 主题日记\n\n")
                f.write(entry)

    def _detect_topic(self, content: str) -> str:
        for topic, keywords in self.topic_keywords.items():
            if any(keyword in content for keyword in keywords):
                return topic
        if re.search(r"https?://|www\.", content, re.IGNORECASE):
            return "链接与资料"
        if re.search(r"[?？]$|怎么|为什么|如何|能不能|可不可以", content):
            return "问题与讨论"
        return "未分类记录"

    def _format_entry(
        self,
        now: datetime,
        topic: str,
        source: str,
        user_id: str,
        user_name: str,
        content: str,
        group_id: str = None,
    ) -> str:
        escaped_content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        lines: List[str] = [
            f"## {topic}",
            f"- 时间：{now.strftime('%H:%M:%S')}",
            f"- 来源：{source}" + (f" {group_id}" if group_id else ""),
            f"- 用户：{user_name}（{user_id}）",
            "- 内容：",
        ]
        lines.extend(f"  > {line}" for line in escaped_content.splitlines())
        lines.append("")
        return "\n".join(lines) + "\n"
