"""
OneBot 后端注册表（兼容垫片）

实现已迁移到 :mod:`sdk.adapter`，此处保留旧导入路径的向后兼容。
"""

from __future__ import annotations

from sdk.adapter.backends import BACKENDS, DEFAULT_BACKEND, BackendSpec, get_backend

__all__: list[str] = [
    "BACKENDS",
    "DEFAULT_BACKEND",
    "BackendSpec",
    "get_backend",
]
