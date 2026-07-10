# ==================== 系统必要导入 ====================
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sdk.pluginsystem import PluginBase, filter_registry
from sdk.core.events import GroupMessageEvent, PrivateMessageEvent

# ==================== 功能层导入 ====================
from .abcapi import WeatherAPI, NewsAPI
from .logic import (
    HELP_TEXT,
    WEATHER_KEYWORDS,
    NEWS_KEYWORDS,
    FORTUNE_KEYWORDS,
    HELP_KEYWORDS,
    build_fortune_segments,
    build_weather_segments,
    build_forecast_segments,
    build_news_segments,
    extract_city_from_weather,
    extract_city_from_forecast,
    match_keyword,
)

logger = logging.getLogger("rqhmain")


class RqhmainPlugin(PluginBase):
    """Rqhmain综合插件 - 运势、随机图、天气、新闻、IP查询等功能"""

    def __init__(self):
        super().__init__()
        self.name = "rqhmain"
        self.version = "2.0.0"
        self.description = "综合插件 - 运势、随机图、天气、新闻、IP查询等功能"
        self.author = "rqh"
        self.enabled = True
        self.config: Dict[str, Any] = {}

    async def on_load(self, api, event_bus, plugin_dir=None):
        await super().on_load(api, event_bus, plugin_dir)
        logger.info(f"已加载, v{self.version}")
        self.config = await self.load_config()
        logger.info(f"配置已加载: {self.config}")

    async def on_unload(self):
        logger.info("卸载中")

    # ==================== 事件入口 ====================

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

    # ==================== 关键词路由 ====================

    async def _process_keywords(self, event: Any, raw_message: str) -> None:
        group_id = getattr(event, "group_id", None)

        # 天气查询
        if match_keyword(raw_message, WEATHER_KEYWORDS):
            await self._handle_weather(event, raw_message, group_id)
            return

        # 新闻查询
        if match_keyword(raw_message, NEWS_KEYWORDS):
            await self._handle_news(event, raw_message, group_id)
            return

        # 运势查询
        if match_keyword(raw_message, FORTUNE_KEYWORDS):
            await self._handle_fortune(event, group_id)
            return

        # 帮助
        if match_keyword(raw_message, HELP_KEYWORDS):
            await self._handle_help(event, raw_message, group_id)

    # ==================== 功能实现 ====================

    async def _handle_weather(
        self,
        event: Any,
        raw_message: str,
        group_id: Optional[int],
    ) -> None:
        if "天气" in raw_message or "气温" in raw_message:
            city = extract_city_from_weather(raw_message)
            if not city:
                msg = "请告诉我您想查询的城市，例如：天气 北京"
                await self._reply(event, group_id, msg)
                return

            try:
                result = WeatherAPI().query_weather(city)
                if result.get("success"):
                    data = result.get("data")
                    if isinstance(data, dict):
                        segments = build_weather_segments(city, data)
                        await self._reply_segments(event, group_id, segments)
                        return
                    msg = f"查询 {city} 天气成功，但数据格式异常"
                else:
                    msg = f"查询 {city} 天气失败: {result.get('error', '未知错误')}"
            except Exception as e:
                msg = f"查询天气时出错: {e}"

            await self._reply(event, group_id, msg)
            return

        # 预报类查询
        city = extract_city_from_forecast(raw_message)
        if not city:
            msg = "请告诉我您想查询的城市"
            await self._reply(event, group_id, msg)
            return

        try:
            result = WeatherAPI().query_weather(city, info_type="forecast")
            if result.get("success"):
                data = result.get("data")
                if isinstance(data, dict):
                    segments = build_forecast_segments(city, data)
                    await self._reply_segments(event, group_id, segments)
                    return
                msg = f"查询 {city} 天气预报成功，但数据格式异常"
            else:
                msg = f"查询 {city} 天气预报失败: {result.get('error', '未知错误')}"
        except Exception as e:
            msg = f"查询天气预报时出错: {e}"

        await self._reply(event, group_id, msg)

    async def _handle_news(
        self,
        event: Any,
        raw_message: str,
        group_id: Optional[int],
    ) -> None:
        try:
            result = NewsAPI().get_news()
            if result:
                segments = build_news_segments(result)
                await self._reply_segments(event, group_id, segments)
                return
            msg = "获取新闻失败，请稍后重试"
        except Exception as e:
            msg = f"获取新闻时出错: {e}"

        await self._reply(event, group_id, msg)

    async def _handle_fortune(self, event: Any, group_id: Optional[int]) -> None:
        try:
            segments = build_fortune_segments()
            await self._reply_segments(event, group_id, segments)
        except Exception as e:
            msg = f"查询运势时出错: {e}"
            await self._reply(event, group_id, msg)

    async def _handle_help(
        self,
        event: Any,
        raw_message: str,
        group_id: Optional[int],
    ) -> None:
        if "指南" in raw_message:
            await self._reply(event, group_id, HELP_TEXT)

    # ==================== 回复辅助 ====================

    async def _reply(self, event: Any, group_id: Optional[int], msg: str) -> None:
        if group_id:
            await self.api.send_group_message(group_id=group_id, message=msg)
        else:
            await self.api.send_private_message(user_id=event.user_id, message=msg)

    async def _reply_segments(
        self,
        event: Any,
        group_id: Optional[int],
        segments: list,
    ) -> None:
        if group_id:
            await self.api.send_group_message_segments(
                group_id=group_id, segments=segments
            )
        else:
            await self.api.send_private_message_segments(
                user_id=event.user_id, segments=segments
            )
