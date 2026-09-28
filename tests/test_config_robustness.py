"""ConfigManager 健壮性回归测试。

覆盖两个已确认缺陷：

* DEFECT 1 —— ``_save_config`` 使用默认（不安全）dumper，而 ``_load_config`` 使用
  ``yaml.safe_load``。元组/集合/自定义对象会被写成 ``!!python/tuple`` 等标签，
  ``safe_load`` 读不回来 → 异常被吞掉、``self.config`` 变成 ``{}``，
  下一次 ``save()`` 就把 ``config.yaml`` 覆盖成 ``{}``，无关配置永久丢失。
* DEFECT 2 —— 中间键为 ``null`` 或标量（手写配置常见）时，``set()`` 抛出裸
  ``TypeError: 'NoneType' object does not support item assignment``，
  且 ``set_*`` 包装方法没有任何保护。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from sdk.config.config import ConfigManager

VALID_CONFIG = (
    "napcat:\n"
    "  ws_url: ws://test:3002\n"
    "  access_token: token-value\n"
    "  bot_uin: '123456'\n"
    "bot:\n"
    "  load_plugins: true\n"
    "  plugin_dir: plugins\n"
    "logging:\n"
    "  level: INFO\n"
    "settings:\n"
    "  debug: false\n"
)

# 旧版不安全 dumper 写出的内容：safe_load 无法构造 tag:yaml.org,2002:python/tuple
POISONED_CONFIG = VALID_CONFIG + "bad: !!python/tuple\n- 1\n- 2\n"


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


class TestSaveLoadRoundTrip:
    """DEFECT 1：save/load 往返必须一致，且失败不得破坏磁盘上的配置。"""

    def test_unrelated_keys_survive_save_with_non_safe_value(
        self, tmp_path: Path
    ) -> None:
        """保存含元组的值后，文件仍可被 safe_load 读回，且无关键全部保留。"""
        cfg = _write(tmp_path / "config.yaml", VALID_CONFIG)
        manager = ConfigManager(str(cfg))
        manager.set("settings.extra", (1, 2))
        manager.save()

        raw = cfg.read_text(encoding="utf-8")
        assert "!!python" not in raw, (
            "save() 写出了 safe_load 无法读取的标签:\n" + raw
        )

        reloaded = ConfigManager(str(cfg))
        assert reloaded.get("napcat.ws_url") == "ws://test:3002"
        assert reloaded.get("napcat.access_token") == "token-value"
        assert reloaded.get("napcat.bot_uin") == "123456"
        assert reloaded.get("bot.load_plugins") is True
        assert reloaded.get("logging.level") == "INFO"

    def test_load_failure_never_overwrites_existing_file(self, tmp_path: Path) -> None:
        """加载失败后调用 set_* 不得把原文件覆盖成 {}（永久丢失无关配置）。"""
        cfg = _write(tmp_path / "config.yaml", POISONED_CONFIG)
        manager = ConfigManager(str(cfg))

        try:
            manager.set_bot_uin("999")
        except Exception:  # noqa: BLE001 - 允许显式报错，但不允许静默覆盖
            pass

        raw = cfg.read_text(encoding="utf-8")
        assert "ws_url" in raw and "load_plugins" in raw, (
            "加载失败后的 save() 覆盖了原文件，无关配置全部丢失:\n" + raw
        )

    def test_load_failure_is_surfaced_and_blocks_save(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """加载失败必须被记录并阻止后续 save()，不能让调用方误以为已加载。"""
        cfg = _write(tmp_path / "config.yaml", POISONED_CONFIG)

        with caplog.at_level(logging.ERROR, logger="sdk.config.config"):
            manager = ConfigManager(str(cfg))

        assert any(
            "加载失败" in record.getMessage() for record in caplog.records
        ), f"加载失败没有记录任何错误日志: {[r.getMessage() for r in caplog.records]}"

        with pytest.raises(RuntimeError):
            manager.save()

        assert cfg.read_text(encoding="utf-8") == POISONED_CONFIG

    def test_unrepresentable_value_raises_and_leaves_file_intact(
        self, tmp_path: Path
    ) -> None:
        """无法安全序列化的值必须报错，且不得先截断再失败。"""
        cfg = _write(tmp_path / "config.yaml", VALID_CONFIG)
        manager = ConfigManager(str(cfg))
        manager.set("settings.weird", object())

        raised: BaseException | None = None
        try:
            manager.save()
        except Exception as exc:  # noqa: BLE001
            raised = exc

        raw = cfg.read_text(encoding="utf-8")
        assert raw == VALID_CONFIG, f"save() 失败时截断了原文件: {raw!r}"
        assert isinstance(raised, RuntimeError), (
            f"save() 未抛出可解释的错误: {raised!r}"
        )
        assert not (tmp_path / "config.yaml.tmp").exists(), "临时文件未清理"

    def test_atomic_replace_failure_keeps_original_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """替换步骤失败时，原配置文件必须保持完整（原子写入）。"""
        import sdk.config.config as config_module

        cfg = _write(tmp_path / "config.yaml", VALID_CONFIG)
        manager = ConfigManager(str(cfg))
        manager.set("settings.debug", True)

        def _boom(src: object, dst: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(config_module.os, "replace", _boom)

        with pytest.raises(OSError):
            manager.save()

        assert cfg.read_text(encoding="utf-8") == VALID_CONFIG


class TestSetThroughNonDictIntermediate:
    """DEFECT 2：中间键为 null/标量时，set()/set_*() 必须可预测。"""

    @pytest.mark.parametrize(
        ("intermediate", "label"),
        [
            ("napcat:\n", "null"),
            ('napcat: "ws://legacy"\n', "scalar"),
        ],
    )
    def test_set_helper_repairs_non_dict_intermediate(
        self, tmp_path: Path, intermediate: str, label: str
    ) -> None:
        """set_ws_uri 在 napcat 为 null/标量时不得抛出裸 TypeError。"""
        cfg = _write(
            tmp_path / "config.yaml",
            intermediate + "bot:\n  load_plugins: true\n",
        )
        manager = ConfigManager(str(cfg))

        manager.set_ws_uri("ws://127.0.0.1:3002")  # BEFORE: TypeError

        assert manager.get("napcat.ws_url") == "ws://127.0.0.1:3002"
        assert manager.get("bot.load_plugins") is True

        on_disk = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert on_disk["napcat"]["ws_url"] == "ws://127.0.0.1:3002"

    def test_set_deep_path_through_scalar_intermediate(self, tmp_path: Path) -> None:
        """多级路径中间遇到标量时，set() 必须可预测地完成。"""
        cfg = _write(tmp_path / "config.yaml", "a: 1\n")
        manager = ConfigManager(str(cfg))

        manager.set("a.b.c", "value")  # BEFORE: TypeError

        assert manager.get("a.b.c") == "value"
        assert manager.get("a", "missing") == {"b": {"c": "value"}}

    def test_set_helper_survives_null_intermediate_and_preserves_siblings(
        self, tmp_path: Path
    ) -> None:
        """修复 null 中间键时，兄弟键不得受影响。"""
        cfg = _write(
            tmp_path / "config.yaml",
            "napcat:\nlogging:\n  level: DEBUG\nsettings:\n  debug: true\n",
        )
        manager = ConfigManager(str(cfg))

        manager.set_bot_uin("888")
        manager.set_debug(False)

        assert manager.get("napcat.bot_uin") == "888"
        assert manager.get("logging.level") == "DEBUG"
        assert manager.get("settings.debug") is False
        on_disk = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert on_disk["logging"]["level"] == "DEBUG"
