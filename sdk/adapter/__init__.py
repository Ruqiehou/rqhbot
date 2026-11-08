"""
RqhBot SDK —— 适配器模块

封装 OneBot 11 实现端（NapCat / SnowLuma 等）的注册表与连接参数解析，
与具体配置存储解耦。
"""

from __future__ import annotations

from .backends import BACKENDS, DEFAULT_BACKEND, BackendSpec, get_backend
from .resolver import AdapterResolver, ConfigLike

__all__: list[str] = [
    "BACKENDS",
    "DEFAULT_BACKEND",
    "AdapterResolver",
    "BackendSpec",
    "ConfigLike",
    "get_backend",
]
