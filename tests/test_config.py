"""配置模块测试"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sdk.config.config import Config, ConfigManager

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestConfigManager:
    """ConfigManager 测试"""

    def test_init_with_nonexistent_file(self, tmp_path: Path) -> None:
        """测试不存在的配置文件"""
        config_path = str(tmp_path / "nonexistent.yaml")
        manager = ConfigManager(config_path)
        assert manager.config == {}

    def test_get_nested_key(self, tmp_path: Path) -> None:
        """测试获取嵌套键值"""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("napcat:\n  ws_url: ws://test:3001\n", encoding="utf-8")

        manager = ConfigManager(str(config_file))
        assert manager.get("napcat.ws_url") == "ws://test:3001"

    def test_get_default_value(self, tmp_path: Path) -> None:
        """测试默认值"""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("key: value\n", encoding="utf-8")

        manager = ConfigManager(str(config_file))
        assert manager.get("nonexistent", "default") == "default"

    def test_set_and_save(self, tmp_path: Path) -> None:
        """测试设置并保存"""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("", encoding="utf-8")

        manager = ConfigManager(str(config_file))
        manager.set("new_key", "new_value")
        manager.save()

        manager2 = ConfigManager(str(config_file))
        assert manager2.get("new_key") == "new_value"


class TestConfig:
    """Config 类测试"""

    def test_constants_exist(self) -> None:
        """测试常量存在"""
        assert hasattr(Config, "NAPCAT_WS_URL")
        assert hasattr(Config, "NAPCAT_ACCESS_TOKEN")
        assert hasattr(Config, "LOG_LEVEL")
        assert hasattr(Config, "LOG_DIR")

    def test_get_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试获取环境变量"""
        monkeypatch.setenv("TEST_KEY", "test_value")
        assert Config.get("TEST_KEY") == "test_value"

    def test_get_env_default(self) -> None:
        """测试环境变量默认值"""
        assert Config.get("NONEXISTENT_KEY", "default") == "default"

    def test_get_bool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试布尔值转换"""
        monkeypatch.setenv("BOOL_TRUE", "true")
        monkeypatch.setenv("BOOL_FALSE", "false")
        monkeypatch.setenv("BOOL_ONE", "1")

        assert Config.get_bool("BOOL_TRUE") is True
        assert Config.get_bool("BOOL_FALSE") is False
        assert Config.get_bool("BOOL_ONE") is True
        assert Config.get_bool("NONEXISTENT", False) is False
