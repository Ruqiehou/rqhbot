"""
客户端运行参数

把「连接参数 / 重连策略 / API 超时」等可调项收拢为一个不可变配置对象，
由调用方（BotClient / 使用方）显式注入 ``OneBotClient``，
使核心层不再依赖全局 ``config_manager`` 单例。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


class ConfigLike(Protocol):
    """构造 ``ClientSettings`` 所需的最小配置接口"""

    def get(self, key: str, default: Any = None) -> Any:
        """读取配置值（支持点号路径）"""
        ...


# 部分 API 在群/好友数量大时响应较慢，单独放宽超时
DEFAULT_ACTION_TIMEOUTS: dict[str, float] = {
    "get_group_list": 60.0,
    "get_group_member_list": 60.0,
    "get_friend_list": 60.0,
    "get_group_msg_history": 60.0,
    "get_friend_msg_history": 60.0,
    "send_group_msg": 15.0,
    "send_private_msg": 15.0,
    "delete_msg": 15.0,
}


def _coerce(value: Any, cast: Any, default: Any) -> Any:
    """把配置值安全转换为目标类型，缺失或非法时回退默认值"""
    if value is None:
        return default
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def _coerce_timeout(raw: Any) -> float | None:
    """把配置值转为正数超时秒数，非法值返回 None"""
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _parse_action_timeouts(raw: Any) -> dict[str, float]:
    """解析 ``settings.api_timeout``：支持标量或 {action: 秒数} 字典"""
    if isinstance(raw, dict):
        parsed: dict[str, float] = {}
        for key, value in raw.items():
            seconds = _coerce_timeout(value)
            if seconds is not None:
                parsed[str(key)] = seconds
        return parsed
    seconds = _coerce_timeout(raw)
    return {"default": seconds} if seconds is not None else {}


@dataclass(frozen=True)
class ClientSettings:
    """客户端运行参数快照

    构造后不再读取配置文件，配置热更新需要重新构造并注入新的实例。
    """

    auto_reconnect: bool = True
    max_reconnect_attempts: int = 5
    reconnect_delay: float = 3.0
    reconnect_max_rounds: int = 3
    ping_interval: float = 25.0
    ping_timeout: float = 10.0
    close_timeout: float = 5.0
    default_api_timeout: float = 30.0
    action_timeouts: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_ACTION_TIMEOUTS)
    )
    # 环境变量回退（未显式传入 ws_url / access_token 时使用）
    ws_url: str = ""
    access_token: str = ""

    @classmethod
    def from_env(cls) -> ClientSettings:
        """仅从环境变量构造（保持旧版 ``Config`` 的回退行为）"""
        return cls(
            ws_url=os.getenv("NAPCAT_WS_URL", ""),
            access_token=os.getenv("NAPCAT_ACCESS_TOKEN", ""),
        )

    @classmethod
    def from_config(cls, config: ConfigLike) -> ClientSettings:
        """从配置对象快照出运行参数

        取值映射：

        - ``settings.auto_reconnect`` → ``auto_reconnect``
        - ``settings.max_reconnect_attempts`` → ``max_reconnect_attempts``
        - ``settings.reconnect_interval`` → ``reconnect_delay``
        - ``settings.api_timeout`` → ``action_timeouts``
        """
        raw_timeouts = _parse_action_timeouts(config.get("settings.api_timeout", {}))
        merged: dict[str, float] = dict(DEFAULT_ACTION_TIMEOUTS)
        merged.update(raw_timeouts)

        return cls(
            auto_reconnect=bool(config.get("settings.auto_reconnect", True)),
            max_reconnect_attempts=_coerce(
                config.get("settings.max_reconnect_attempts"), int, 5
            ),
            reconnect_delay=_coerce(
                config.get("settings.reconnect_interval"), float, 3.0
            ),
            action_timeouts=merged,
            ws_url=os.getenv("NAPCAT_WS_URL", ""),
            access_token=os.getenv("NAPCAT_ACCESS_TOKEN", ""),
        )

    def timeout_for(self, action: str, fallback: float) -> float:
        """按 API action 解析超时秒数

        优先级：``action_timeouts[action]`` > ``action_timeouts["default"]``
        > ``fallback``。
        """
        configured = self.action_timeouts.get(action)
        if configured is not None:
            return configured
        configured_default = self.action_timeouts.get("default")
        if configured_default is not None:
            return configured_default
        return fallback


__all__: list[str] = [
    "DEFAULT_ACTION_TIMEOUTS",
    "ClientSettings",
    "ConfigLike",
]
