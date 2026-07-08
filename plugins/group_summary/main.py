import asyncio
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sdk.core.events import GroupMessageEvent
from sdk.pluginsystem import PluginBase, filter_registry

logger = logging.getLogger("group_summary")


class GroupSummaryPlugin(PluginBase):
    """群总结插件 - 基于用户消息总结发言和风格并生成报告。"""

    def __init__(self):
        super().__init__()
        self.name = "group_summary"
        self.version = "1.0.0"
        self.description = "群总结插件 - 基于用户消息总结发言和风格并生成报告"
        self.author = "rqh"
        self.enabled = True
        self.plugin_dir = Path(__file__).parent
        self.data_dir = self.plugin_dir / "data"
        self.report_dir = self.plugin_dir / "reports"
        self._write_lock = asyncio.Lock()
        self.command_prefixes = ("群总结", "群总结帮助")
        self.stop_words = {
            "的", "了", "是", "我", "你", "他", "她", "它", "和", "就", "都", "也", "很", "在", "有", "没", "不", "啊", "吗", "吧", "呢", "喵",
            "一个", "这个", "那个", "什么", "怎么", "为什么", "可以", "不是", "还是", "然后", "如果", "但是", "所以", "因为", "已经",
        }

    async def on_load(self, api, event_bus, plugin_dir=None):
        await super().on_load(api, event_bus, plugin_dir)
        if plugin_dir:
            self.plugin_dir = Path(plugin_dir)
            self.data_dir = self.plugin_dir / "data"
            self.report_dir = self.plugin_dir / "reports"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"已加载，数据目录: {self.data_dir}")

    @filter_registry.group_server()
    async def handle_group_message(self, event: GroupMessageEvent):
        text = event.message.plain_text.strip()
        if not text:
            return
        if text == "群总结帮助":
            await self._reply_help(event)
            return
        if text.startswith("群总结"):
            await self._handle_summary_command(event, text)
            await self._record_message(event, text)
            return
        await self._record_message(event, text)

    async def _record_message(self, event: GroupMessageEvent, text: str):
        now = datetime.now()
        row = {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": int(now.timestamp()),
            "group_id": str(event.group_id),
            "user_id": str(event.user_id),
            "user_name": event.user_name or str(event.user_id),
            "message_id": int(event.message_id),
            "text": text,
        }
        file_path = self.data_dir / f"{now.strftime('%Y-%m-%d')}.jsonl"
        async with self._write_lock:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    async def _handle_summary_command(self, event: GroupMessageEvent, text: str):
        group_id = str(event.group_id)
        args = text.split()
        if len(args) >= 3 and args[1] == "用户":
            report = self._build_user_report(group_id, args[2], days=7)
        else:
            days = self._parse_days(args[1] if len(args) >= 2 else "今日")
            report = self._build_group_report(group_id, days)
        await self.api.send_group_message(group_id=event.group_id, message=report[:3500])
        self._save_report(group_id, report)

    async def _reply_help(self, event: GroupMessageEvent):
        msg = "群总结插件命令：\n群总结 - 总结今日群消息\n群总结 今日 - 总结今日群消息\n群总结 7天 - 总结最近7天\n群总结 用户 QQ号 - 总结指定用户最近7天发言和风格\n群总结帮助 - 查看说明"
        await self.api.send_group_message(group_id=event.group_id, message=msg)

    def _parse_days(self, value: str) -> int:
        if value in ("今日", "今天", "日"):
            return 1
        match = re.search(r"(\d+)", value)
        if not match:
            return 1
        return max(1, min(int(match.group(1)), 30))

    def _iter_records(self, group_id: str, days: int) -> Iterable[Dict[str, Any]]:
        today = datetime.now().date()
        start_date = today - timedelta(days=days - 1)
        for i in range(days):
            day = start_date + timedelta(days=i)
            file_path = self.data_dir / f"{day.strftime('%Y-%m-%d')}.jsonl"
            if not file_path.exists():
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if str(row.get("group_id")) == group_id:
                        yield row

    def _build_group_report(self, group_id: str, days: int) -> str:
        records = list(self._iter_records(group_id, days))
        period = "今日" if days == 1 else f"最近{days}天"
        if not records:
            return f"📊 群总结报告（{period}）\n暂无可总结的用户消息。"

        user_stats = defaultdict(lambda: {"name": "", "count": 0, "chars": 0, "messages": []})
        hour_counter = Counter()
        topic_counter = Counter()
        word_counter = Counter()

        for row in records:
            text = str(row.get("text", "")).strip()
            user_id = str(row.get("user_id", ""))
            user_stats[user_id]["name"] = str(row.get("user_name", user_id))
            user_stats[user_id]["count"] += 1
            user_stats[user_id]["chars"] += len(text)
            user_stats[user_id]["messages"].append(text)
            hour_counter[datetime.fromtimestamp(int(row.get("timestamp", 0))).hour] += 1
            topic_counter[self._classify_topic(text)] += 1
            word_counter.update(self._extract_words(text))

        top_users = sorted(user_stats.items(), key=lambda item: item[1]["count"], reverse=True)[:8]
        active_hour = hour_counter.most_common(1)[0][0] if hour_counter else 0
        top_topics = "、".join(f"{topic}({count})" for topic, count in topic_counter.most_common(5))
        top_words = "、".join(word for word, _ in word_counter.most_common(12)) or "暂无"
        style_lines = self._build_user_style_lines(top_users[:5])

        lines = [
            f"📊 群总结报告（{period}）",
            f"群号：{group_id}",
            f"消息数：{len(records)} 条",
            f"参与用户：{len(user_stats)} 人",
            f"高峰时段：{active_hour}:00 - {active_hour + 1}:00",
            f"主要主题：{top_topics or '暂无'}",
            f"高频词：{top_words}",
            "",
            "🏆 发言榜：",
        ]
        for index, (user_id, stat) in enumerate(top_users, 1):
            avg_len = stat["chars"] / max(stat["count"], 1)
            lines.append(f"{index}. {stat['name']}（{user_id}）：{stat['count']}条，均长{avg_len:.1f}字")
        lines.extend(["", "🎭 用户风格速写："])
        lines.extend(style_lines)
        lines.extend(["", f"📝 总评：{self._build_overall_comment(records, topic_counter, user_stats)}"])
        return "\n".join(lines)

    def _build_user_report(self, group_id: str, target_user_id: str, days: int = 7) -> str:
        records = [row for row in self._iter_records(group_id, days) if str(row.get("user_id")) == target_user_id]
        if not records:
            return f"📊 用户风格报告\n用户 {target_user_id} 最近{days}天暂无记录。"

        name = str(records[-1].get("user_name", target_user_id))
        messages = [str(row.get("text", "")).strip() for row in records if str(row.get("text", "")).strip()]
        total_chars = sum(len(text) for text in messages)
        topic_counter = Counter(self._classify_topic(text) for text in messages)
        word_counter = Counter()
        hour_counter = Counter()
        for row, text in zip(records, messages):
            word_counter.update(self._extract_words(text))
            hour_counter[datetime.fromtimestamp(int(row.get("timestamp", 0))).hour] += 1
        style = self._analyze_style(messages)
        active_hour = hour_counter.most_common(1)[0][0] if hour_counter else 0
        examples = self._select_examples(messages)

        lines = [
            "📊 用户风格报告",
            f"用户：{name}（{target_user_id}）",
            f"范围：最近{days}天",
            f"发言数：{len(messages)} 条",
            f"平均长度：{total_chars / max(len(messages), 1):.1f} 字",
            f"常见主题：{'、'.join(f'{k}({v})' for k, v in topic_counter.most_common(5))}",
            f"活跃时段：{active_hour}:00 - {active_hour + 1}:00",
            f"高频词：{'、'.join(word for word, _ in word_counter.most_common(12)) or '暂无'}",
            f"表达风格：{style}",
            "代表发言：",
        ]
        lines.extend(f"- {example}" for example in examples)
        return "\n".join(lines)

    def _classify_topic(self, text: str) -> str:
        rules = [
            ("AI/模型", ("模型", "ai", "AI", "gpt", "GPT", "qwen", "Qwen", "deepseek", "DeepSeek")),
            ("代码/开发", ("代码", "bug", "Bug", "插件", "函数", "报错", "修复", "github", "GitHub", "api", "API")),
            ("生活日常", ("早", "晚安", "吃", "睡", "摸鱼", "作业", "上课")),
            ("图片表情", ("[图片", "[表情", "表情包", "骰子", "猜拳", "戳一戳")),
            ("问题讨论", ("？", "?", "怎么", "为什么", "如何", "能不能", "可不可以")),
        ]
        for topic, keywords in rules:
            if any(keyword in text for keyword in keywords):
                return topic
        if re.search(r"https?://|www\.", text, re.IGNORECASE):
            return "链接资料"
        return "闲聊杂谈"

    def _extract_words(self, text: str) -> List[str]:
        words = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,4}", text)
        return [word for word in words if word not in self.stop_words and not word.isdigit()]

    def _analyze_style(self, messages: List[str]) -> str:
        if not messages:
            return "暂无足够样本"
        joined = "\n".join(messages)
        avg_len = sum(len(text) for text in messages) / len(messages)
        question_ratio = sum(1 for text in messages if "?" in text or "？" in text) / len(messages)
        emoji_ratio = sum(1 for text in messages if re.search(r"[~～!！…]|\[[^\]]+\]", text)) / len(messages)
        traits = []
        if avg_len >= 45:
            traits.append("长句展开型")
        elif avg_len <= 10:
            traits.append("短句高频型")
        else:
            traits.append("中等长度交流型")
        if question_ratio >= 0.25:
            traits.append("爱提问/推进讨论")
        if emoji_ratio >= 0.25:
            traits.append("表情和语气词较多")
        if any(word in joined for word in ("喵", "哥哥", "姐姐")):
            traits.append("角色感明显")
        if any(word in joined for word in ("代码", "模型", "插件", "bug", "API", "api")):
            traits.append("技术话题倾向")
        return "、".join(traits)

    def _build_user_style_lines(self, top_users: List[Tuple[str, Dict[str, Any]]]) -> List[str]:
        lines = []
        for user_id, stat in top_users:
            messages = stat["messages"]
            style = self._analyze_style(messages)
            lines.append(f"- {stat['name']}（{user_id}）：{style}")
        return lines or ["- 暂无足够样本"]

    def _build_overall_comment(self, records: List[Dict[str, Any]], topic_counter: Counter, user_stats: Dict[str, Dict[str, Any]]) -> str:
        main_topic = topic_counter.most_common(1)[0][0] if topic_counter else "闲聊杂谈"
        most_active = max(user_stats.values(), key=lambda stat: stat["count"])
        return f"本时段群聊以“{main_topic}”为主，{most_active['name']} 发言最活跃。整体互动量为 {len(records)} 条，可继续观察高频主题变化。"

    def _select_examples(self, messages: List[str]) -> List[str]:
        cleaned = [text.replace("\n", " ") for text in messages if len(text.strip()) >= 2]
        cleaned.sort(key=len, reverse=True)
        return cleaned[:3] or ["暂无代表发言"]

    def _save_report(self, group_id: str, report: str):
        now = datetime.now()
        file_path = self.report_dir / f"summary_{group_id}_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report)
