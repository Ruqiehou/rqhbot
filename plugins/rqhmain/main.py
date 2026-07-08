# ==================== 系统必要导入 ====================
import os
import sys
import json
import random
import logging
from sdk.pluginsystem import PluginBase, filter_registry
from sdk.core.events import GroupMessageEvent, PrivateMessageEvent
from sdk.core import MessageSegment

# ==================== 功能自主导入 ====================
# 添加插件目录到 Python 路径，确保本地模块可导入
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from .abcapi import *
from zm import zimu

logger = logging.getLogger("rqhmain")

config_dir = os.path.dirname(__file__)
with open(os.path.join(config_dir, "csys.json"), "r", encoding="utf-8") as f:
    csys = json.load(f)
with open(os.path.join(config_dir, "csmsword.json"), "r", encoding="utf-8") as f:
    csmsword = json.load(f)
with open(os.path.join(config_dir, "help.md"), "r", encoding="utf-8") as f:
    helpmd = f.read()
    helptxt = str(helpmd)


class RqhmainPlugin(PluginBase):
    """Rqhmain综合插件 - 运势、随机图、天气、新闻、IP查询等功能"""

    def __init__(self):
        super().__init__()
        self.name = "rqhmain"
        self.version = "2.0.0"
        self.description = "综合插件 - 运势、随机图、天气、新闻、IP查询等功能"
        self.author = "rqh"
        self.enabled = True
        self.config = {}

        self.weather_keywords = ["天气", "气温", "预报", "降雨", "湿度", "风力"]
        self.news_keywords = ["新闻", "资讯", "头条", "热点", "60秒", "新闻60秒"]
        self.fortune_keywords = ["运势", "八字", "命理", "紫微", "星座", "塔罗", "今日运势", "运势查询"]
        self.help_keywords = ["帮助", "使用说明", "功能"]

    async def on_load(self, api, event_bus, plugin_dir=None):
        """插件加载时调用"""
        await super().on_load(api, event_bus, plugin_dir)
        logger.info(f"已加载, v{self.version}")
        self.config = await self.load_config()
        logger.info(f"配置已加载: {self.config}")

    async def on_unload(self):
        """插件卸载时调用"""
        logger.info(f"卸载中")

    @filter_registry.group_server
    async def rqhbase_group(self, event: GroupMessageEvent):
        raw_message = event.message.plain_text.strip()
        logger.info(f"群消息: {event.user_id}: {raw_message}")
        await self._process_keywords(event, raw_message)

    @filter_registry.private_server
    async def rqhbase_private(self, event: PrivateMessageEvent):
        raw_message = event.message.plain_text.strip()
        logger.info(f"私聊消息: {event.user_id}: {raw_message}")
        await self._process_keywords(event, raw_message)

    async def _process_keywords(self, event, raw_message: str):
        """处理用户关键词"""
        group_id = getattr(event, 'group_id', None)

        # 天气查询
        if any(keyword in raw_message for keyword in self.weather_keywords):
            if "天气" in raw_message or "气温" in raw_message:
                city = raw_message.replace("天气", "").replace("气温", "").strip()
                if not city:
                    msg = "请告诉我您想查询的城市，例如：天气 北京"
                    if group_id:
                        await self.api.send_group_message(group_id=group_id, message=msg)
                    else:
                        await self.api.send_private_message(user_id=event.user_id, message=msg)
                    return
                # 查询天气
                try:
                    client = WeatherAPI()
                    result = client.query_weather(city)
                    if result["success"]:
                        data = result["data"]
                        if isinstance(data, dict):
                            msg = f"📍 {city} 当前天气\n"
                            if "temp" in data:
                                msg += f"温度: {data['temp']}°C\n"
                            if "humidity" in data:
                                msg += f"湿度: {data['humidity']}%\n"
                            if "wind" in data:
                                msg += f"风力: {data['wind']}\n"
                            if "condition" in data:
                                msg += f"天气: {data['condition']}\n"
                            msg += "数据来源: 52vmy API"
                        else:
                            msg = f"查询 {city} 天气成功，但数据格式异常"
                    else:
                        msg = f"查询 {city} 天气失败: {result.get('error', '未知错误')}"
                except Exception as e:
                    msg = f"查询天气时出错: {str(e)}"
                if group_id:
                    await self.api.send_group_message(group_id=group_id, message=msg)
                else:
                    await self.api.send_private_message(user_id=event.user_id, message=msg)

            elif any(kw in raw_message for kw in ["预报", "降雨", "湿度", "风力"]):
                city = raw_message
                for kw in ["预报", "降雨", "湿度", "风力"]:
                    city = city.replace(kw, "")
                city = city.strip()
                if not city:
                    msg = "请告诉我您想查询的城市"
                    if group_id:
                        await self.api.send_group_message(group_id=group_id, message=msg)
                    else:
                        await self.api.send_private_message(user_id=event.user_id, message=msg)
                    return
                # 查询天气预报
                try:
                    client = WeatherAPI()
                    result = client.query_weather(city, info_type="forecast")
                    if result["success"]:
                        data = result["data"]
                        if isinstance(data, dict):
                            msg = f"📍 {city} 天气预报\n"
                            if "forecast" in data:
                                forecast = data["forecast"]
                                if isinstance(forecast, list) and len(forecast) > 0:
                                    for i, day in enumerate(forecast[:3]):
                                        if isinstance(day, dict):
                                            date = day.get("date", "未知日期")
                                            temp = day.get("temp", "未知温度")
                                            condition = day.get("condition", "未知天气")
                                            msg += f"{i+1}. {date}: {temp}, {condition}\n"
                            msg += "数据来源: 52vmy API"
                        else:
                            msg = f"查询 {city} 天气预报成功，但数据格式异常"
                    else:
                        msg = f"查询 {city} 天气预报失败: {result.get('error', '未知错误')}"
                except Exception as e:
                    msg = f"查询天气预报时出错: {str(e)}"
                if group_id:
                    await self.api.send_group_message(group_id=group_id, message=msg)
                else:
                    await self.api.send_private_message(user_id=event.user_id, message=msg)

        # 新闻查询
        elif any(keyword in raw_message for keyword in self.news_keywords):
            if "新闻" in raw_message or "60秒" in raw_message:
                try:
                    news_client = NewsAPI()
                    result = news_client.get_news()
                    if result:
                        msg = "📰 60秒读懂世界\n\n"
                        if "title" in result:
                            msg += f"标题: {result['title']}\n\n"
                        if "content" in result:
                            content = result["content"]
                            if isinstance(content, list):
                                for i, item in enumerate(content[:10], 1):
                                    if isinstance(item, dict):
                                        title = item.get("title", "")
                                        if title:
                                            msg += f"{i}. {title}\n"
                                    elif isinstance(item, str):
                                        msg += f"{i}. {item[:50]}...\n"
                            elif isinstance(content, str):
                                lines = content.split("\n")[:10]
                                for i, line in enumerate(lines, 1):
                                    msg += f"{i}. {line[:50]}...\n"
                        msg += "\n数据来源: 52vmy API"
                    else:
                        msg = "获取新闻失败，请稍后重试"
                except Exception as e:
                    msg = f"获取新闻时出错: {str(e)}"
                if group_id:
                    await self.api.send_group_message(group_id=group_id, message=msg)
                else:
                    await self.api.send_private_message(user_id=event.user_id, message=msg)

        # 运势查询
        elif any(keyword in raw_message for keyword in self.fortune_keywords):
            if "运势" in raw_message or "今日运势" in raw_message:
                try:
                    user_id = str(event.user_id)
                    if not isinstance(csys, list) or len(csys) == 0:
                        msg = "运势数据加载失败，请稍后重试"
                        if group_id:
                            await self.api.send_group_message(group_id=group_id, message=msg)
                        else:
                            await self.api.send_private_message(user_id=event.user_id, message=msg)
                        return

                    fortune = random.choice(csys)
                    stars, type_, desc = "", "", ""

                    if isinstance(fortune, str):
                        if "★" in fortune:
                            parts = fortune.split(" ", 2)
                            if len(parts) >= 3:
                                stars, type_, desc = parts[0], parts[1], parts[2]
                            else:
                                desc = fortune
                        else:
                            desc = fortune
                    elif isinstance(fortune, dict):
                        stars = fortune.get("stars", "")
                        type_ = fortune.get("type", "")
                        desc = fortune.get("desc", "")

                    # 构建图文混排消息
                    segments = [MessageSegment.text(f"✨ 今日运势\n\n")]
                    if stars and type_:
                        segments.append(MessageSegment.text(f"{stars} {type_}\n"))
                    if desc:
                        segments.append(MessageSegment.text(f"🔮 {desc}\n\n"))

                    # 随机配图
                    tup_dir = os.path.join(os.path.dirname(__file__), "tup")
                    if os.path.isdir(tup_dir):
                        images = [f for f in os.listdir(tup_dir) if f.lower().endswith(('.jpg', '.png', '.gif', '.jpeg'))]
                        if images:
                            img = random.choice(images)
                            segments.append(MessageSegment.image(f"file:///{os.path.join(tup_dir, img).replace(os.sep, '/')}"))

                    if group_id:
                        await self.api.send_group_message_segments(group_id=group_id, segments=segments)
                    else:
                        await self.api.send_private_message_segments(user_id=event.user_id, segments=segments)
                except Exception as e:
                    msg = f"查询运势时出错: {str(e)}"
                    if group_id:
                        await self.api.send_group_message(group_id=group_id, message=msg)
                    else:
                        await self.api.send_private_message(user_id=event.user_id, message=msg)

        # 帮助
        elif any(keyword in raw_message for keyword in self.help_keywords):
            if "指南" in raw_message:
                if group_id:
                    await self.api.send_group_message(group_id=group_id, message=helptxt)
                else:
                    await self.api.send_private_message(user_id=event.user_id, message=helptxt)
