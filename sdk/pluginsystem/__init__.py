"""
RqhBot SDK —— 插件系统模块
提供插件开发所需的核心功能，包括：
  - PluginBase: 插件基类，插件必须继承此类
  - PluginManager: 基础插件管理器（旧版）
  - HotReloadPluginManager: 支持热重载的插件管理器（推荐）
  - filter_registry: 过滤器装饰器注册表
"""

from __future__ import annotations

from .plugin_base import (
    PluginBase,
    PluginManager,
    filter_registry,
    group_server,
    message_filter,
    private_server,
)
from .plugin_manager import HotReloadPluginManager

__all__: list[str] = [
    "HotReloadPluginManager",
    "PluginBase",
    "PluginManager",
    "filter_registry",
    "group_server",
    "message_filter",
    "private_server",
]
