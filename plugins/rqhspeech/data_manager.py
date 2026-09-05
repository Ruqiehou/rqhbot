"""
数据管理模块 - 根据got.txt建议优化
1. 封装公共函数（获取用户名、加载/保存用户数据等）
2. 修复周切换函数参数问题
3. 统一数据操作接口
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from .speech_config import SpeechConfig

logger = logging.getLogger(__name__)

# 用户数据锁，防止并发读写导致数据丢失
_user_locks: Dict[str, asyncio.Lock] = {}
_user_locks_lock = asyncio.Lock()


async def _get_user_lock(user_id: str) -> asyncio.Lock:
    """获取指定用户的锁，确保同一用户的数据操作串行化"""
    async with _user_locks_lock:
        if user_id not in _user_locks:
            _user_locks[user_id] = asyncio.Lock()
        return _user_locks[user_id]


# ========== 工具函数 ==========

def get_user_file(user_id: str) -> str:
    """获取用户文件路径"""
    primary_file = os.path.join(SpeechConfig.USERS_DIR, f"user_{user_id}.json")
    legacy_file = os.path.join(SpeechConfig.LEGACY_USERS_DIR, f"user_{user_id}.json")
    return SpeechConfig.resolve_existing_file(primary_file, legacy_file)


def get_daily_file(date_str: str = None) -> str:
    """获取每日数据文件路径"""
    if date_str is None:
        date_str = SpeechConfig.get_current_date()
    primary_file = os.path.join(SpeechConfig.DAILY_DATA_DIR, f"daily_{date_str}.json")
    legacy_file = os.path.join(SpeechConfig.LEGACY_DAILY_DATA_DIR, f"daily_{date_str}.json")
    return SpeechConfig.resolve_existing_file(primary_file, legacy_file)


def get_weekly_file(week_key: str = None) -> str:
    """获取每周数据文件路径"""
    if week_key is None:
        current_date = datetime.now()
        current_week_start = current_date - timedelta(days=current_date.weekday())
        week_key = f"{current_week_start.isocalendar()[0]}-W{current_week_start.isocalendar()[1]:02d}"
    primary_file = os.path.join(SpeechConfig.WEEKLY_DATA_DIR, f"weekly_{week_key}.json")
    legacy_file = os.path.join(SpeechConfig.LEGACY_WEEKLY_DATA_DIR, f"weekly_{week_key}.json")
    return SpeechConfig.resolve_existing_file(primary_file, legacy_file)


def load_user_data(user_id: str) -> Optional[Dict[str, Any]]:
    """加载用户数据"""
    user_file = get_user_file(user_id)
    if not os.path.exists(user_file):
        return None
    try:
        with open(user_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"加载用户数据失败 {user_id}: {e}")
        return None


def save_user_data(user_id: str, data: Dict[str, Any]) -> bool:
    """保存用户数据"""
    user_file = os.path.join(SpeechConfig.USERS_DIR, f"user_{user_id}.json")
    try:
        with open(user_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存用户数据失败 {user_id}: {e}")
        return False


def load_daily_data(date_str: str = None) -> Optional[Dict[str, Any]]:
    """加载每日数据"""
    daily_file = get_daily_file(date_str)
    if not os.path.exists(daily_file):
        return None
    try:
        with open(daily_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"加载每日数据失败 {date_str}: {e}")
        return None


def save_daily_data(data: Dict[str, Any], date_str: str = None) -> bool:
    """保存每日数据"""
    if date_str is None:
        date_str = SpeechConfig.get_current_date()
    daily_file = os.path.join(SpeechConfig.DAILY_DATA_DIR, f"daily_{date_str}.json")
    try:
        with open(daily_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存每日数据失败 {date_str}: {e}")
        return False


def load_weekly_data(week_key: str = None) -> Optional[Dict[str, Any]]:
    """加载每周数据"""
    weekly_file = get_weekly_file(week_key)
    if not os.path.exists(weekly_file):
        return None
    try:
        with open(weekly_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"加载每周数据失败 {week_key}: {e}")
        return None


def save_weekly_data(data: Dict[str, Any], week_key: str = None) -> bool:
    """保存每周数据"""
    if week_key is None:
        current_date = datetime.now()
        current_week_start = current_date - timedelta(days=current_date.weekday())
        week_key = f"{current_week_start.isocalendar()[0]}-W{current_week_start.isocalendar()[1]:02d}"
    weekly_file = os.path.join(SpeechConfig.WEEKLY_DATA_DIR, f"weekly_{week_key}.json")
    try:
        with open(weekly_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存每周数据失败 {week_key}: {e}")
        return False


def get_display_username(user_info: Dict[str, Any], default: str = "未知用户") -> str:
    """
    获取显示用户名 - 根据got.txt建议封装的公共函数
    按优先级顺序查找用户名
    """
    return (
        user_info.get("summary", {}).get("username")
        or user_info.get("summary", {}).get("用户名")
        or user_info.get("用户名")
        or user_info.get("username")
        or default
    )


def user_exists(user_id: str) -> bool:
    """
    检查用户是否存在 - 根据got.txt建议优化
    只检查文件是否存在，不依赖发言数
    """
    user_file = get_user_file(user_id)
    return os.path.exists(user_file)


def check_and_handle_week_transition(user_data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    检查并处理周切换 - 根据got.txt建议优化
    移除未使用的user_id和username参数
    """
    current_date = datetime.now()
    current_week_start = current_date - timedelta(days=current_date.weekday())
    current_week_key = f"{current_week_start.isocalendar()[0]}-W{current_week_start.isocalendar()[1]:02d}"

    if "weekly_stats" not in user_data:
        user_data["weekly_stats"] = {}

    if current_week_key not in user_data["weekly_stats"]:
        user_data["weekly_stats"][current_week_key] = {
            "统计周期": {
                "week_start": current_week_start.strftime("%Y-%m-%d"),
                "week_end": (current_week_start + timedelta(days=6)).strftime("%Y-%m-%d"),
                "week_key": current_week_key
            },
            "累计数据": {
                "总发言数": 0,
                "活跃天数": 0
            },
            "每日明细": {},
            "活跃时间": {
                "首次活跃日期": None,
                "最后活跃日期": None
            },
            "统计时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 初始化本周每日明细
        for i in range(7):
            day = (current_week_start + timedelta(days=i)).strftime("%Y-%m-%d")
            user_data["weekly_stats"][current_week_key]["每日明细"][day] = 0

    return user_data, current_week_key


# ========== 用户管理类 ==========

class UserDataManager:
    """用户数据管理器 - 统一的数据操作接口"""

    def __init__(self):
        self.users_dir = SpeechConfig.USERS_DIR

    def _iter_user_ids(self):
        user_dirs = [SpeechConfig.USERS_DIR]
        if os.path.exists(SpeechConfig.LEGACY_USERS_DIR):
            user_dirs.append(SpeechConfig.LEGACY_USERS_DIR)

        seen_users = set()
        for users_dir in user_dirs:
            if not os.path.exists(users_dir):
                continue
            for filename in os.listdir(users_dir):
                if not filename.startswith("user_") or not filename.endswith(".json"):
                    continue
                user_id = filename[5:-5]
                if user_id in seen_users:
                    continue
                seen_users.add(user_id)
                yield user_id

    def _iter_week_keys(self):
        weekly_dirs = [SpeechConfig.WEEKLY_DATA_DIR]
        if os.path.exists(SpeechConfig.LEGACY_WEEKLY_DATA_DIR):
            weekly_dirs.append(SpeechConfig.LEGACY_WEEKLY_DATA_DIR)

        seen_weeks = set()
        for weekly_dir in weekly_dirs:
            if not os.path.exists(weekly_dir):
                continue
            for filename in os.listdir(weekly_dir):
                if not filename.startswith("weekly_") or not filename.endswith(".json"):
                    continue
                week_key = filename[7:-5]
                if week_key in seen_weeks:
                    continue
                seen_weeks.add(week_key)
                yield week_key

    def _iter_daily_dates(self):
        daily_dirs = [SpeechConfig.DAILY_DATA_DIR]
        if os.path.exists(SpeechConfig.LEGACY_DAILY_DATA_DIR):
            daily_dirs.append(SpeechConfig.LEGACY_DAILY_DATA_DIR)

        seen_dates = set()
        for daily_dir in daily_dirs:
            if not os.path.exists(daily_dir):
                continue
            for filename in os.listdir(daily_dir):
                if not filename.startswith("daily_") or not filename.endswith(".json"):
                    continue
                date_str = filename[6:-5]
                if date_str in seen_dates:
                    continue
                seen_dates.add(date_str)
                yield date_str

    def create_user(self, user_id: str, username: str) -> Dict[str, Any]:
        """创建新用户数据"""
        current_time = datetime.now().strftime(SpeechConfig.DATETIME_FORMAT)
        return {
            "用户id": user_id,
            "用户名": username,
            "发言": {
                "发言数量": 0,
                "时间": datetime.now().strftime(SpeechConfig.DISPLAY_DATE_FORMAT)
            },
            "创建时间": current_time,
            "最后更新": current_time,
            "summary": {
                "user_id": user_id,
                "username": username,
                "total_weeks": 0,
                "total_messages": 0,
                "avg_messages_per_week": 0,
                "most_active_week": None,
                "consistency_score": 0,
                "first_week": None,
                "last_week": None,
                "update_time": current_time
            }
        }

    async def update_user_message(self, user_id: str, group_id: str) -> bool:
        """
        更新用户发言数据（异步版本，带锁保护）
        自动处理周切换，将日数据和周数据分开存储
        """
        # 获取用户锁，防止并发读写
        lock = await _get_user_lock(user_id)
        async with lock:
            user_data = load_user_data(user_id)
            if not user_data:
                return False

            current_date_str = datetime.now().strftime("%Y-%m-%d")
            current_date = datetime.now()
            current_week_start = current_date - timedelta(days=current_date.weekday())
            current_week_key = f"{current_week_start.isocalendar()[0]}-W{current_week_start.isocalendar()[1]:02d}"

            # 加载每日数据
            daily_data = load_daily_data(current_date_str)
            if daily_data is None:
                daily_data = {"日期": current_date_str, "users": {}}

            # 加载每周数据
            weekly_data = load_weekly_data(current_week_key)
            if weekly_data is None:
                weekly_data = {
                    "week_key": current_week_key,
                    "week_start": current_week_start.strftime("%Y-%m-%d"),
                    "week_end": (current_week_start + timedelta(days=6)).strftime("%Y-%m-%d"),
                    "users": {}
                }

            # 更新每日数据
            if user_id not in daily_data["users"]:
                daily_data["users"][user_id] = {"groups": {}}
            if group_id not in daily_data["users"][user_id]["groups"]:
                daily_data["users"][user_id]["groups"][group_id] = 0
            daily_data["users"][user_id]["groups"][group_id] += 1

            # 更新每周数据
            if user_id not in weekly_data["users"]:
                weekly_data["users"][user_id] = {"groups": {}}
            if group_id not in weekly_data["users"][user_id]["groups"]:
                weekly_data["users"][user_id]["groups"][group_id] = {"daily": {}, "total": 0, "active_days": 0}

            # 更新每日明细
            if current_date_str not in weekly_data["users"][user_id]["groups"][group_id]["daily"]:
                weekly_data["users"][user_id]["groups"][group_id]["daily"][current_date_str] = 0
            weekly_data["users"][user_id]["groups"][group_id]["daily"][current_date_str] += 1

            # 更新累计数据
            weekly_data["users"][user_id]["groups"][group_id]["total"] += 1

            # 更新活跃天数
            if weekly_data["users"][user_id]["groups"][group_id]["daily"][current_date_str] == 1:
                weekly_data["users"][user_id]["groups"][group_id]["active_days"] += 1

            # 保存每日数据到 daily 文件夹
            save_daily_data(daily_data, current_date_str)

            # 保存每周数据到 weekly 文件夹
            save_weekly_data(weekly_data, current_week_key)

            # ========== 同步更新用户文件中的 weekly_stats ==========
            if "weekly_stats" not in user_data:
                user_data["weekly_stats"] = {}

            if current_week_key not in user_data["weekly_stats"]:
                user_data["weekly_stats"][current_week_key] = {
                    "统计周期": {
                        "week_start": current_week_start.strftime("%Y-%m-%d"),
                        "week_end": (current_week_start + timedelta(days=6)).strftime("%Y-%m-%d"),
                        "week_key": current_week_key
                    },
                    "累计数据": {
                        "总发言数": 0,
                        "活跃天数": 0
                    },
                    "每日明细": {},
                    "活跃时间": {
                        "首次活跃日期": None,
                        "最后活跃日期": None
                    },
                    "统计时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                # 初始化本周每日明细
                for i in range(7):
                    day = (current_week_start + timedelta(days=i)).strftime("%Y-%m-%d")
                    user_data["weekly_stats"][current_week_key]["每日明细"][day] = 0

            # 确保群数据存在
            if group_id not in user_data["weekly_stats"][current_week_key]:
                user_data["weekly_stats"][current_week_key][group_id] = {
                    "每日明细": {},
                    "累计数据": {
                        "总发言数": 0,
                        "活跃天数": 0
                    }
                }
                # 初始化每日明细
                for i in range(7):
                    day = (current_week_start + timedelta(days=i)).strftime("%Y-%m-%d")
                    user_data["weekly_stats"][current_week_key][group_id]["每日明细"][day] = 0

            # 更新用户文件中的每日明细
            if current_date_str not in user_data["weekly_stats"][current_week_key][group_id]["每日明细"]:
                user_data["weekly_stats"][current_week_key][group_id]["每日明细"][current_date_str] = 0
            user_data["weekly_stats"][current_week_key][group_id]["每日明细"][current_date_str] += 1

            # 更新用户文件中的累计数据
            user_data["weekly_stats"][current_week_key][group_id]["累计数据"]["总发言数"] += 1

            # 更新活跃天数
            if user_data["weekly_stats"][current_week_key][group_id]["每日明细"][current_date_str] == 1:
                user_data["weekly_stats"][current_week_key][group_id]["累计数据"]["活跃天数"] += 1

            # 更新用户汇总信息
            self._update_summary(user_data, user_id)

            # 保存数据
            return save_user_data(user_id, user_data)

    def _update_summary(self, user_data: Dict[str, Any], user_id: str = None):
        """更新用户汇总信息"""
        total_messages = 0
        total_weeks = 0
        most_active_week = None
        max_messages = 0
        weeks = []

        if not os.path.exists(SpeechConfig.WEEKLY_DATA_DIR) and not os.path.exists(SpeechConfig.LEGACY_WEEKLY_DATA_DIR):
            user_data["summary"].update({
                "total_weeks": 0,
                "total_messages": 0,
                "avg_messages_per_week": 0,
                "most_active_week": None,
                "first_week": None,
                "last_week": None,
                "update_time": datetime.now().strftime(SpeechConfig.DATETIME_FORMAT)
            })
            return

        weekly_dirs = [SpeechConfig.WEEKLY_DATA_DIR]
        if os.path.exists(SpeechConfig.LEGACY_WEEKLY_DATA_DIR):
            weekly_dirs.append(SpeechConfig.LEGACY_WEEKLY_DATA_DIR)

        seen_weeks = set()
        for weekly_dir in weekly_dirs:
            if not os.path.exists(weekly_dir):
                continue
            for filename in os.listdir(weekly_dir):
                if not filename.startswith("weekly_") or not filename.endswith(".json"):
                    continue

                week_key = filename[7:-5]
                if week_key in seen_weeks:
                    continue
                seen_weeks.add(week_key)
                weekly_data = load_weekly_data(week_key)

                if not weekly_data or "users" not in weekly_data:
                    continue

                if user_id and user_id not in weekly_data["users"]:
                    continue

                weeks.append(week_key)

                week_total = 0
                if user_id and user_id in weekly_data["users"]:
                    for group_data in weekly_data["users"][user_id]["groups"].values():
                        if isinstance(group_data, dict):
                            week_total += group_data.get("total", 0)
                elif not user_id:
                    for user_data_temp in weekly_data["users"].values():
                        if isinstance(user_data_temp, dict) and "groups" in user_data_temp:
                            for group_data in user_data_temp["groups"].values():
                                if isinstance(group_data, dict):
                                    week_total += group_data.get("total", 0)

                total_messages += week_total

                if week_total > max_messages:
                    max_messages = week_total
                    most_active_week = {"week_key": week_key, "messages": week_total}

        total_weeks = len(weeks)
        weeks.sort()

        user_data["summary"].update({
            "total_weeks": total_weeks,
            "total_messages": total_messages,
            "avg_messages_per_week": round(total_messages / total_weeks, 2) if total_weeks > 0 else 0,
            "most_active_week": most_active_week,
            "first_week": weeks[0] if weeks else None,
            "last_week": weeks[-1] if weeks else None,
            "update_time": datetime.now().strftime(SpeechConfig.DATETIME_FORMAT)
        })

    def get_user_today_count(self, user_id: str, group_id: str) -> int:
        """获取用户今日发言数"""
        current_date_str = datetime.now().strftime("%Y-%m-%d")
        daily_data = load_daily_data(current_date_str)
        
        if not daily_data or "users" not in daily_data:
            return 0
        
        if user_id not in daily_data["users"]:
            return 0
        
        user_data = daily_data["users"][user_id]
        if "groups" not in user_data or group_id not in user_data["groups"]:
            return 0
        
        return user_data["groups"][group_id]

    def get_user_week_count(self, user_id: str, group_id: str) -> int:
        """获取用户本周发言数"""
        current_date = datetime.now()
        current_week_start = current_date - timedelta(days=current_date.weekday())
        current_week_key = f"{current_week_start.isocalendar()[0]}-W{current_week_start.isocalendar()[1]:02d}"
        
        weekly_data = load_weekly_data(current_week_key)
        
        if not weekly_data or "users" not in weekly_data:
            return 0
        
        if user_id not in weekly_data["users"]:
            return 0
        
        user_data = weekly_data["users"][user_id]
        if "groups" not in user_data or group_id not in user_data["groups"]:
            return 0
        
        group_data = user_data["groups"][group_id]
        if isinstance(group_data, dict):
            return group_data.get("total", 0)
        return 0
    
    def get_user_month_count(self, user_id: str, group_id: str, year: int = None, month: int = None) -> int:
        """
        获取用户本月发言数
        :param user_id: 用户ID
        :param group_id: 群号
        :param year: 年份，默认为当前年
        :param month: 月份，默认为当前月
        """
        stats = self.get_monthly_ranking_stats(group_id, year, month)
        for item in stats:
            if item["用户id"] == user_id:
                return item["总发言数"]
        return 0
    
    def get_user_year_count(self, user_id: str, group_id: str, year: int = None) -> int:
        """
        获取用户本年度发言数
        :param user_id: 用户ID
        :param group_id: 群号
        :param year: 年份，默认为当前年
        """
        if year is None:
            year = datetime.now().year
        
        total_messages = 0
        
        if not os.path.exists(SpeechConfig.WEEKLY_DATA_DIR) and not os.path.exists(SpeechConfig.LEGACY_WEEKLY_DATA_DIR):
            return 0

        weekly_dirs = [SpeechConfig.WEEKLY_DATA_DIR]
        if os.path.exists(SpeechConfig.LEGACY_WEEKLY_DATA_DIR):
            weekly_dirs.append(SpeechConfig.LEGACY_WEEKLY_DATA_DIR)

        seen_weeks = set()
        for weekly_dir in weekly_dirs:
            if not os.path.exists(weekly_dir):
                continue
            for filename in os.listdir(weekly_dir):
                if not filename.startswith("weekly_") or not filename.endswith(".json"):
                    continue

                week_key = filename[7:-5]
                if week_key in seen_weeks:
                    continue
                seen_weeks.add(week_key)

                try:
                    week_year = int(week_key.split("-W")[0])

                    if week_year == year:
                        weekly_data = load_weekly_data(week_key)
                        if weekly_data and "users" in weekly_data:
                            if user_id in weekly_data["users"]:
                                user_data = weekly_data["users"][user_id]
                                if "groups" in user_data and group_id in user_data["groups"]:
                                    group_data = user_data["groups"][group_id]
                                    if isinstance(group_data, dict):
                                        total_messages += group_data.get("total", 0)
                except Exception:
                    continue
        
        return total_messages

    def get_daily_rankings(self, group_id: str, date_str: str = None) -> List[Tuple[str, int]]:
        """
        获取日榜排行
        如果指定date_str，则获取历史日榜
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        rankings = []

        daily_data = load_daily_data(date_str)
        if not daily_data or "users" not in daily_data:
            return rankings

        for user_id, user_data in daily_data["users"].items():
            if not isinstance(user_data, dict) or "groups" not in user_data:
                continue
            
            if group_id in user_data["groups"]:
                count = user_data["groups"][group_id]
                if count > 0:
                    rankings.append((user_id, count))

        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def get_weekly_rankings(self, group_id: str) -> List[Tuple[str, int]]:
        """
        获取当前周榜排行
        从用户文件中的 weekly_stats 读取数据，保证实时性
        """
        rankings = []
        
        current_date = datetime.now()
        current_week_start = current_date - timedelta(days=current_date.weekday())
        current_week_key = f"{current_week_start.isocalendar()[0]}-W{current_week_start.isocalendar()[1]:02d}"
        
        for user_id in self._iter_user_ids():
            user_data = load_user_data(user_id)
            
            if not user_data or "weekly_stats" not in user_data:
                continue
            
            # 检查当前周是否有数据
            if current_week_key not in user_data["weekly_stats"]:
                continue
            
            week_data = user_data["weekly_stats"][current_week_key]
            
            # 检查该群是否有数据
            if group_id not in week_data:
                continue
            
            group_data = week_data[group_id]
            if not isinstance(group_data, dict):
                continue
            
            # 获取累计数据
            total_count = group_data.get("累计数据", {}).get("总发言数", 0)
            if total_count > 0:
                rankings.append((user_id, total_count))
        
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings
    
    def get_historical_weekly_rankings(self, group_id: str, week_identifier: str) -> Tuple[List[Tuple[str, int]], str]:
        """
        获取历史周榜排行
        :param group_id: 群号
        :param week_identifier: 周标识符，支持两种格式：
                               1. YYYY-MM-DD（日期格式，自动找到该周的周一）
                               2. W数字（如 W06，表示当前年份的第6周）
        :return: (排行榜列表, 周信息字符串)
        """
        week_key = None
        week_info = ""
        
        # 判断是日期格式还是W+数字格式
        if week_identifier.startswith('W') or week_identifier.startswith('w'):
            # W+数字格式，如 W06（ISO 周数）
            try:
                week_num = int(week_identifier[1:])
                if week_num < 1 or week_num > 53:
                    return [], "无效的周数"

                current_year = datetime.now().isocalendar()[0]
                week_key = f"{current_year}-W{week_num:02d}"

                # 使用 ISO 周格式解析该周第一天的日期（周一）
                week_first_day = datetime.fromisocalendar(current_year, week_num, 1)
                week_end = week_first_day + timedelta(days=6)
                week_info = f"{current_year}年第{week_num}周 ({week_first_day.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')})"
            except (ValueError, IndexError):
                return [], "周数格式错误"
        else:
            # 日期格式 YYYY-MM-DD
            try:
                target_date = datetime.strptime(week_identifier, "%Y-%m-%d")
                # 找到该周的周一
                week_start = target_date - timedelta(days=target_date.weekday())
                week_key = f"{week_start.isocalendar()[0]}-W{week_start.isocalendar()[1]:02d}"
                week_end = week_start + timedelta(days=6)
                week_info = f"{week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')}"
            except ValueError:
                return [], "日期格式错误，请使用 YYYY-MM-DD 格式"
        
        # 加载对应周的数据
        weekly_data = load_weekly_data(week_key)
        if not weekly_data or "users" not in weekly_data:
            return [], week_info
        
        rankings = []
        for user_id, user_data in weekly_data["users"].items():
            if not isinstance(user_data, dict) or "groups" not in user_data:
                continue
            
            if group_id in user_data["groups"]:
                group_data = user_data["groups"][group_id]
                if isinstance(group_data, dict):
                    count = group_data.get("total", 0)
                    if count > 0:
                        rankings.append((user_id, count))
        
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings, week_info
    
    def get_monthly_ranking_stats(self, group_id: str, year: int = None, month: int = None) -> List[Dict[str, Any]]:
        """
        获取月榜详细统计
        :param group_id: 群号
        :param year: 年份，默认为当前年
        :param month: 月份，默认为当前月
        """
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month

        stats = {}
        active_dates = {}

        for date_str in self._iter_daily_dates():
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            if date_obj.year != year or date_obj.month != month:
                continue

            daily_data = load_daily_data(date_str)
            if not daily_data or "users" not in daily_data:
                continue

            for user_id, user_data in daily_data["users"].items():
                if not isinstance(user_data, dict) or "groups" not in user_data:
                    continue
                if group_id not in user_data["groups"]:
                    continue

                count = user_data["groups"].get(group_id, 0)
                if count <= 0:
                    continue

                stats[user_id] = stats.get(user_id, 0) + count
                active_dates.setdefault(user_id, set()).add(date_str)

        result = []
        for user_id, total_messages in stats.items():
            user_data = load_user_data(user_id) or {}
            result.append({
                "用户id": user_id,
                "用户名": get_display_username(user_data, user_id),
                "总发言数": total_messages,
                "活跃天数": len(active_dates.get(user_id, set())),
                "月份": f"{year}年{month}月"
            })

        result.sort(key=lambda x: x["总发言数"], reverse=True)
        return result

    def get_monthly_summary(self, group_id: str, year: int = None, month: int = None) -> Dict[str, Any]:
        """获取月度统计摘要"""
        stats = self.get_monthly_ranking_stats(group_id, year, month)
        if not stats:
            return {
                "total_users": 0,
                "total_messages": 0,
                "top_user": None
            }

        return {
            "total_users": len(stats),
            "total_messages": sum(item["总发言数"] for item in stats),
            "top_user": stats[0]
        }

    def get_monthly_rankings(self, group_id: str, year: int = None, month: int = None) -> List[Tuple[str, int]]:
        """
        获取月榜排行
        :param group_id: 群号
        :param year: 年份，默认为当前年
        :param month: 月份，默认为当前月
        """
        stats = self.get_monthly_ranking_stats(group_id, year, month)
        return [(item["用户id"], item["总发言数"]) for item in stats]
    
    def get_monthly_rankings_by_start_date(self, group_id: str, start_date_str: str) -> List[Tuple[str, int]]:
        """
        根据起始日期获取月度排行榜
        :param group_id: 群号
        :param start_date_str: 月份起始日期字符串 (YYYY-MM-DD)
        """
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            year = start_date.year
            month = start_date.month
        except ValueError:
            return []
        
        return self.get_monthly_rankings(group_id, year, month)
    
    def get_yearly_rankings(self, group_id: str, year: int = None) -> List[Tuple[str, int]]:
        """
        获取年榜排行
        :param group_id: 群号
        :param year: 年份，默认为当前年
        """
        if year is None:
            year = datetime.now().year
        
        rankings = {}

        for week_key in self._iter_week_keys():
            try:
                week_year = int(week_key.split("-W")[0])

                if week_year == year:
                    weekly_data = load_weekly_data(week_key)
                    if weekly_data and "users" in weekly_data:
                        for user_id, user_data in weekly_data["users"].items():
                            if not isinstance(user_data, dict) or "groups" not in user_data:
                                continue

                            if group_id in user_data["groups"]:
                                group_data = user_data["groups"][group_id]
                                if isinstance(group_data, dict):
                                    count = group_data.get("total", 0)
                                    if user_id not in rankings:
                                        rankings[user_id] = 0
                                    rankings[user_id] += count
            except Exception:
                continue

        result = [(user_id, count) for user_id, count in rankings.items() if count > 0]
        result.sort(key=lambda x: x[1], reverse=True)
        return result
    
    def get_seasonal_rankings(self, group_id: str, year: int = None, season: int = None) -> List[Tuple[str, int]]:
        """
        获取季榜排行
        :param group_id: 群号
        :param year: 年份，默认为当前年
        :param season: 季度 (1-4)，默认为当前季度
        """
        if year is None:
            year = datetime.now().year
        if season is None:
            # 根据当前月份计算季度
            season = (datetime.now().month - 1) // 3 + 1
        
        # 计算该季度的月份范围
        month_start = (season - 1) * 3 + 1
        month_end = month_start + 2
        
        rankings = []

        for user_id in self._iter_user_ids():
            user_data = load_user_data(user_id)

            if not user_data or "weekly_stats" not in user_data:
                continue

            # 累加该季度所有月的发言数
            total_messages = 0
            for week_key, week_data in user_data["weekly_stats"].items():
                if not isinstance(week_data, dict):
                    continue
                
                # 检查周是否在该季度内
                if group_id in week_data:
                    try:
                        week_year = int(week_key.split("-W")[0])
                        week_num = int(week_key.split("-W")[1])
                        
                        # 计算该周第一天的日期
                        week_first_day = datetime.strptime(f"{week_year}-W{week_num:02d}-1", "%Y-W%W-%w")
                        
                        # 如果该周在当前季度内，则累加发言数
                        if week_first_day.year == year and month_start <= week_first_day.month <= month_end:
                            total_messages += week_data[group_id].get("累计数据", {}).get("总发言数", 0)
                    except Exception:
                        continue

            if total_messages > 0:
                rankings.append((user_id, total_messages))

        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def set_username(self, user_id: str, new_username: str) -> bool:
        """
        设置用户名 - 根据got.txt建议修复乱码键名bug
        """
        user_data = load_user_data(user_id)
        if not user_data:
            return False

        # 更新所有相关字段
        user_data["用户名"] = new_username

        if "summary" not in user_data:
            user_data["summary"] = {}
        user_data["summary"]["username"] = new_username
        user_data["summary"]["user_id"] = user_id

        # 更新周数据中的用户名
        if "weekly_stats" in user_data:
            for week_key in user_data["weekly_stats"]:
                if isinstance(user_data["weekly_stats"][week_key], dict):
                    user_data["weekly_stats"][week_key]["用户名"] = new_username
                    user_data["weekly_stats"][week_key]["用户id"] = user_id

        user_data["最后更新"] = datetime.now().strftime(SpeechConfig.DATETIME_FORMAT)

        return save_user_data(user_id, user_data)

    def search_user_by_username(self, username: str) -> Optional[str]:
        """通过用户名搜索用户ID"""
        for user_id in self._iter_user_ids():
            user_data = load_user_data(user_id)

            if not user_data:
                continue

            current_username = get_display_username(user_data, "")
            if current_username == username:
                return user_id

        return None


# ========== 日志管理类 ==========

class LogManager:
    """日志管理器 - 根据got.txt建议使用logging模块"""

    def __init__(self):
        self.logs_dir = SpeechConfig.LOGS_DIR
        self.log_file = os.path.join(self.logs_dir, SpeechConfig.get_log_filename())

    def log_message(self, user_id: str, username: str, group_id: str,
                    daily_count: int, week_total: int):
        """记录发言日志"""
        if not SpeechConfig.ENABLE_LOGGING:
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_week_key = f"{datetime.now().isocalendar()[0]}-W{datetime.now().isocalendar()[1]:02d}"

        log_entry = (
            f"[{current_time}] 用户 {username}({user_id}) 于 {current_date} "
            f"在群 {group_id} 发言，今日: {daily_count}, "
            f"本周({current_week_key}): {week_total}\n"
        )

        try:
            self.log_file = os.path.join(self.logs_dir, SpeechConfig.get_log_filename())
            os.makedirs(self.logs_dir, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"写入日志失败: {e}")


# 全局实例
user_manager = UserDataManager()
log_manager = LogManager()
