"""
命令处理器模块 - 封装所有与发言排行相关的命令逻辑
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from .speech_config import SpeechConfig
from .data_manager import (
    user_manager,
    load_user_data,
    get_display_username,
    user_exists,
)


class CommandHandler:
    """命令处理器"""

    def __init__(self, reply_func: Callable[..., Any]):
        self.reply_func = reply_func

    async def _reply(self, event: Any, msg: str) -> None:
        await self.reply_func(event, msg)

    def _format_lines(self, title: str, items: List[Tuple[str, int]], top_n: int) -> str:
        lines = [f"{title}\n"]
        for i, (uid, count) in enumerate(items[:top_n], 1):
            ud = load_user_data(uid)
            name = get_display_username(ud, uid) if ud else uid
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i:>2}."
            lines.append(f"{medal} [{name}]: {count}条")
        return "\n".join(lines)

    async def handle_register(self, event: Any, user_id: str, username: str) -> bool:
        if user_exists(user_id):
            await self._reply(event, "❌ 用户已注册")
            return True
        from .data_manager import save_user_data
        data = user_manager.create_user(user_id, username)
        save_user_data(user_id, data)
        await self._reply(event, f"✅ 用户 {username} ({user_id}) 已注册")
        return True

    async def handle_daily_rank(self, event: Any, group_id: str) -> bool:
        items = user_manager.get_daily_rankings(group_id)
        if not items:
            await self._reply(event, "暂无发言记录")
            return True
        await self._reply(event, self._format_lines("📊 今日发言排行", items, 15))

    async def handle_weekly_rank(self, event: Any, group_id: str) -> bool:
        items = user_manager.get_weekly_rankings(group_id)
        if not items:
            await self._reply(event, "暂无本周发言记录")
            return True
        await self._reply(event, self._format_lines("📊 本周发言排行", items, 15))

    async def handle_monthly_rank(self, event: Any, group_id: str) -> bool:
        items = user_manager.get_monthly_rankings(group_id)
        if not items:
            await self._reply(event, "暂无本月发言记录")
            return True
        await self._reply(event, self._format_lines("📊 本月发言排行", items, 15))

    async def handle_seasonal_rank(self, event: Any, group_id: str) -> bool:
        items = user_manager.get_seasonal_rankings(group_id)
        if not items:
            await self._reply(event, "暂无本季度发言记录")
            return True
        await self._reply(event, self._format_lines("📊 本季发言排行", items, 15))

    async def handle_yearly_rank(self, event: Any, group_id: str) -> bool:
        items = user_manager.get_yearly_rankings(group_id)
        if not items:
            await self._reply(event, "暂无本年发言记录")
            return True
        await self._reply(event, self._format_lines("📊 本年发言排行", items, 15))

    async def handle_history_rank(self, event: Any, group_id: str, text: str) -> bool:
        date_str = self._extract_date(text)
        if not date_str:
            await self._reply(event, "格式: 历史榜 yyyy-mm-dd")
            return True
        items = user_manager.get_daily_rankings(f"{group_id}:{date_str}")
        if not items:
            await self._reply(event, f"无 {date_str} 的发言记录")
            return True
        await self._reply(event, self._format_lines(f"📊 {date_str} 发言排行", items, 15))

    async def handle_history_weekly_rank(self, event: Any, group_id: str, text: str) -> bool:
        week = self._extract_week(text)
        if not week:
            await self._reply(event, "格式: 历史周榜 2026-W01")
            return True
        items = user_manager.get_weekly_rankings(f"{group_id}:{week}")
        if not items:
            await self._reply(event, f"无第{week}周发言记录")
            return True
        await self._reply(event, self._format_lines(f"📊 第{week}周排行", items, 15))

    async def handle_history_monthly_rank(self, event: Any, group_id: str, text: str) -> bool:
        month = self._extract_month(text)
        if not month:
            await self._reply(event, "格式: 历史月榜 yyyy-mm")
            return True
        items = user_manager.get_monthly_rankings(f"{group_id}:{month}")
        if not items:
            await self._reply(event, f"无 {month} 发言记录")
            return True
        await self._reply(event, self._format_lines(f"📊 {month} 排行", items, 15))

    async def handle_history_yearly_rank(self, event: Any, group_id: str, text: str) -> bool:
        year = self._extract_year(text)
        if not year:
            await self._reply(event, "格式: 历史年榜 yyyy")
            return True
        items = user_manager.get_yearly_rankings(f"{group_id}:{year}")
        if not items:
            await self._reply(event, f"无 {year} 发言记录")
            return True
        await self._reply(event, self._format_lines(f"📊 {year} 排行", items, 15))

    async def handle_my_stats(self, event: Any, user_id: str, group_id: str) -> bool:
        data = load_user_data(user_id)
        if not data:
            await self._reply(event, "❌ 未注册，请先发送「登记」")
            return True
        name = get_display_username(data, user_id)
        daily = data.get("发言", {}).get("每日", {})
        weekly = data.get("发言", {}).get("每周", {})
        total = sum(daily.values()) if isinstance(daily, dict) else 0
        weeks = sum(1 for v in weekly.values() if v > 0) if isinstance(weekly, dict) else 0
        await self._reply(event, f"📊 [{name}] 统计\n今日: {daily.get(SpeechConfig.get_current_date(), 0)}条\n总发言: {total}条\n活跃周: {weeks}周")

    async def handle_set_username(self, event: Any, user_id: str, text: str) -> bool:
        name = self._extract_param(text, "改名")
        if not name:
            await self._reply(event, "格式: 改名 新名字")
            return True
        data = load_user_data(user_id)
        if not data:
            await self._reply(event, "❌ 未注册，请先发送「登记」")
            return True
        data["用户名"] = name
        from .data_manager import save_user_data
        save_user_data(user_id, data)
        await self._reply(event, f"✅ 已改名为: {name}")

    async def handle_query_user(self, event: Any, group_id: str, text: str) -> bool:
        target = self._extract_param(text, "查")
        if not target:
            await self._reply(event, "格式: 查 用户名或QQ")
            return True
        results = []
        from .data_manager import user_manager as um
        for uid in um._iter_user_ids():
            d = load_user_data(uid)
            if d and (target in str(d.get("用户名", "")) or target in str(uid)):
                results.append(f"{get_display_username(d, uid)} ({uid})")
        if not results:
            await self._reply(event, "未找到匹配用户")
        else:
            await self._reply(event, "📋 匹配用户:\n" + "\n".join(results[:20]))

    async def handle_delete_user(self, event: Any, user_id: str, text: str) -> bool:
        if str(user_id) not in SpeechConfig.ADMIN_USERS:
            await self._reply(event, "❌ 仅管理员可操作")
            return True
        target = self._extract_param(text, "删")
        if not target:
            await self._reply(event, "格式: 删 QQ号")
            return True
        import os
        from .data_manager import get_user_file
        path = get_user_file(target)
        if os.path.exists(path):
            os.remove(path)
            await self._reply(event, f"✅ 已删除用户 {target}")
        else:
            await self._reply(event, f"❌ 用户 {target} 不存在")

    async def handle_auto_archive(self, event: Any, user_id: str) -> bool:
        if str(user_id) not in SpeechConfig.ADMIN_USERS:
            await self._reply(event, "❌ 仅管理员可操作")
            return True
        from .archive_manager import ArchiveManager
        am = ArchiveManager()
        result = await am.auto_archive()
        await self._reply(event, f"📦 归档完成: {result}")

    async def handle_add_group(self, event: Any, user_id: str, text: str) -> bool:
        if str(user_id) not in SpeechConfig.ADMIN_USERS:
            await self._reply(event, "❌ 仅管理员可操作")
            return True
        gid = self._extract_param(text, "加群")
        if gid:
            SpeechConfig().add_allowed_group(gid)
            await self._reply(event, f"✅ 已添加群 {gid}")
        else:
            await self._reply(event, "格式: 加群 群号")

    async def handle_remove_group(self, event: Any, user_id: str, text: str) -> bool:
        if str(user_id) not in SpeechConfig.ADMIN_USERS:
            await self._reply(event, "❌ 仅管理员可操作")
            return True
        gid = self._extract_param(text, "移群")
        if gid:
            SpeechConfig().remove_allowed_group(gid)
            await self._reply(event, f"✅ 已移除群 {gid}")
        else:
            await self._reply(event, "格式: 移群 群号")

    async def handle_view_whitelist(self, event: Any, user_id: str) -> bool:
        if str(user_id) not in SpeechConfig.ADMIN_USERS:
            await self._reply(event, "❌ 仅管理员可操作")
            return True
        groups = SpeechConfig.ALLOWED_GROUPS
        if groups:
            await self._reply(event, "📋 白名单群:\n" + "\n".join(groups))
        else:
            await self._reply(event, "当前无白名单群")

    async def handle_toggle_whitelist(self, event: Any, user_id: str) -> bool:
        if str(user_id) not in SpeechConfig.ADMIN_USERS:
            await self._reply(event, "❌ 仅管理员可操作")
            return True
        cfg = SpeechConfig()
        cfg.WHITELIST_MODE = not cfg.WHITELIST_MODE
        await self._reply(event, f"✅ 白名单模式: {'开启' if cfg.WHITELIST_MODE else '关闭'}")

    async def handle_repair_data(self, event: Any, user_id: str) -> bool:
        if str(user_id) not in SpeechConfig.ADMIN_USERS:
            await self._reply(event, "❌ 仅管理员可操作")
            return True
        await self._reply(event, "🔧 数据修复中，请稍候...")
        fixed = 0
        for uid in user_manager._iter_user_ids():
            d = load_user_data(uid)
            if d and not isinstance(d.get("发言"), dict):
                d["发言"] = {"发言数量": 0, "每日": {}, "每周": {}}
                from .data_manager import save_user_data
                save_user_data(uid, d)
                fixed += 1
        await self._reply(event, f"✅ 修复完成，共处理 {fixed} 个用户")

    # ---- 辅助 ----

    @staticmethod
    def _extract_date(text: str) -> Optional[str]:
        import re
        m = re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})", text)
        if m:
            return m.group(1).replace("年", "-").replace("月", "-").replace("/", "-")
        return None

    @staticmethod
    def _extract_week(text: str) -> Optional[str]:
        import re
        m = re.search(r"(\d{4})[-\s]?(?:W|第|周)?(\d{1,2})", text)
        if m:
            return f"{m.group(1)}-W{int(m.group(2)):02d}"
        return None

    @staticmethod
    def _extract_month(text: str) -> Optional[str]:
        import re
        m = re.search(r"(\d{4})[-/](\d{1,2})", text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}"
        return None

    @staticmethod
    def _extract_year(text: str) -> Optional[str]:
        import re
        m = re.search(r"(\d{4})", text)
        return m.group(1) if m else None

    @staticmethod
    def _extract_param(text: str, cmd: str) -> Optional[str]:
        rest = text[len(cmd):].strip() if text.startswith(cmd) else text.strip()
        return rest or None
