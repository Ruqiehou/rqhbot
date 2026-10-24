"""
适配器解析器

把「顶层 adapter 字段 → WebSocket 地址 / 令牌 / 多实例选择」的解析逻辑
从 ``ConfigManager`` 中抽离出来，配置层只负责读写 YAML。
"""

from __future__ import annotations

from typing import Any, Protocol

from .backends import DEFAULT_BACKEND, BackendSpec, get_backend


class ConfigLike(Protocol):
    """解析器所需的最小配置接口"""

    def get(self, key: str, default: Any = None) -> Any:
        """读取配置值（支持点号路径）"""
        ...

    def set(self, key: str, value: Any) -> None:
        """写入配置值（支持点号路径）"""
        ...


class AdapterResolver:
    """按 ``adapter`` 字段解析当前适配器的连接参数"""

    def __init__(self, config: ConfigLike) -> None:
        self._config: ConfigLike = config

    @property
    def backend(self) -> BackendSpec:
        """当前适配器后端描述"""
        return get_backend(self._config.get("adapter") or DEFAULT_BACKEND)

    @property
    def name(self) -> str:
        """当前适配器后端名称"""
        return self.backend.name

    def set_backend(self, name: str) -> None:
        """切换适配器后端（仅写入配置，持久化由调用方决定）"""
        self._config.set("adapter", get_backend(name).name)

    # ==================== 连接参数 ====================

    def ws_uri(self) -> str:
        """读取 WebSocket 地址，缺省回落到该后端默认值"""
        backend: BackendSpec = self.backend
        instance: dict[str, Any] | None = self._active_instance()
        if instance is not None:
            return instance.get("ws_uri") or backend.default_ws_uri
        return (
            self._config.get(f"{backend.config_section}.ws_url")
            or backend.default_ws_uri
        )

    def ws_token(self) -> str:
        """读取访问令牌，缺省为空串"""
        backend: BackendSpec = self.backend
        instance: dict[str, Any] | None = self._active_instance()
        if instance is not None:
            return instance.get("ws_token", "") or ""
        return self._config.get(f"{backend.config_section}.access_token", "") or ""

    # ==================== 多实例（SnowLuma） ====================

    def instances(self) -> list[dict[str, Any]]:
        """获取当前后端的多实例配置列表"""
        raw: Any = self._config.get(f"{self.backend.config_section}.instances", [])
        return raw if isinstance(raw, list) else []

    def active_index(self) -> int:
        """获取当前激活的实例索引"""
        raw: Any = self._config.get(f"{self.backend.config_section}.active", 0)
        return raw if isinstance(raw, int) else 0

    def set_active(self, index: int) -> None:
        """切换当前实例（仅写入配置）

        Raises:
            ValueError: 索引超出范围。
        """
        instances: list[dict[str, Any]] = self.instances()
        if not 0 <= index < len(instances):
            raise ValueError(f"实例索引 {index} 超出范围 (0-{len(instances) - 1})")
        self._config.set(f"{self.backend.config_section}.active", index)

    def select_instance(self) -> int:
        """CLI 交互式选择当前后端的实例（仅多实例时调用）

        Returns:
            最终激活的实例索引
        """
        instances: list[dict[str, Any]] = self.instances()
        active: int = self.active_index()
        print(f"\n=== {self.backend.display_name} 实例选择 ===")
        for i, inst in enumerate(instances):
            name = inst.get("name", f"实例 {i + 1}")
            ws_uri = inst.get("ws_uri", "未知")
            marker = " [当前]" if i == active else ""
            print(f"  {i + 1}. {name} ({ws_uri}){marker}")
        print("  0. 直接启动（使用当前实例）")
        print()

        while True:
            try:
                choice = input(f"请选择实例 [0-{len(instances)}，默认 0]: ").strip()
                if not choice or choice == "0":
                    name = instances[active].get("name", f"实例 {active + 1}")
                    print(f"使用当前实例: {name}")
                    return active
                index = int(choice) - 1
                if 0 <= index < len(instances):
                    self.set_active(index)
                    save = getattr(self._config, "save", None)
                    if callable(save):
                        save()
                    print(f"已选择: {instances[index].get('name', f'实例 {index + 1}')}")
                    return index
                print(f"请输入 0-{len(instances)} 范围内的数字")
            except ValueError:
                print("请输入有效数字")
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                return active

    # ==================== 内部 ====================

    def _active_instance(self) -> dict[str, Any] | None:
        """返回当前后端的激活实例配置（无多实例配置时为 None）"""
        instances: list[dict[str, Any]] = self.instances()
        active: int = self.active_index()
        if 0 <= active < len(instances):
            instance: Any = instances[active]
            if isinstance(instance, dict):
                return instance
        return None
