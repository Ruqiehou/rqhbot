"""
RqhBot SDK —— 配置模块
提供配置管理、适配器后端注册表与日志设置
"""

from __future__ import annotations

from sdk.adapter import BACKENDS, DEFAULT_BACKEND, BackendSpec, get_backend

from .config import (
    Config,
    ConfigManager,
    config_manager,
    get_logger,
    setup_logging,
)

__all__: list[str] = [
    "BACKENDS",
    "DEFAULT_BACKEND",
    "BackendSpec",
    "Config",
    "ConfigManager",
    "config_manager",
    "get_backend",
    "get_logger",
    "setup_logging",
]
