"""
归档管理模块 - 保留老版本的归档功能，添加自动检查功能

自动检查从上次归档后的所有日期并归档
"""

import json
import csv
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from .speech_config import SpeechConfig


class DailyArchiver:
    """每日归档管理器"""
    
    def __init__(self):
        """初始化"""
        self.users_dir = SpeechConfig.USERS_DIR
        self.archives_dir = SpeechConfig.DAILY_RANKINGS_DIR
        self.last_archive_file = os.path.join(SpeechConfig.ARCHIVES_DIR, "last_archive.json")
    
    def get_all_user_files(self) -> List[str]:
        """获取所有用户JSON文件"""
        user_files = []
        user_dirs = [self.users_dir]
        if os.path.exists(SpeechConfig.LEGACY_USERS_DIR):
            user_dirs.append(SpeechConfig.LEGACY_USERS_DIR)

        seen_files = set()
        for users_dir in user_dirs:
            if not os.path.exists(users_dir):
                continue
            for file in os.listdir(users_dir):
                if file.endswith(SpeechConfig.USER_FILE_EXTENSION) and file not in seen_files:
                    seen_files.add(file)
                    user_files.append(file)
        return user_files

    def load_user_data(self, filename: str) -> Optional[Dict[str, Any]]:
        """加载用户数据"""
        primary_file = os.path.join(self.users_dir, filename)
        legacy_file = os.path.join(SpeechConfig.LEGACY_USERS_DIR, filename)
        filepath = SpeechConfig.resolve_existing_file(primary_file, legacy_file)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            print(f"❌ 加载文件 {filename} 时出错: {e}")
            return None
    
    def collect_user_stats_for_date(self, target_date: str) -> List[Dict[str, Any]]:
        """收集指定日期的用户统计数据"""
        user_stats = []
        user_files = self.get_all_user_files()
        
        print(f"📊 正在收集 {len(user_files)} 个用户的统计数据...")
        
        for user_file in user_files:
            data = self.load_user_data(user_file)
            if data:
                # 提取用户信息
                user_id = data.get("用户id", "")
                username = (
                    data.get('summary', {}).get('username') or 
                    data.get('summary', {}).get('用户名') or
                    data.get('用户名') or 
                    data.get('username') or 
                    ""
                )
                
                # 从weekly_stats的每日明细中获取指定日期的数据
                message_count = 0
                weekly_stats = data.get("weekly_stats", {})
                
                # 遍历所有周的统计数据查找目标日期
                for week_data in weekly_stats.values():
                    if isinstance(week_data, dict):
                        # 检查是否有每日明细
                        if "每日明细" in week_data:
                            daily_details = week_data["每日明细"]
                            if target_date in daily_details:
                                message_count = daily_details[target_date]
                                break
                        # 检查是否有群聊数据
                        for key, value in week_data.items():
                            if key not in ["统计周期", "统计时间"] and isinstance(value, dict):
                                if "每日明细" in value:
                                    daily_details = value["每日明细"]
                                    if target_date in daily_details:
                                        message_count += daily_details[target_date]
                
                # 设置最后发言时间为目标日期
                target_date_obj = datetime.strptime(target_date, "%Y-%m-%d")
                message_time = target_date_obj.strftime(SpeechConfig.DISPLAY_DATE_FORMAT)
                
                # 计算活跃度得分
                activity_score = message_count * 1.0
                
                user_stat = {
                    "用户id": user_id,
                    "用户名": username,
                    "发言数量": message_count,
                    "最后发言时间": message_time,
                    "活跃度得分": activity_score,
                    "数据文件": user_file,
                    "收集时间": SpeechConfig.get_current_datetime()
                }
                
                user_stats.append(user_stat)
        
        return user_stats
    
    def generate_ranking(self, user_stats: List[Dict[str, Any]], 
                        top_n: int = None) -> Dict[str, Any]:
        """生成排行榜"""
        if top_n is None:
            top_n = SpeechConfig.RANKING_TOP_N
        
        # 按发言数量降序排序
        sorted_by_messages = sorted(
            user_stats, 
            key=lambda x: x["发言数量"], 
            reverse=True
        )
        
        # 按活跃度得分降序排序
        sorted_by_activity = sorted(
            user_stats, 
            key=lambda x: x["活跃度得分"], 
            reverse=True
        )
        
        # 过滤掉发言数为0的用户
        active_users = [u for u in user_stats 
                       if u["发言数量"] >= SpeechConfig.MIN_MESSAGES_FOR_RANKING]
        
        # 生成榜单数据
        ranking_data = {
            "生成时间": SpeechConfig.get_current_datetime(),
            "统计日期": SpeechConfig.get_current_date(),
            "总用户数": len(user_stats),
            "活跃用户数": len(active_users),
            "总发言数": sum(u["发言数量"] for u in user_stats),
            "榜单": {
                "按发言数量排名": [
                    {
                        "排名": i + 1,
                        "用户id": user["用户id"],
                        "用户名": user["用户名"],
                        "发言数量": user["发言数量"],
                        "最后发言时间": user["最后发言时间"]
                    }
                    for i, user in enumerate(sorted_by_messages[:top_n])
                ],
                "按活跃度排名": [
                    {
                        "排名": i + 1,
                        "用户id": user["用户id"],
                        "用户名": user["用户名"],
                        "活跃度得分": user["活跃度得分"],
                        "发言数量": user["发言数量"]
                    }
                    for i, user in enumerate(sorted_by_activity[:top_n])
                ]
            },
            "详细数据": active_users
        }
        
        return ranking_data
    
    def save_ranking_json(self, ranking_data: Dict[str, Any], 
                         date: str = None) -> str:
        """保存榜单为JSON文件"""
        if date is None:
            date = SpeechConfig.get_current_date()
        
        filename = SpeechConfig.get_ranking_filename(date)
        filepath = os.path.join(self.archives_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(ranking_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 榜单已保存为JSON文件: {filename}")
            return filepath
            
        except Exception as e:
            print(f"❌ 保存JSON榜单时出错: {e}")
            return ""
    
    def save_ranking_csv(self, ranking_data: Dict[str, Any], 
                        date: str = None) -> str:
        """保存榜单为CSV文件"""
        if date is None:
            date = SpeechConfig.get_current_date()
        
        filename = SpeechConfig.get_csv_filename(date)
        filepath = os.path.join(self.archives_dir, filename)
        
        try:
            # 提取按发言数量排名的数据
            message_ranking = ranking_data["榜单"]["按发言数量排名"]
            
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                
                # 写入标题
                writer.writerow([
                    "排名", "用户ID", "用户名", 
                    "发言数量", "最后发言时间", "统计日期"
                ])
                
                # 写入数据
                for item in message_ranking:
                    writer.writerow([
                        item["排名"],
                        item["用户id"],
                        item["用户名"],
                        item["发言数量"],
                        item["最后发言时间"],
                        date
                    ])
            
            print(f"✅ 榜单已保存为CSV文件: {filename}")
            return filepath
            
        except Exception as e:
            print(f"❌ 保存CSV榜单时出错: {e}")
            return ""
    
    def archive_for_date(self, target_date: str) -> Tuple[bool, str]:
        """归档指定日期的数据"""
        print(f"[归档] 开始为日期 {target_date} 执行数据归档...")
        
        try:
            # 收集指定日期的用户统计数据
            user_stats = self.collect_user_stats_for_date(target_date)
            
            if not user_stats:
                return False, f"日期 {target_date} 没有用户数据"
            
            # 生成榜单
            ranking_data = self.generate_ranking(user_stats)
            ranking_data["统计日期"] = target_date
            
            # 保存榜单文件
            json_file = self.save_ranking_json(ranking_data, target_date)
            csv_file = self.save_ranking_csv(ranking_data, target_date)
            
            if not json_file and not csv_file:
                return False, "榜单保存失败"
            
            # 生成归档报告
            report = self.generate_archive_report(ranking_data)
            
            # 更新最后归档日期
            self.update_last_archive_date(target_date)
            
            return True, f"成功归档 {target_date} 的数据\n{report}"
            
        except Exception as e:
            print(f"[归档] ❌ 执行归档时出现异常: {e}")
            import traceback
            traceback.print_exc()
            return False, f"归档失败: {str(e)}"
    
    def generate_archive_report(self, ranking_data: Dict[str, Any]) -> str:
        """生成归档报告"""
        total_users = ranking_data["总用户数"]
        active_users = ranking_data["活跃用户数"]
        total_messages = ranking_data["总发言数"]
        
        # 获取榜首用户
        top_user = ranking_data["榜单"]["按发言数量排名"][0] if ranking_data["榜单"]["按发言数量排名"] else {}
        
        report = f"""
📈 归档报告
══════════════════════════════════════
统计日期：{ranking_data["统计日期"]}
生成时间：{ranking_data["生成时间"]}
总用户数：{total_users} 人
活跃用户：{active_users} 人
总发言数：{total_messages} 条

🏆 榜首用户
══════════════════════════════════════
👑 用户名：{top_user.get("用户名", "无")}
🆔 用户ID：{top_user.get("用户id", "无")}
💬 发言数：{top_user.get("发言数量", 0)} 条
⏰ 最后发言：{top_user.get("最后发言时间", "无")}

📊 详细榜单已保存到：{self.archives_dir}
        """
        
        print(report)
        return report
    
    def get_last_archive_date(self) -> Optional[str]:
        """获取最后归档日期"""
        if not os.path.exists(self.last_archive_file):
            return None
        
        try:
            with open(self.last_archive_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("last_archive_date")
        except Exception as e:
            print(f"❌ 读取最后归档日期失败: {e}")
            return None
    
    def update_last_archive_date(self, date: str):
        """更新最后归档日期"""
        try:
            data = {"last_archive_date": date, "update_time": SpeechConfig.get_current_datetime()}
            with open(self.last_archive_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 更新最后归档日期失败: {e}")
    
    def get_dates_to_archive(self) -> List[str]:
        """获取需要归档的日期列表"""
        dates_to_archive = []
        
        # 获取最后归档日期
        last_archive_date = self.get_last_archive_date()
        
        # 计算开始日期
        if last_archive_date:
            start_date = datetime.strptime(last_archive_date, "%Y-%m-%d") + timedelta(days=1)
        else:
            # 如果没有最后归档日期，默认从7天前开始
            start_date = datetime.now() - timedelta(days=7)
        
        # 计算结束日期（昨天）
        end_date = datetime.now() - timedelta(days=1)
        
        # 生成日期列表
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            dates_to_archive.append(date_str)
            current_date += timedelta(days=1)
        
        return dates_to_archive
    
    def auto_archive(self) -> Tuple[bool, str]:
        """自动归档从上次归档后的所有日期"""
        print("=" * 50)
        print("开始自动归档处理")
        print("=" * 50)
        
        # 获取需要归档的日期
        dates_to_archive = self.get_dates_to_archive()
        
        if not dates_to_archive:
            return True, "没有需要归档的日期"
        
        print(f"找到 {len(dates_to_archive)} 个需要归档的日期:")
        for date in dates_to_archive:
            print(f"  - {date}")
        
        # 逐个归档日期
        results = []
        for date in dates_to_archive:
            success, message = self.archive_for_date(date)
            results.append((date, success, message))
        
        # 生成汇总报告
        successful = sum(1 for _, success, _ in results if success)
        total = len(results)
        
        report = f"""
📊 自动归档汇总报告
══════════════════════════════════════
总处理日期：{total} 个
成功归档：{successful} 个
失败归档：{total - successful} 个

详细结果：
"""
        
        for date, success, message in results:
            status = "✅" if success else "❌"
            report += f"{status} {date}: {message.split('\n')[0]}\n"
        
        print(report)
        return True, report
    
    def archive_today(self) -> Tuple[bool, str]:
        """归档今天的数据"""
        today = SpeechConfig.get_current_date()
        return self.archive_for_date(today)
    
    def display_today_ranking(self):
        """显示今日榜单"""
        today_file = os.path.join(
            self.archives_dir, 
            SpeechConfig.get_ranking_filename()
        )
        
        if not os.path.exists(today_file):
            print("今日榜单尚未生成，请先执行归档操作。")
            return
        
        try:
            with open(today_file, 'r', encoding='utf-8') as f:
                ranking_data = json.load(f)
            
            print("=" * 60)
            print("🏆 今日发言排行榜 🏆")
            print("=" * 60)
            print(f"📅 统计日期: {ranking_data['统计日期']}")
            print(f"👥 总用户数: {ranking_data['总用户数']}")
            print(f"💬 总发言数: {ranking_data['总发言数']}")
            print()
            
            # 显示按发言数量排名的前10名
            print("📊 按发言数量排名（前10名）:")
            print("-" * 60)
            for item in ranking_data['榜单']['按发言数量排名'][:10]:
                print(f"🏅 第{item['排名']:2d}名: {item['用户名']:15s} "
                      f"| 💬 {item['发言数量']:4d}条 "
                      f"| ⏰ {item['最后发言时间']}")
            
            print()
            
            # 显示按活跃度排名的前5名
            print("🚀 按活跃度排名（前5名）:")
            print("-" * 60)
            for item in ranking_data['榜单']['按活跃度排名'][:5]:
                print(f"⭐ 第{item['排名']:2d}名: {item['用户名']:15s} "
                      f"| 📈 {item['活跃度得分']:6.2f}分 "
                      f"| 💬 {item['发言数量']:4d}条")
            
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ 读取榜单时出错: {e}")


def daily_archive():
    """执行日常归档"""
    today = SpeechConfig.get_current_date()
    print(f"开始归档今天的数据: {today}")
    
    archiver = DailyArchiver()
    success, message = archiver.archive_for_date(today)
    
    if success:
        print("✅ 日归档完成")
    else:
        print(f"❌ 归档失败: {message}")
    
    return success

def auto_archive():
    """执行自动归档"""
    archiver = DailyArchiver()
    success, message = archiver.auto_archive()
    
    if success:
        print("✅ 自动归档完成")
    else:
        print(f"❌ 自动归档失败: {message}")
    
    return success

def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--today':
            daily_archive()
        elif sys.argv[1] == '--auto':
            auto_archive()
        elif sys.argv[1] == '--date':
            if len(sys.argv) > 2:
                target_date = sys.argv[2]
                try:
                    datetime.strptime(target_date, "%Y-%m-%d")
                    archiver = DailyArchiver()
                    archiver.archive_for_date(target_date)
                except ValueError:
                    print(f"❌ 日期格式错误: {target_date}. 请使用 YYYY-MM-DD 格式")
            else:
                print("❌ 请指定日期: python archive_manager.py --date YYYY-MM-DD")
        elif sys.argv[1] == '--display':
            archiver = DailyArchiver()
            archiver.display_today_ranking()
        else:
            print("使用方法:")
            print("  python archive_manager.py --today          # 归档今天数据")
            print("  python archive_manager.py --auto           # 自动归档")
            print("  python archive_manager.py --date DATE      # 归档指定日期数据")
            print("  python archive_manager.py --display        # 显示今日榜单")
    else:
        # 默认执行自动归档
        auto_archive()


if __name__ == "__main__":
    main()
