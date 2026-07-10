from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sdk.core import MessageSegment

logger = logging.getLogger("rqhmain")


# ==================== 数据加载 ====================

def _load_json_resource(name: str) -> Any:
    base = Path(__file__).resolve().parent
    path = base / name
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.warning("资源 %s 加载失败", name)
        return []


CSYS = _load_json_resource("csys.json")
CSMSWORD = _load_json_resource("csmsword.json")

try:
    _help_path = Path(__file__).resolve().parent / "help.md"
    HELP_TEXT = _help_path.read_text(encoding="utf-8")
except Exception:
    HELP_TEXT = "帮助文档加载失败"


# ==================== 运势逻辑 ====================

def build_fortune_segments() -> List[Dict[str, Any]]:
    """构建运势图文消息段"""
    if not isinstance(CSYS, list) or not CSYS:
        return [MessageSegment.text("运势数据加载失败，请稍后重试")]

    fortune = random.choice(CSYS)
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

    segments: List[Dict[str, Any]] = [
        MessageSegment.text("✨ 今日运势\n\n"),
    ]
    if stars and type_:
        segments.append(MessageSegment.text(f"{stars} {type_}\n"))
    if desc:
        segments.append(MessageSegment.text(f"🔮 {desc}\n\n"))

    tup_dir = Path(__file__).resolve().parent / "tup"
    if tup_dir.is_dir():
        images = [
            f for f in os.listdir(tup_dir)
            if f.lower().endswith((".jpg", ".png", ".gif", ".jpeg"))
        ]
        if images:
            img = random.choice(images)
            segments.append(
                MessageSegment.image(
                    f"file:///{os.path.join(tup_dir, img).replace(os.sep, '/')}"
                )
            )

    return segments


# ==================== 天气逻辑 ====================

def build_weather_segments(city: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    lines = [f"📍 {city} 当前天气"]
    if "temp" in data:
        lines.append(f"温度: {data['temp']}°C")
    if "humidity" in data:
        lines.append(f"湿度: {data['humidity']}%")
    if "wind" in data:
        lines.append(f"风力: {data['wind']}")
    if "condition" in data:
        lines.append(f"天气: {data['condition']}")
    lines.append("数据来源: 52vmy API")
    return [MessageSegment.text("\n".join(lines))]


def build_forecast_segments(city: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    lines = [f"📍 {city} 天气预报"]
    forecast = data.get("forecast", [])
    if isinstance(forecast, list):
        for i, day in enumerate(forecast[:3]):
            if isinstance(day, dict):
                date = day.get("date", "未知日期")
                temp = day.get("temp", "未知温度")
                condition = day.get("condition", "未知天气")
                lines.append(f"{i + 1}. {date}: {temp}, {condition}")
    lines.append("数据来源: 52vmy API")
    return [MessageSegment.text("\n".join(lines))]


# ==================== 新闻逻辑 ====================

def build_news_segments(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    lines = ["📰 60秒读懂世界\n"]
    if "title" in result:
        lines.append(f"标题: {result['title']}\n")
    content = result.get("content")
    if isinstance(content, list):
        for i, item in enumerate(content[:10], 1):
            if isinstance(item, dict):
                title = item.get("title", "")
                if title:
                    lines.append(f"{i}. {title}")
            elif isinstance(item, str):
                lines.append(f"{i}. {item[:50]}...")
    elif isinstance(content, str):
        for i, line in enumerate(content.split("\n")[:10], 1):
            lines.append(f"{i}. {line[:50]}...")
    lines.append("\n数据来源: 52vmy API")
    return [MessageSegment.text("\n".join(lines))]


# ==================== 关键词匹配辅助 ====================

WEATHER_KEYWORDS = ["天气", "气温", "预报", "降雨", "湿度", "风力"]
NEWS_KEYWORDS = ["新闻", "资讯", "头条", "热点", "60秒", "新闻60秒"]
FORTUNE_KEYWORDS = ["运势", "八字", "命理", "紫微", "星座", "塔罗", "今日运势", "运势查询"]
HELP_KEYWORDS = ["帮助", "使用说明", "功能"]


def match_keyword(text: str, keywords: List[str]) -> bool:
    return any(kw in text for kw in keywords)


def extract_city_from_weather(text: str) -> Optional[str]:
    """从天气查询文本中提取城市名"""
    for kw in ["天气", "气温"]:
        if kw in text:
            city = text.replace(kw, "").strip()
            if city:
                return city
    return None


def extract_city_from_forecast(text: str) -> Optional[str]:
    """从天气预报文本中提取城市名"""
    city = text
    for kw in ["预报", "降雨", "湿度", "风力"]:
        city = city.replace(kw, "")
    city = city.strip()
    return city if city else None
