"""适配器模块测试

覆盖 ``sdk.adapter`` 的后端注册表与 ``AdapterResolver`` 的连接参数解析，
以及 ``ConfigManager`` 对解析器的委托方法。
"""

from __future__ import annotations

from typing import Any

import pytest

from sdk.adapter import BACKENDS, DEFAULT_BACKEND, AdapterResolver, get_backend
from sdk.config import ConfigManager


class _FakeConfig:
    """最小 ConfigLike 实现，支持点号路径读写"""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = data if data is not None else {}

    def get(self, key: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, key: str, value: Any) -> None:
        parts: list[str] = key.split(".")
        node: dict[str, Any] = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value


# ==================== 后端注册表 ====================


def test_default_backend_is_napcat() -> None:
    """缺省后端应为 napcat"""
    assert DEFAULT_BACKEND == "napcat"
    assert get_backend().name == "napcat"
    assert get_backend(None).name == "napcat"
    assert get_backend("").name == "napcat"


def test_backend_name_is_case_insensitive() -> None:
    """后端名称解析不区分大小写，并忽略首尾空白"""
    assert get_backend("SnowLuma").name == "snowluma"
    assert get_backend("  NAPCAT ").name == "napcat"


def test_unknown_backend_raises() -> None:
    """未注册的后端应抛 ValueError，并列出可选值"""
    with pytest.raises(ValueError) as excinfo:
        get_backend("nonexistent")
    assert "napcat" in str(excinfo.value)
    assert "snowluma" in str(excinfo.value)


def test_backend_default_ports() -> None:
    """NapCat / SnowLuma 的默认端口沿用各自约定"""
    assert BACKENDS["napcat"].default_ws_uri == "ws://localhost:3002"
    assert BACKENDS["snowluma"].default_ws_uri == "ws://localhost:3001"


def test_backend_auto_start_capability() -> None:
    """NapCat 可由框架自动启动，SnowLuma 不可"""
    assert BACKENDS["napcat"].auto_start_capable is True
    assert BACKENDS["snowluma"].auto_start_capable is False


def test_backend_config_section_matches_name() -> None:
    """各后端的配置段名应与后端名一致"""
    for name, spec in BACKENDS.items():
        assert spec.name == name
        assert spec.config_section == name


# ==================== 连接参数解析 ====================


def test_resolver_defaults_to_napcat() -> None:
    """空配置下解析器回落到默认后端"""
    resolver = AdapterResolver(_FakeConfig())
    assert resolver.name == "napcat"
    assert resolver.backend.display_name == "NapCat"


def test_ws_uri_falls_back_to_backend_default() -> None:
    """配置段缺失时回落到该后端默认地址"""
    assert AdapterResolver(_FakeConfig()).ws_uri() == "ws://localhost:3002"

    cfg = _FakeConfig({"adapter": "snowluma"})
    assert AdapterResolver(cfg).ws_uri() == "ws://localhost:3001"


def test_ws_uri_reads_backend_section() -> None:
    """按当前后端读取各自配置段的 ws_url"""
    cfg = _FakeConfig({
        "napcat": {"ws_url": "ws://127.0.0.1:9000"},
        "snowluma": {"ws_url": "ws://127.0.0.1:9001"},
    })
    assert AdapterResolver(cfg).ws_uri() == "ws://127.0.0.1:9000"

    cfg.set("adapter", "snowluma")
    assert AdapterResolver(cfg).ws_uri() == "ws://127.0.0.1:9001"


def test_ws_token_defaults_to_empty() -> None:
    """未配置令牌时返回空串"""
    assert AdapterResolver(_FakeConfig()).ws_token() == ""


def test_ws_token_reads_backend_section() -> None:
    """按当前后端读取各自配置段的 access_token"""
    cfg = _FakeConfig({
        "adapter": "snowluma",
        "napcat": {"access_token": "napcat-token"},
        "snowluma": {"access_token": "snowluma-token"},
    })
    assert AdapterResolver(cfg).ws_token() == "snowluma-token"


def test_set_backend_writes_config() -> None:
    """切换后端只写配置，不做持久化"""
    cfg = _FakeConfig()
    AdapterResolver(cfg).set_backend("snowluma")
    assert cfg.get("adapter") == "snowluma"


def test_set_backend_unknown_raises() -> None:
    """切换到未注册后端应抛 ValueError"""
    with pytest.raises(ValueError):
        AdapterResolver(_FakeConfig()).set_backend("bad")


# ==================== 多实例 ====================


def test_instances_empty_by_default() -> None:
    """无多实例配置时返回空列表"""
    resolver = AdapterResolver(_FakeConfig())
    assert resolver.instances() == []
    assert resolver.active_index() == 0


def test_instances_non_list_is_ignored() -> None:
    """instances 字段类型非法时按空列表处理"""
    cfg = _FakeConfig({"napcat": {"instances": "not-a-list"}})
    assert AdapterResolver(cfg).instances() == []


def test_active_index_non_int_falls_back_to_zero() -> None:
    """active 字段类型非法时按 0 处理"""
    cfg = _FakeConfig({"napcat": {"active": "1"}})
    assert AdapterResolver(cfg).active_index() == 0


def test_active_instance_overrides_section_uri() -> None:
    """配置了多实例时从 active 实例读取 ws_uri"""
    cfg = _FakeConfig({
        "napcat": {
            "ws_url": "ws://section:3002",
            "instances": [
                {"name": "一号", "ws_uri": "ws://one:3002", "ws_token": "t1"},
                {"name": "二号", "ws_uri": "ws://two:3002", "ws_token": "t2"},
            ],
            "active": 1,
        }
    })
    resolver = AdapterResolver(cfg)
    assert resolver.ws_uri() == "ws://two:3002"
    assert resolver.ws_token() == "t2"


def test_active_instance_missing_uri_falls_back_to_default() -> None:
    """实例未配置 ws_uri 时回落到后端默认地址"""
    cfg = _FakeConfig({
        "napcat": {"instances": [{"name": "一号"}], "active": 0}
    })
    assert AdapterResolver(cfg).ws_uri() == "ws://localhost:3002"


def test_out_of_range_active_ignores_instances() -> None:
    """active 越界时不使用实例，回落到普通配置段"""
    cfg = _FakeConfig({
        "napcat": {
            "ws_url": "ws://section:3002",
            "instances": [{"ws_uri": "ws://one:3002"}],
            "active": 5,
        }
    })
    assert AdapterResolver(cfg).ws_uri() == "ws://section:3002"


def test_set_active_writes_config() -> None:
    """切换实例写入 active 索引"""
    cfg = _FakeConfig({
        "napcat": {"instances": [{"name": "a"}, {"name": "b"}], "active": 0}
    })
    AdapterResolver(cfg).set_active(1)
    assert cfg.get("napcat.active") == 1


def test_set_active_out_of_range_raises() -> None:
    """实例索引越界时抛 ValueError"""
    cfg = _FakeConfig({"napcat": {"instances": [{"name": "a"}]}})
    resolver = AdapterResolver(cfg)
    with pytest.raises(ValueError):
        resolver.set_active(1)
    with pytest.raises(ValueError):
        resolver.set_active(-1)


# ==================== ConfigManager 委托 ====================


def _make_manager(tmp_path, content: str) -> ConfigManager:
    """在临时目录生成 config.yaml 并加载"""
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return ConfigManager(str(path))


def test_config_manager_backend_defaults(tmp_path) -> None:
    """空配置文件下使用默认后端与默认地址"""
    manager = _make_manager(tmp_path, "")
    assert manager.get_backend_name() == "napcat"
    assert manager.get_ws_uri() == "ws://localhost:3002"
    assert manager.get_ws_token() == ""


def test_config_manager_reads_snowluma_section(tmp_path) -> None:
    """adapter: snowluma 时读取 snowluma 段"""
    manager = _make_manager(
        tmp_path,
        "adapter: snowluma\n"
        "snowluma:\n"
        "  ws_url: ws://127.0.0.1:4001\n"
        "  access_token: snow-token\n",
    )
    assert manager.get_backend_name() == "snowluma"
    assert manager.get_ws_uri() == "ws://127.0.0.1:4001"
    assert manager.get_ws_token() == "snow-token"


def test_config_manager_set_backend_persists(tmp_path) -> None:
    """set_backend 写入磁盘，重新加载后仍生效"""
    manager = _make_manager(tmp_path, "")
    manager.set_backend("snowluma")
    assert manager.get_backend_name() == "snowluma"

    reloaded = ConfigManager(str(tmp_path / "config.yaml"))
    assert reloaded.get_backend_name() == "snowluma"


def test_config_manager_snowluma_instance_helpers(tmp_path) -> None:
    """SnowLuma 多实例辅助方法可读可写"""
    manager = _make_manager(
        tmp_path,
        "adapter: snowluma\n"
        "snowluma:\n"
        "  instances:\n"
        "    - name: 一号\n"
        "      ws_uri: ws://one:3001\n"
        "    - name: 二号\n"
        "      ws_uri: ws://two:3001\n"
        "  active: 0\n",
    )
    assert len(manager.get_snowluma_instances()) == 2
    assert manager.get_active_snowluma_index() == 0
    assert manager.get_ws_uri() == "ws://one:3001"

    manager.set_active_snowluma(1)
    assert manager.get_active_snowluma_index() == 1
    assert manager.get_ws_uri() == "ws://two:3001"
