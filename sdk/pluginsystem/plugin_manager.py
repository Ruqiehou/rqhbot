"""
热重载插件管理器
支持插件热重载 —— 停止旧插件（取消事件订阅、清理资源）→ 重新导入 Python 模块 → 加载并启动新插件

与 PluginBase 的生命周期 (on_load / on_unload) 无缝配合：
  - on_load()    订阅事件到 EventBus，创建后台任务
  - on_unload()  取消所有事件订阅，取消所有后台任务
  
支持文件监控自动热重载：
  - 监控插件目录下的 .py 文件变化
  - 文件修改后自动触发重载（带防抖）
  - 终端实时显示重载状态
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import importlib.util
import json
import logging
import re
import sys
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Optional
from packaging.requirements import Requirement
from packaging.version import Version, InvalidVersion

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    Observer = None
    FileSystemEventHandler = object
    FileModifiedEvent = None
    FileCreatedEvent = None

from .plugin_base import PluginBase

logger = logging.getLogger("HotReloadPluginManager")


def _print_reload_status(plugin_name: str, status: str, success: bool = True) -> None:
    """在终端打印重载状态（带颜色标记）"""
    timestamp = time.strftime("%H:%M:%S")
    if success:
        print(f"\033[32m[{timestamp}] ✓ 插件 '{plugin_name}' {status}\033[0m")
    else:
        print(f"\033[31m[{timestamp}] ✗ 插件 '{plugin_name}' {status}\033[0m")


class HotReloadPluginManager:
    """热重载插件管理器

    管理所有插件的模块导入、实例生命周期和热重载。
    不持有 BotClient 引用，只依赖 IClient 和 EventBus。

    Attributes:
        plugin_dir: 插件根目录
        plugins:    已加载的插件实例 (name -> instance)
        plugin_modules: 已加载的插件 Python 模块 (name -> module)
    """

    def __init__(self, plugin_dir: str = "plugins") -> None:
        self.plugin_dir: Path = Path(plugin_dir)
        self.plugins: Dict[str, PluginBase] = {}
        self.plugin_modules: Dict[str, object] = {}
        self._api: Optional[Any] = None
        self._event_bus: Optional[Any] = None

        # 文件监控相关
        self._observer: Optional[Any] = None
        self._debounce_tasks: Dict[str, asyncio.Task] = {}
        self._debounce_delay: float = 0.5  # 防抖延迟（秒）
        self._file_watcher_enabled: bool = False

        # 将插件根目录的父目录（项目根目录）加入 sys.path，
        # 使 plugins.xxx 形式的包导入能正常工作
        root_dir = str(self.plugin_dir.parent)
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        # 预注册 plugins 命名空间包（即使目录下没有 __init__.py）
        if "plugins" not in sys.modules:
            plugins_pkg = types.ModuleType("plugins")
            plugins_pkg.__path__ = [str(self.plugin_dir)]
            plugins_pkg.__package__ = ""
            sys.modules["plugins"] = plugins_pkg

        # 插件配置缓存
        self._plugin_configs: Dict[str, Dict[str, Any]] = {}

        # 设置插件管理器引用，让插件可以访问管理器
        PluginBase._plugin_manager = self

    def _load_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """加载插件配置 (plugin.json)

        Args:
            plugin_name: 插件名称

        Returns:
            插件配置字典，如果不存在或加载失败则返回默认配置
        """
        config_path = self.plugin_dir / plugin_name / "plugin.json"
        default_config = {
            "name": plugin_name,
            "version": "1.0.0",
            "description": "",
            "author": "Unknown",
            "enabled": True,
            "priority": 100,
            "dependencies": [],
            "python_requires": ">=3.8",
        }

        if not config_path.exists():
            return default_config

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            # 合并默认值
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            self._plugin_configs[plugin_name] = config
            return config
        except Exception as e:
            logger.warning(f"加载插件配置 {plugin_name} 失败: {e}，使用默认配置")
            return default_config

    def _check_dependencies(self, plugin_name: str, dependencies: List[str]) -> bool:
        """检查插件依赖是否满足（含版本校验）

        Args:
            plugin_name: 插件名称
            dependencies: 依赖列表

        Returns:
            是否所有依赖都满足
        """
        if not dependencies:
            return True

        unsatisfied: List[str] = []
        for dep in dependencies:
            # 解析包名和版本要求
            try:
                req = Requirement(dep)
            except Exception:
                # 解析失败，只检查是否存在
                pkg_name = dep.split(">=")[0].split("<=")[0].split("==")[0].split("[")[0].strip()
                try:
                    importlib.import_module(pkg_name)
                except ImportError:
                    unsatisfied.append(dep)
                continue

            # 检查包是否安装
            try:
                installed_version_str = importlib.metadata.version(req.name)
            except importlib.metadata.PackageNotFoundError:
                unsatisfied.append(dep)
                continue

            # 检查版本是否满足要求
            if req.specifier:
                try:
                    installed_version = Version(installed_version_str)
                except InvalidVersion:
                    logger.warning(f"插件 {plugin_name}: 无法解析 {req.name} 版本 {installed_version_str!r}，跳过版本检查")
                    continue

                if installed_version not in req.specifier:
                    unsatisfied.append(f"{req.name}{req.specifier} (已安装 {installed_version_str})")

        if unsatisfied:
            logger.error(f"插件 {plugin_name} 依赖不满足: {', '.join(unsatisfied)}")
            return False

        return True

    # ==================== 注册 / 加载 / 重载 / 卸载 ====================

    def register_plugin(self, plugin: PluginBase, plugin_dir: Optional[Path] = None) -> bool:
        """注册已实例化的插件（用于直接提供插件对象而非从文件加载）

        这个方法允许将外部创建的插件实例注册到管理器中，
        适用于插件已在外部实例化的场景。

        Args:
            plugin: 插件实例
            plugin_dir: 插件目录路径（可选）

        Returns:
            是否成功
        """
        pname: str = plugin.name.lower()

        if pname in self.plugins:
            logger.warning(f"插件 {pname} 已注册")
            return False

        self.plugins[pname] = plugin
        logger.info(f"注册插件: {pname}")

        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(
                    plugin.on_load(self._api, self._event_bus, plugin_dir)
                )
            else:
                logger.warning(f"事件循环未运行，延迟加载插件 {pname}")
        except RuntimeError:
            logger.warning(f"没有运行的事件循环，延迟加载插件 {pname}")

        return True

    async def load_plugin(
        self, plugin_name: str, api: Any, event_bus: Any
    ) -> bool:
        """加载（或重载）一个插件

        流程：
        1. 如果已加载，先卸载旧版
        2. 检查 plugin.json 配置（enabled、dependencies）
        3. 使用 importlib 重新导入 Python 模块
        4. 查找 PluginBase 子类并实例化
        5. 调用 instance.on_load() 完成事件订阅和初始化

        插件以完整包形式加载（如 plugins.yiyichat.main），
        预注册包到 sys.modules 避免 __init__.py 中的循环导入。

        Args:
            plugin_name: 插件名称（对应 plugins/<plugin_name>/ 目录）
            api:         IClient 实例
            event_bus:   EventBus 实例

        Returns:
            是否成功
        """
        # 如果已经加载，先卸载旧版（取消订阅 + 取消任务）
        if plugin_name in self.plugins:
            await self.unload_plugin(plugin_name)

        # 加载插件配置
        config = self._load_plugin_config(plugin_name)

        # 检查是否启用
        if not config.get("enabled", True):
            logger.info(f"插件 {plugin_name} 已禁用，跳过加载")
            return False

        # 检查依赖
        dependencies = config.get("dependencies", [])
        if not self._check_dependencies(plugin_name, dependencies):
            return False

        main_file = self.plugin_dir / plugin_name / "main.py"
        if not main_file.exists():
            logger.error(f"插件 {plugin_name} 入口不存在: {main_file}")
            return False

        try:
            pkg_name = f"plugins.{plugin_name}"
            module_name = f"{pkg_name}.main"

            # 彻底清理旧的模块缓存（包括 __pycache__）
            self._clean_all_plugin_cache(plugin_name)

            # 预注册插件包，避免 __init__.py 中 from .main import XXX 导致的循环导入
            if pkg_name not in sys.modules:
                plugin_pkg = types.ModuleType(pkg_name)
                plugin_pkg.__path__ = [str(self.plugin_dir / plugin_name)]
                plugin_pkg.__package__ = "plugins"
                sys.modules[pkg_name] = plugin_pkg

            # 从文件位置加载模块（不使用缓存）
            spec = importlib.util.spec_from_file_location(
                module_name, main_file
            )
            if spec is None or spec.loader is None:
                logger.error(f"无法加载插件模块: {main_file}")
                return False
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 查找继承 PluginBase 的类（跳过基类本身）
            plugin_class: Optional[type] = None
            for attr_name in dir(module):
                attr: Any = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, PluginBase)
                    and attr is not PluginBase
                ):
                    plugin_class = attr
                    break

            if plugin_class is None:
                logger.error(f"插件 {plugin_name} 中未找到 PluginBase 子类")
                return False

            # 实例化并加载
            instance: PluginBase = plugin_class()
            await instance.on_load(api, event_bus, self.plugin_dir / plugin_name)

            self.plugins[plugin_name] = instance
            self.plugin_modules[plugin_name] = module

            logger.info(
                f"插件 {plugin_name} (v{instance.version}) 加载成功"
            )
            return True

        except Exception as e:
            logger.error(
                f"加载插件 {plugin_name} 失败: {e}", exc_info=True
            )
            return False

    async def unload_plugin(self, plugin_name: str) -> None:
        """卸载插件

        调用 PluginBase.on_unload() 清理事件订阅和后台任务，
        然后从内部记录中移除。

        Args:
            plugin_name: 插件名称
        """
        if plugin_name not in self.plugins:
            return

        instance = self.plugins[plugin_name]

        # 1. 调用插件的 on_unload 清理方法
        try:
            await instance.on_unload()
        except Exception as e:
            logger.error(f"插件 {plugin_name} on_unload 出错: {e}", exc_info=True)

        # 2. 从内部记录中移除
        del self.plugins[plugin_name]
        if plugin_name in self.plugin_modules:
            del self.plugin_modules[plugin_name]

        # 3. 清理配置缓存
        cache_keys_to_remove = [k for k in self._plugin_configs if k == plugin_name]
        for key in cache_keys_to_remove:
            del self._plugin_configs[key]

        logger.info(f"插件 {plugin_name} 已卸载")

    async def reload_plugin(
        self, plugin_name: str, api: Any = None, event_bus: Any = None
    ) -> bool:
        """热重载指定插件

        封装了 unload + load 操作，是触发热重载的便捷入口。

        Args:
            plugin_name: 插件名称
            api:         IClient 实例（可选，默认使用缓存的实例）
            event_bus:   EventBus 实例（可选，默认使用缓存的实例）

        Returns:
            是否成功
        """
        logger.info(f"正在热重载插件: {plugin_name}")

        # 使用传入的参数或缓存的实例
        _api = api or self._api
        _event_bus = event_bus or self._event_bus

        if _api is None or _event_bus is None:
            logger.error(f"热重载插件 {plugin_name} 失败：缺少 api 或 event_bus")
            return False

        # 1. 先卸载旧插件（如果已加载）
        if plugin_name in self.plugins:
            await self.unload_plugin(plugin_name)
            logger.info(f"插件 {plugin_name} 已卸载，准备重新加载")

        # 2. 重新加载插件
        success = await self.load_plugin(plugin_name, _api, _event_bus)

        if success:
            logger.info(f"插件 {plugin_name} 热重载完成")
        else:
            logger.error(f"插件 {plugin_name} 热重载失败")
        return success

    # ==================== 批量操作 ====================

    async def load_all_plugins(self, api: Any, event_bus: Any) -> List[str]:
        """从插件目录加载所有插件

        扫描 self.plugin_dir 下每个子目录中的 main.py，
        依次调用 load_plugin() 进行加载。

        Args:
            api:        IClient 实例
            event_bus:  EventBus 实例

        Returns:
            成功加载的插件名称列表
        """
        # 保存 api 和 event_bus 引用
        self._api = api
        self._event_bus = event_bus

        loaded_names: List[str] = []
        if not self.plugin_dir.exists():
            logger.warning(f"插件目录不存在: {self.plugin_dir}")
            return loaded_names

        for entry in sorted(self.plugin_dir.iterdir()):
            if not entry.is_dir():
                continue
            main_file = entry / "main.py"
            if not main_file.exists():
                continue
            plugin_name = entry.name
            success = await self.load_plugin(plugin_name, api, event_bus)
            if success:
                loaded_names.append(plugin_name)

        return loaded_names

    async def unload_all_plugins(self) -> None:
        """卸载所有已加载的插件"""
        for plugin_name in list(self.plugins.keys()):
            await self.unload_plugin(plugin_name)

    # ==================== 查询 ====================

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """获取已加载的插件实例

        Args:
            name: 插件名称

        Returns:
            插件实例，未加载则返回 None
        """
        return self.plugins.get(name)

    def get_all_plugins(self) -> Dict[str, PluginBase]:
        """获取所有已加载的插件实例

        Returns:
            name -> instance 字典副本
        """
        return self.plugins.copy()

    # ==================== 内部工具 ====================

    @staticmethod
    def _clean_submodules(plugin_name: str) -> None:
        """清理指定插件的子模块 sys.modules 缓存

        例如插件名为 "abc"，则会删除 sys.modules 中所有
        以 "plugins.abc"、"plugins.abc." 或旧扁平名 "rqhbot_plugin_abc_" 开头的模块，
        确保重载时子模块也被重新导入。

        Args:
            plugin_name: 插件名称
        """
        prefixes = (
            f"plugins.{plugin_name}",
            f"plugins.{plugin_name}.",
            f"rqhbot_plugin_{plugin_name}_",
        )
        to_delete = [
            mod_name
            for mod_name in sys.modules
            if any(mod_name.startswith(p) for p in prefixes)
        ]
        for mod_name in to_delete:
            del sys.modules[mod_name]
            logger.debug(f"清理模块缓存: {mod_name}")

    def _clean_all_plugin_cache(self, plugin_name: str) -> None:
        """彻底清理插件的所有缓存，包括 __pycache__ 中的 .pyc 文件

        Args:
            plugin_name: 插件名称
        """
        import shutil

        # 1. 清理 sys.modules 缓存
        HotReloadPluginManager._clean_submodules(plugin_name)

        # 2. 清理 __pycache__ 目录（使用实例的 plugin_dir）
        plugin_dir = self.plugin_dir / plugin_name
        pycache_dir = plugin_dir / "__pycache__"
        if pycache_dir.exists():
            try:
                shutil.rmtree(pycache_dir)
                logger.debug(f"清理 __pycache__: {pycache_dir}")
            except Exception as e:
                logger.warning(f"清理 __pycache__ 失败: {e}")

    # ==================== 文件监控 ====================

    def start_file_watcher(self) -> bool:
        """启动文件监控，实现自动热重载

        Returns:
            是否成功启动
        """
        if not HAS_WATCHDOG:
            logger.warning("watchdog 未安装，无法启用文件监控。请运行: pip install watchdog")
            _print_reload_status("系统", "watchdog 未安装，自动热重载不可用", success=False)
            return False

        if self._file_watcher_enabled:
            logger.info("文件监控已在运行")
            return True

        try:
            # 创建事件处理器
            handler = _PluginFileHandler(self)

            # 创建观察者
            self._observer = Observer()
            self._observer.schedule(
                handler,
                str(self.plugin_dir),
                recursive=True  # 递归监控子目录
            )

            # 启动监控
            self._observer.start()
            self._file_watcher_enabled = True

            logger.info(f"文件监控已启动，监控目录: {self.plugin_dir}")
            _print_reload_status("系统", f"文件监控已启动，监控: {self.plugin_dir}")
            return True

        except Exception as e:
            logger.error(f"启动文件监控失败: {e}", exc_info=True)
            _print_reload_status("系统", f"启动文件监控失败: {e}", success=False)
            return False

    def stop_file_watcher(self) -> None:
        """停止文件监控"""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

        self._file_watcher_enabled = False

        # 取消所有防抖任务
        for task in self._debounce_tasks.values():
            if not task.done():
                task.cancel()
        self._debounce_tasks.clear()

        logger.info("文件监控已停止")
        _print_reload_status("系统", "文件监控已停止")

    def _get_plugin_name_from_path(self, file_path: str) -> Optional[str]:
        """从文件路径提取插件名称

        Args:
            file_path: 文件路径

        Returns:
            插件名称或 None
        """
        try:
            path = Path(file_path)
            # 获取相对于插件目录的路径
            relative = path.relative_to(self.plugin_dir)
            # 第一个目录名就是插件名
            parts = relative.parts
            if parts and len(parts) > 1:  # 至少是 plugin_name/file.py
                return parts[0]
        except (ValueError, IndexError):
            pass
        return None

    async def _debounced_reload(self, plugin_name: str) -> None:
        """带防抖的重载方法

        Args:
            plugin_name: 插件名称
        """
        # 等待防抖延迟
        await asyncio.sleep(self._debounce_delay)

        # 执行重载
        if self._api and self._event_bus:
            success = await self.reload_plugin(plugin_name)
            if success:
                _print_reload_status(plugin_name, "自动重载成功")
            else:
                _print_reload_status(plugin_name, "自动重载失败", success=False)
        else:
            logger.warning(f"无法重载插件 {plugin_name}：api 或 event_bus 未设置")

    def _schedule_reload(self, plugin_name: str) -> None:
        """调度重载任务（带防抖）

        Args:
            plugin_name: 插件名称
        """
        # 取消之前的防抖任务
        if plugin_name in self._debounce_tasks:
            old_task = self._debounce_tasks[plugin_name]
            if not old_task.done():
                old_task.cancel()

        # 创建新的防抖任务（兼容 Python 3.12+，get_event_loop 在无 running loop 时不再返回默认 loop）
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        task = loop.create_task(self._debounced_reload(plugin_name))
        self._debounce_tasks[plugin_name] = task


# ==================== 文件监控事件处理器 ====================

if HAS_WATCHDOG:
    class _PluginFileHandler(FileSystemEventHandler):
        """插件文件变化处理器"""

        def __init__(self, manager: HotReloadPluginManager) -> None:
            self._manager = manager
            self._ignore_patterns = {"__pycache__", ".pyc", ".pyo", ".pyd", "__init__.py"}

        def _should_ignore(self, path: str) -> bool:
            """判断是否应该忽略此文件变化"""
            # 忽略 __pycache__ 目录
            if "__pycache__" in path:
                return True
            # 忽略非 Python 文件
            if not path.endswith(".py"):
                return True
            # 忽略 __init__.py（避免循环导入问题）
            if path.endswith("__init__.py"):
                return True
            return False

        def on_modified(self, event: Any) -> None:
            """文件修改事件"""
            if event.is_directory:
                return

            src_path = event.src_path

            # 检查是否应该忽略
            if self._should_ignore(src_path):
                return

            # 获取插件名
            plugin_name = self._manager._get_plugin_name_from_path(src_path)
            if plugin_name and plugin_name in self._manager.plugins:
                logger.info(f"检测到插件文件变化: {src_path}")
                _print_reload_status(plugin_name, "检测到文件变化，准备重载...")
                self._manager._schedule_reload(plugin_name)

        def on_created(self, event: Any) -> None:
            """文件创建事件（处理新增文件）"""
            self.on_modified(event)
