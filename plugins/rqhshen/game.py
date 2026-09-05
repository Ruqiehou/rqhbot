import random
import json
import os
from datetime import datetime, timedelta

# 全局经验配置
EXPERIENCE_CONFIG = {}

def load_realms_from_json():
    """从JSON文件加载境界配置"""
    global EXPERIENCE_CONFIG
    # 使用插件目录路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, "jingjie.json")
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            realms = data.get('realms', [])
            thresholds = data.get('thresholds', [])
            
            # 加载经验配置
            EXPERIENCE_CONFIG = data.get('experience_settings', {})
            
            # 如果JSON中没有预设的阈值，则按斐波那契数列生成
            if not thresholds and realms:
                thresholds = generate_fibonacci_thresholds(len(realms))
            
            return realms, thresholds
    else:
        # 默认配置 - 250个主要境界
        realms = [
            "练气期",
            "筑基期", 
            "金丹期",
            "元婴期",
            "化神期",
            "炼虚期",
            "合体期",
            "大乘期",
            "渡劫期",
            "散仙",
            "地仙",
            "天仙",
            "真仙",
            "玄仙",
            "金仙",
            "太乙金仙",
            "大至金仙", 
            "太乙玄仙",
            "大至玄仙",
            "太乙真仙",
            "大至真仙",
            "太乙天仙",
            "大至天仙",
            "大罗仙",
            "大罗金仙",
            "大罗散仙",
            "九天玄仙",
            "九天金仙",
            "九天真仙",
            "九天仙",
            "九天散仙",
            "太乙仙",
            "太乙圣",
            "大至圣",
            "太乙圣君",
            "大至圣君",
            "九天玄圣",
            "九天金圣",
            "九天真圣",
            "九天圣",
            "九天散圣",
            "准圣",
            "混元圣人",
            "太乙神将",
            "大至神将",
            "太一神将",
            "太乙天将",
            "大至天将",
            "太一天将",
            "太乙神相",
            "大至神相",
            "太一神相",
            "太乙天相",
            "大至天相",
            "太一天相",
            "太乙神君",
            "大至神君",
            "太一神君",
            "太乙天君",
            "大至天君",
            "太一天君",
            "太乙道君",
            "大至道君",
            "太一道君",
            "太乙帝君",
            "大至帝君",
            "太一帝君",
            "太乙神帝",
            "大至神帝",
            "太一神帝",
            "太乙天帝",
            "大至天帝",
            "太一天帝",
            "太乙神皇",
            "大至神皇",
            "太一神皇",
            "太乙天皇",
            "大至天皇",
            "太一天皇",
            "太乙神王",
            "大至神王",
            "太一神王",
            "太乙天王",
            "大至天王",
            "太一天王",
            "太乙星君",
            "大至星君",
            "太一星君",
            "太乙月君",
            "大至月君",
            "太一月君",
            "太乙日君",
            "大至日君",
            "太一日君",
            "太乙辰君",
            "大至辰君",
            "太一辰君",
            "太乙宿君",
            "大至宿君",
            "太一宿君",
            "天道",
            "大道",
            "混沌圣王",
            "鸿蒙至尊",
            "太初神主",
            "无极道祖",
            "太极仙尊",
            "阴阳法王",
            "五行真君",
            "八卦宗师",
            "九宫真人",
            "十方圣者",
            "百变仙师",
            "千幻神将",
            "万化道君",
            "虚无上人",
            "空灵仙长",
            "寂灭神僧",
            "涅槃佛祖",
            "轮回主宰",
            "造化仙翁",
            "乾坤道人",
            "天地法相",
            "宇宙圣贤",
            "星辰使者",
            "日月神君",
            "山河圣主",
            "江海仙宗",
            "风雷神将",
            "霜雪道君",
            "花鸟真人",
            "虫鱼仙长",
            "草木神翁",
            "金石法王",
            "云雾宗师",
            "烟霞真人",
            "霞光圣者",
            "紫气仙长",
            "青龙神将",
            "白虎神君",
            "朱雀仙师",
            "玄武道长",
            "麒麟圣兽",
            "凤凰神禽",
            "鲲鹏仙羽",
            "蛟龙神鳞",
            "貔貅财神",
            "饕餮食神",
            "睚眦兵神",
            "嘲风建筑神",
            "蒲牢钟神",
            "狻猊火神",
            "狴犴狱神",
            "负屃文神",
            "螭吻水神",
            "腾蛇游神",
            "勾陈天神",
            "螣蛇地神",
            "玄武水神",
            "朱雀火神",
            "白虎金神",
            "青龙木神",
            "黄龙土神",
            "苍龙东神",
            "赤龙南神",
            "白龙西神",
            "墨龙北神",
            "金龙财神",
            "银龙宝神",
            "铜龙运神",
            "铁龙力神",
            "玉龙祥神",
            "珠龙瑞神",
            "翠龙福神",
            "玛瑙龙吉神",
            "琥珀龙顺神",
            "珊瑚龙安神",
            "琉璃龙泰神",
            "水晶龙和神",
            "钻石龙昌神",
            "珍珠龙盛神",
            "翡翠龙兴神",
            "黄金龙隆神",
            "白银龙丰神",
            "青铜龙盛神",
            "钢铁龙强神",
            "玉石龙祥神",
            "玛瑙龙庆神",
            "翡翠龙嘉神",
            "珍珠龙福神",
            "钻石龙贵神",
            "水晶龙宝神",
            "琥珀龙瑞神",
            "珊瑚龙吉神",
            "琉璃龙祥神",
            "云母龙安神",
            "水晶龙泰神",
            "冰晶龙和神",
            "雪花龙清神",
            "雨滴龙润神",
            "露珠龙泽神",
            "甘露龙恩神",
            "朝霞龙辉神",
            "夕阳龙照神",
            "明月龙华神",
            "繁星龙耀神",
            "银河龙瀚神",
            "彩云龙霓神",
            "飞虹龙桥神",
            "雷电龙威神",
            "闪电龙迅神",
            "暴雨龙沛神",
            "微风龙和神",
            "清风龙爽神",
            "暖风龙温神",
            "寒风龙冽神",
            "春风龙生神",
            "夏风龙长神",
            "秋风龙收神",
            "冬风龙藏神",
            "四季龙轮神",
            "昼夜龙恒神",
            "晨昏龙序神",
            "黎明龙启神",
            "正午龙烈神",
            "黄昏龙暮神",
            "深夜龙静神",
            "子时龙初神",
            "丑时龙萌神",
            "寅时龙生神",
            "卯时龙明神",
            "辰时龙升神",
            "巳时龙进神",
            "午时龙旺神",
            "未时龙缓神",
            "申时龙收神",
            "酉时龙成神",
            "戌时龙固神",
            "亥时龙藏神",
            "天干甲龙",
            "天干乙龙",
            "天干丙龙",
            "天干丁龙",
            "天干戊龙",
            "天干己龙",
            "天干庚龙",
            "天干辛龙",
            "天干壬龙",
            "天干癸龙",
            "地支子龙",
            "地支丑龙",
            "地支寅龙",
            "地支卯龙",
            "地支辰龙",
            "地支巳龙",
            "地支午龙",
            "地支未龙",
            "地支申龙",
            "地支酉龙",
            "地支戌龙",
            "地支亥龙",
            "三才天地人龙",
            "四象青龙",
            "五方中央龙",
            "六合八荒龙",
            "七星北斗龙",
            "八封乾坤龙",
            "九州华夏龙",
            "十方世界龙",
            "十二生肖龙",
            "二十四节气龙",
            "三十六计谋龙",
            "七十二变化龙",
            "八十一难渡龙",
            "九九归元龙",
            "百炼成钢龙",
            "千锤百炼龙",
            "万法归宗龙",
            "无上至尊龙"
        ]
        
        # 根据斐波那契数列生成突破所需经验列表
        thresholds = []
        for i in range(len(realms)):
            if i == 0:
                thresholds.append(100)      # 练气 -> 筑基 需要 100
            elif i == 1:
                thresholds.append(200)      # 筑基 -> 金丹 需要 200
            else:
                # 斐波那契逻辑：当前 = 前一个 + 前两个
                val = thresholds[i-1] + thresholds[i-2]
                thresholds.append(val)
        
        return realms, thresholds

def generate_fibonacci_thresholds(num_realms):
    """根据斐波那契数列生成突破所需经验列表"""
    thresholds = []
    for i in range(num_realms):
        if i == 0:
            thresholds.append(100)      # 第一个境界需要100经验
        elif i == 1:
            thresholds.append(200)      # 第二个境界需要200经验
        else:
            # 斐波那契逻辑：当前 = 前一个 + 前两个
            val = thresholds[i-1] + thresholds[i-2]
            thresholds.append(val)
    
    return thresholds

# 1. 从配置文件加载境界名称列表
REALM_NAMES, REALM_THRESHOLDS = load_realms_from_json()

# 为每个境界添加子层级 (0-8，共9个子层)
def generate_sub_realms():
    sub_realms = []
    for idx, realm_name in enumerate(REALM_NAMES):
        for i in range(9):  # 0-8 共9个子层
            sub_realms.append(f"{idx+1}.{realm_name}·{i+1}")
    # 最终境界不划分子层
    sub_realms.append(f"{len(REALM_NAMES)}.{REALM_NAMES[-1]}")  # 最后一个境界保持原样
    return sub_realms

SUB_REALMS = generate_sub_realms()

# 为每个子境界设置突破经验
def generate_sub_thresholds():
    sub_thresholds = []
    for i, base_threshold in enumerate(REALM_THRESHOLDS):
        # 每个主境界分为9个子层，每个子层需要 1/9 的基础突破经验
        if base_threshold == float('inf'):  # 最后一个境界
            sub_step = float('inf')
        else:
            sub_step = base_threshold // 9
        for j in range(9):
            sub_thresholds.append(sub_step)
    # 最后一个境界不需要突破
    sub_thresholds.append(float('inf'))
    return sub_thresholds

SUB_REALM_THRESHOLDS = generate_sub_thresholds()

# 飞升境界等级列表
ASCENSION_LEVELS = [9, 49, 159, 199, 279]

# ==================== 关键词配置 ====================

RANK_KEYWORDS = ["排行榜", "榜单", "排名"]
STATS_KEYWORDS = ["统计", "数据", "修为", "境界", "等级"]
CULTIVATE_KEYWORDS = ["开灵", "打坐", "突破", "修炼", "修行", "修仙"]
HELP_KEYWORDS = ["帮助", "使用说明", "功能"]


def get_help_text() -> str:
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


def build_player_stats_msg(player) -> str:
    return (
        f"📊 修仙统计\n\n"
        f"👤 用户: {player.username}\n"
        f"境界: {player.current_realm_name}\n"
        f"当前修为: {player.exp}\n"
        f"下境界所需: {player.next_threshold if player.next_threshold != float('inf') else 'MAX'}\n"
        f"总突破次数: {player.total_breakthroughs}\n"
        f"总获得修为: {player.total_exp_gained}"
    )


def build_player_status_msg(player) -> str:
    return (
        f"✨ 修炼状态\n\n"
        f"👤 用户: {player.username}\n"
        f"境界: {player.current_realm_name}\n"
        f"修为: {player.exp}/{player.next_threshold if player.next_threshold != float('inf') else 'MAX'}\n"
        f"总突破: {player.total_breakthroughs} 次\n"
        f"总修为: {player.total_exp_gained}"
    )


class CultivationSystem:
    def __init__(self, data_dir=None):
        if data_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(script_dir, "data")
        self.data_dir = data_dir
        self.players = {}
        self._ensure_data_dir_exists()
        self.load_all_players()
    
    def _ensure_data_dir_exists(self):
        """确保数据目录存在"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def load_player(self, qq_id: int, username: str):
        """加载或创建玩家数据"""
        player_file = os.path.join(self.data_dir, f"player_{qq_id}.json")
        
        if os.path.exists(player_file):
            with open(player_file, 'r', encoding='utf-8') as f:
                player_data = json.load(f)
                player = Cultivator(
                    username=player_data.get('username', username),
                    qq_id=qq_id,
                    realm_index=player_data.get('realm_index', 0),
                    exp=player_data.get('exp', 0),
                    last_meditate=player_data.get('last_meditate', ''),
                    total_exp_gained=player_data.get('total_exp_gained', 0),
                    total_breakthroughs=player_data.get('total_breakthroughs', 0),
                    items=player_data.get('items', []),
                    is_soul_opened=player_data.get('is_soul_opened', False),
                    is_ascended=player_data.get('is_ascended', False),
                    ascension_count=player_data.get('ascension_count', 0)
                )
        else:
            player = Cultivator(username, qq_id)
        
        self.players[qq_id] = player
        return player
    
    def save_player(self, player):
        """保存玩家数据"""
        player_file = os.path.join(self.data_dir, f"player_{player.qq_id}.json")
        player_data = {
            'username': player.username,
            'qq_id': player.qq_id,
            'realm_index': player.realm_index,
            'exp': player.exp,
            'last_meditate': player.last_meditate,
            'total_exp_gained': player.total_exp_gained,
            'total_breakthroughs': player.total_breakthroughs,
            'items': player.items,
            'is_soul_opened': player.is_soul_opened,
            'is_ascended': player.is_ascended,
            'ascension_count': player.ascension_count
        }
        
        with open(player_file, 'w', encoding='utf-8') as f:
            json.dump(player_data, f, ensure_ascii=False, indent=2)
    
    def load_all_players(self):
        """加载所有玩家数据到内存缓存"""
        if not os.path.exists(self.data_dir):
            return
        
        for filename in os.listdir(self.data_dir):
            if filename.startswith("player_") and filename.endswith(".json"):
                try:
                    qq_id = int(filename.replace("player_", "").replace(".json", ""))
                    self.load_player(qq_id, f"User_{qq_id}")
                except ValueError:
                    continue
    
    def load_all_players_from_files(self):
        """从文件加载所有玩家数据，不使用缓存 - 用于排行榜等需要最新数据的场景"""
        players = []
        if not os.path.exists(self.data_dir):
            return players
        
        for filename in os.listdir(self.data_dir):
            if filename.startswith("player_") and filename.endswith(".json"):
                try:
                    qq_id = int(filename.replace("player_", "").replace(".json", ""))
                    player_file = os.path.join(self.data_dir, filename)
                    with open(player_file, 'r', encoding='utf-8') as f:
                        player_data = json.load(f)
                        player = Cultivator(
                            username=player_data.get('username', f'User_{qq_id}'),
                            qq_id=qq_id,
                            realm_index=player_data.get('realm_index', 0),
                            exp=player_data.get('exp', 0),
                            last_meditate=player_data.get('last_meditate', ''),
                            total_exp_gained=player_data.get('total_exp_gained', 0),
                            total_breakthroughs=player_data.get('total_breakthroughs', 0),
                            items=player_data.get('items', []),
                            is_soul_opened=player_data.get('is_soul_opened', False)
                        )
                        players.append(player)
                except ValueError:
                    continue
                except Exception as e:
                    print(f"加载玩家文件 {filename} 时出错: {e}")
                    continue
        
        return players
    
    def find_player_by_username(self, target_username):
        """根据用户名查找玩家"""
        for player in self.players.values():
            if player.username.lower() == target_username.lower():
                return player
        return None
    
    def get_ranking(self, top_n=10):
        """获取排行榜"""
        players = self.load_all_players_from_files()
        
        if not players:
            return "暂无玩家数据"
        
        # 按境界排序
        sorted_players = sorted(players, key=lambda p: p.realm_index, reverse=True)
        
        ranking_info = "🏆 修仙排行榜 🏆\n\n"
        for i, player in enumerate(sorted_players[:top_n], 1):
            ranking_info += f"{i}. {player.username} - {player.current_realm_name}\n"
        
        return ranking_info


class Cultivator:
    def __init__(self, username: str, qq_id: int, realm_index: int = 0, exp: int = 0, 
                 last_meditate: str = '', total_exp_gained: int = 0, 
                 total_breakthroughs: int = 0, items: list = None, is_soul_opened: bool = False,
                 is_ascended: bool = False, ascension_count: int = 0):
        self.username = username
        self.qq_id = qq_id
        self.realm_index = realm_index
        self.exp = exp
        self.last_meditate = last_meditate
        self.total_exp_gained = total_exp_gained
        self.total_breakthroughs = total_breakthroughs
        self.items = items if items is not None else []
        self.is_soul_opened = is_soul_opened
        self.is_ascended = is_ascended
        self.ascension_count = ascension_count

    @property
    def current_realm_name(self):
        """获取当前境界名称（包括子境界）"""
        if self.realm_index >= len(SUB_REALMS):
            return f"{SUB_REALMS[-1]} (大圆满)"
        return SUB_REALMS[self.realm_index]

    @property
    def next_threshold(self):
        """获取突破到下一境界所需的经验值"""
        if self.realm_index >= len(SUB_REALM_THRESHOLDS):
            return float('inf')
        return SUB_REALM_THRESHOLDS[self.realm_index]

    def can_meditate(self):
        """检查是否可以打坐"""
        return True

    def open_soul(self):
        """开灵功能 - 踏入仙途"""
        if self.is_soul_opened:
            return "道友已经开灵成功，正在仙途之上修行！"
        
        success_rate = random.randint(1, 100)
        if success_rate <= 80:
            self.is_soul_opened = True
            self.realm_index = 0
            self.exp = 0
            return (
                f"🎉🎉🎉 恭喜【{self.username}】成功开灵！🎉🎉🎉\n"
                f"成功踏入仙途，正式成为【{REALM_NAMES[0]}】修士！\n"
                f"前方路漫漫，愿道友在修仙之路上勇猛精进！"
            )
        else:
            return (
                f"😅【{self.username}】尝试开灵失败...\n"
                f"体内的灵力未能成功激活，需要继续积累灵气，方可踏入仙途。\n"
                f"建议多加修炼，提升体质后再尝试开灵。"
            )

    def meditate(self):
        """打坐功能"""
        if not self.is_soul_opened:
            return "道友尚未开灵，无法进行打坐修炼。请先使用开灵功能踏入仙途。"
        
        current_exp = self.exp
        # 修复：使用对数曲线替代线性/指数曲线，防止老玩家一次获得大量修为
        # 基准值 + log(当前修为+1) * 系数，平衡新手和老玩家
        min_gain = max(10, int(10 + current_exp ** 0.5 * 2))
        max_gain = max(30, int(30 + current_exp ** 0.7 * 5))
        
        gain = random.randint(min_gain, max_gain)
        self.exp += gain
        self.total_exp_gained += gain
        
        msg = f"【{self.username}】闭目打坐，感悟天地灵气...\n"
        msg += f"✨ 修为增加：+{gain} (当前境界 {min_gain}-{max_gain} 范围)\n"

        breakthrough_occurred = False
        while self.realm_index < len(SUB_REALMS) - 1 and self.exp >= self.next_threshold:
            realm_stage = (self.realm_index // 9) + 1
            success_rate = max(0.6, 0.85 - (realm_stage * 0.005))
            
            if random.random() > success_rate:
                loss_amount = self.exp // 2
                self.exp = max(0, self.exp - loss_amount)
                
                failure_messages = [
                    f"\n💥 突破失败！由于心境不稳，修为倒退！\n",
                    f"\n⚡ 突破受阻！天地灵气反噬，修为受损！\n",
                    f"\n🔥 突破失利！体内灵力紊乱，修为减半！\n",
                    f"\n❄️ 突破失败！道心受创，修为大损！\n"
                ]
                msg += random.choice(failure_messages)
                msg += f"💔 修为损失：-{loss_amount}\n"
                msg += f"📊 当前修为：{self.exp} / {self.next_threshold if self.next_threshold != float('inf') else 'MAX'}\n"
                break
            else:
                self.realm_index += 1
                self.total_breakthroughs += 1
                breakthrough_occurred = True
                
                current_realm = SUB_REALMS[self.realm_index]
                msg += f"\n🎉 🎉 🎉 自动突破成功！ 🎉 🎉 🎉\n"
                msg += f"恭喜道友晋升至：【{current_realm}】\n"
        
        msg += f"📊 当前修为：{self.exp} / {self.next_threshold if self.next_threshold != float('inf') else 'MAX'}\n"

        if breakthrough_occurred:
            if self.realm_index < len(SUB_REALMS) - 1:
                msg += f"下一目标：{SUB_REALMS[self.realm_index + 1]} (需要 {self.next_threshold} 修为)"
            else:
                msg += "\n🎉 恭喜道友达到最高境界，已臻至化境，世间再无瓶颈！"
        elif self.realm_index >= len(SUB_REALMS) - 1:
            msg += "\n💡 道友已臻至化境，世间再无瓶颈！"
        else:
            msg += f"\n💡 继续努力修炼，当前境界已达到 {self.exp}/{self.next_threshold} 修为"

        return msg

    def attempt_breakthrough(self):
        """手动突破功能"""
        if not self.is_soul_opened:
            return "道友尚未开灵，无法进行突破。请先使用开灵功能踏入仙途。"

        if self.realm_index >= len(SUB_REALMS) - 1:
            return "🎉 恭喜道友达到最高境界，已臻至化境，世间再无瓶颈！"

        # 检查修为是否足够突破
        if self.exp < self.next_threshold:
            return f"当前修为不足，无法突破。需要 {self.next_threshold} 修为"

        breakthrough_count = 0
        while self.realm_index < len(SUB_REALMS) - 1 and self.exp >= self.next_threshold:
            realm_stage = (self.realm_index // 9) + 1
            success_rate = max(0.6, 0.85 - (realm_stage * 0.005))

            if random.random() > success_rate:
                loss_percentage = random.uniform(0.05, 0.15)
                loss_amount = int(self.exp * loss_percentage)
                self.exp = max(0, self.exp - loss_amount)

                failure_messages = [
                    f"💥 突破失败！走火入魔，修为受损 -{loss_amount} 修为！",
                    f"⚡ 突破失败！经脉受创，流失 -{loss_amount} 修为！",
                    f"🔥 突破失败！灵力反噬，损失 -{loss_amount} 修为！",
                    f"💧 突破失败！根基不稳，消散 -{loss_amount} 修为！"
                ]
                msg = random.choice(failure_messages)
                msg += f"\n当前修为：{self.exp}/{self.next_threshold if self.next_threshold != float('inf') else 'MAX'}"
                return msg

            self.realm_index += 1
            self.total_breakthroughs += 1
            breakthrough_count += 1

        if breakthrough_count > 0:
            msg = f"🎉 手动突破成功！晋升至：{self.current_realm_name}\n"
            msg += f"🎉 累计突破次数：{self.total_breakthroughs} 次"
            return msg
        else:
            return f"当前修为不足，无法突破。需要 {self.next_threshold} 修为"

    def attempt_ascension(self):
        """飞升功能 - 在9、49、159、199、279级对应的大境界可以飞升"""
        if not self.is_soul_opened:
            return "道友尚未开灵，无法飞升。请先使用开灵功能踏入仙途。"
        
        # 计算当前主境界（从1开始）
        current_main_realm = (self.realm_index // 9) + 1
        
        # 检查当前是否在可以飞升的主境界
        if current_main_realm not in ASCENSION_LEVELS:
            return f"❌ 当前主境界【{current_main_realm}级】无法飞升。\n可飞升的主境界为：{', '.join(map(str, ASCENSION_LEVELS))}级\n当前境界：【{self.current_realm_name}】"
        
        # 飞升成功率30%
        if random.randint(1, 100) <= 30:
            # 飞升成功
            self.is_ascended = True
            self.ascension_count += 1
            
            msg = f"🌟🌟🌟 恭喜【{self.username}】成功飞升！ 🌟🌟🌟\n"
            msg += f"从【{current_main_realm}级·{self.current_realm_name}】突破凡尘，成功飞升！\n"
            msg += f"🎊 飞升次数：{self.ascension_count}\n"
            msg += f"📊 当前境界：【{self.current_realm_name}】\n"
            msg += f"⚡ 当前修为：{self.exp}\n"
            if current_main_realm == 279:
                msg += f"💡 279级飞升后可以继续积累修为，但无法突破到更高境界！"
        else:
            # 飞升失败，扣除一半经验
            loss_amount = self.exp // 2
            self.exp = max(0, self.exp - loss_amount)
            
            failure_messages = [
                f"💥【{self.username}】飞升失败！天劫降临，道心受损！\n",
                f"⚡【{self.username}】飞升失败！雷劫未过，修为大损！\n",
                f"🔥【{self.username}】飞升失败！天威难测，根基不稳！\n",
                f"❄️【{self.username}】飞升失败！机缘未到，修为减半！\n"
            ]
            msg = random.choice(failure_messages)
            msg += f"💔 修为损失：-{loss_amount}\n"
            msg += f"📊 当前修为：{self.exp} / {self.next_threshold if self.next_threshold != float('inf') else 'MAX'}\n"
            msg += f"💡 道友请继续修炼，积累足够修为后再尝试飞升！"
        
        return msg

    def get_status(self):
        """获取玩家状态"""
        if not self.is_soul_opened:
            return f"【{self.username}】\n尚未开灵，请用开灵功能踏入仙途。"
        
        ascension_status = f"✅ 已飞升 (第{self.ascension_count}次)" if self.is_ascended else "❌ 未飞升"
        
        msg = f"【{self.username}】\n"
        msg += f"当前境界：{self.current_realm_name}\n"
        msg += f"当前修为：{self.exp} / {self.next_threshold if self.next_threshold != float('inf') else 'MAX'}\n"
        msg += f"总突破次数：{self.total_breakthroughs} 次\n"
        msg += f"总获得修为：{self.total_exp_gained}\n"
        msg += f"🌌 飞升状态：{ascension_status}"
        
        return msg

    def battle(self, opponent):
        """与其他玩家对战"""
        self_power = self.realm_index * 100 + self.exp
        opponent_power = opponent.realm_index * 100 + opponent.exp
        
        total_power = self_power + opponent_power
        if total_power == 0:
            win_prob = 0.5
        else:
            win_prob = self_power / total_power
        
        win_prob = win_prob * 0.7 + random.random() * 0.3
        
        if random.random() < win_prob:
            exp_gain = random.randint(50, 200)
            self.exp += exp_gain
            
            battle_result = f"⚔️ 战斗胜利！【{self.username}】击败了【{opponent.username}】\n"
            battle_result += f"🎉 获得修为奖励：+{exp_gain}\n"
            battle_result += f"当前修为：{self.exp}/{self.next_threshold if self.next_threshold != float('inf') else 'MAX'}"
            
            return battle_result
        else:
            exp_loss = random.randint(20, 100)
            self.exp = max(0, self.exp - exp_loss)
            
            battle_result = f"⚔️ 战斗失败！【{self.username}】败给了【{opponent.username}】\n"
            battle_result += f"💔 战败惩罚：-{exp_loss} 修为\n"
            battle_result += f"当前修为：{self.exp}/{self.next_threshold if self.next_threshold != float('inf') else 'MAX'}"
            
            return battle_result

    def attack(self, opponent):
        """攻击其他玩家"""
        self_power = self.realm_index * 100 + self.exp
        opponent_power = opponent.realm_index * 100 + opponent.exp
        
        total_power = self_power + opponent_power
        if total_power == 0:
            win_prob = 0.5
        else:
            win_prob = self_power / total_power
        
        win_prob = win_prob * 0.7 + random.random() * 0.3
        
        if random.random() < win_prob:
            opponent_loss = opponent.exp // 2
            opponent.exp = max(0, opponent.exp - opponent_loss)
            
            self_loss = self.exp // 3
            self.exp = max(0, self.exp - self_loss)
            
            self.check_and_update_realm_after_attack()
            opponent.check_and_update_realm_after_attack()
            
            attack_result = f"🗡️ 攻击成功！【{self.username}】重创了【{opponent.username}】\n"
            attack_result += f"💥 对方修为损失：-{opponent_loss} (剩余: {opponent.exp})\n"
            attack_result += f"💔 自身修为损失：-{self_loss} (剩余: {self.exp})"
        else:
            opponent_loss = opponent.exp // 3
            opponent.exp = max(0, opponent.exp - opponent_loss)
            
            self_loss = self.exp // 2
            self.exp = max(0, self.exp - self_loss)
            
            self.check_and_update_realm_after_attack()
            opponent.check_and_update_realm_after_attack()
            
            attack_result = f"🛡️ 攻击失败！【{opponent.username}】抵御了【{self.username}】的攻击\n"
            attack_result += f"💥 对方修为损失：-{opponent_loss} (剩余: {opponent.exp})\n"
            attack_result += f"💔 自身修为损失：-{self_loss} (剩余: {self.exp})"
        
        return attack_result

    def check_and_update_realm_after_attack(self):
        """在攻击后检查是否需要更新境界"""
        while self.realm_index > 0 and self.exp < SUB_REALM_THRESHOLDS[self.realm_index]:
            self.realm_index -= 1
