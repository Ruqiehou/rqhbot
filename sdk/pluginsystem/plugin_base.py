"""
插件系统核心模块
提供 PluginBase 基类与 PluginManager 管理器，全部采用强类型声明
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, TypeAlias, TypeVar

try:
    from ..config import setup_logging
    from ..core.interfaces import IClient
    from ..core.events import GroupMessageEvent, PrivateMessageEvent, NoticeEvent, RequestEvent
    from ..core.event_bus import EventBus
except ImportError:
    from sdk.config import setup_logging
    from sdk.core.interfaces import IClient
    from sdk.core.events import GroupMessageEvent, PrivateMessageEvent, NoticeEvent, RequestEvent
    from sdk.core.event_bus import EventBus

setup_logging()

logger: logging.Logger = logging.getLogger(__name__)

PluginConfig = Dict[str, Any]
F = TypeVar("F", bound=Callable[..., Any])
MessageFilter = Callable[[Any], bool]
MessageHandler = Callable[..., Coroutine[Any, Any, None]]


class MessageFilterRule:
    def __init__(
        self,
        message_type: str,
        *,
        keyword: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        prefix: Optional[str] = None,
        prefixes: Optional[List[str]] = None,
        equals: Optional[str] = None,
        contains: Optional[str] = None,
        regex: Optional[str] = None,
        custom: Optional[MessageFilter] = None,
    ) -> None:
        self.message_type = message_type
        self.keyword = keyword
        self.keywords = keywords or []
        self.prefix = prefix
        self.prefixes = prefixes or []
        self.equals = equals
        self.contains = contains
        self.regex = re.compile(regex) if regex else None
        self.custom = custom

    def match(self, event: Any) -> bool:
        text = str(getattr(getattr(event, "message", None), "plain_text", "")).strip()

        if self.equals is not None and text != self.equals:
            return False

        if self.keyword is not None and self.keyword not in text:
            return False

        if self.keywords and not any(keyword in text for keyword in self.keywords):
            return False

        if self.contains is not None and self.contains not in text:
            return False

        if self.prefix is not None and not text.startswith(self.prefix):
            return False

        if self.prefixes and not any(text.startswith(prefix) for prefix in self.prefixes):
            return False

        if self.regex is not None and self.regex.search(text) is None:
            return False

        if self.custom is not None and not self.custom(event):
            return False

        return True


def _message_filter_decorator(message_type: str, **filters: Any) -> Callable[[MessageHandler], MessageHandler]:
    def decorator(func: MessageHandler) -> MessageHandler:
        rules: List[MessageFilterRule] = list(getattr(func, "_rqhbot_message_filters", []))
        rules.append(MessageFilterRule(message_type, **filters))
        setattr(func, "_rqhbot_message_filters", rules)
        return func
    return decorator


def group_server(**filters: Any) -> Callable[[MessageHandler], MessageHandler]:
    return _message_filter_decorator("group", **filters)


def private_server(**filters: Any) -> Callable[[MessageHandler], MessageHandler]:
    return _message_filter_decorator("private", **filters)


def message_filter(message_type: str, **filters: Any) -> Callable[[MessageHandler], MessageHandler]:
    return _message_filter_decorator(message_type, **filters)


class FilterRegistry:
    def group_server(self, func: Optional[MessageHandler] = None, **filters: Any) -> Any:
        decorator = group_server(**filters)
        if func is None:
            return decorator
        return decorator(func)

    def private_server(self, func: Optional[MessageHandler] = None, **filters: Any) -> Any:
        decorator = private_server(**filters)
        if func is None:
            return decorator
        return decorator(func)

    def message_filter(self, message_type: str, **filters: Any) -> Callable[[MessageHandler], MessageHandler]:
        return _message_filter_decorator(message_type, **filters)


filter_registry = FilterRegistry()


class PluginBase:
    """插件基类 —— 所有插件必须继承此类

    插件通过 filter_registry.group_server / filter_registry.private_server
    声明群聊和私聊消息处理器。插件只依赖 IClient 接口和 EventBus，
    不持有 BotClient 引用。
    """

    def __init__(self) -> None:
        self.name: str = self.__class__.__name__
        self.version: str = "1.0.0"
        self.description: str = ""
        self.author: str = "Unknown"
        self.enabled: bool = True
        self.api: Optional[IClient] = None
        self.event_bus: Optional[EventBus] = None
        self._tasks: List[asyncio.Task[Any]] = []
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
        self._config_cache: Dict[str, PluginConfig] = {}
        self._config_cache_time: Dict[str, float] = {}
        self._config_ttl: float = 600.0
        self._plugin_dir: Optional[Path] = None
        self._message_handlers: Dict[str, List[Dict[str, Any]]] = {
            "group": [],
            "private": [],
        }
        self._collect_message_handlers()

    # ==================== 路径解析 ====================

    def _resolve_plugin_dir(self, bot: Optional[Any] = None) -> Path:
        """解析当前插件真实目录"""
        if self._plugin_dir is not None:
            return self._plugin_dir

        module_file: Optional[str] = getattr(
            sys.modules.get(self.__class__.__module__), "__file__", None
        )
        if module_file:
            return Path(module_file).resolve().parent

        return Path.cwd() / "plugins" / (self.name.lower() if self.name else "")

    # ==================== 过滤器注册 ====================

    def _collect_message_handlers(self) -> None:
        self._message_handlers = {"group": [], "private": []}

        seen = set()
        for cls in type(self).__mro__:
            for attr_name, source in vars(cls).items():
                if attr_name in seen:
                    continue
                seen.add(attr_name)
                rules = getattr(source, "_rqhbot_message_filters", ())
                if not rules:
                    continue
                handler = getattr(self, attr_name)
                for rule in rules:
                    if rule.message_type in self._message_handlers:
                        self._message_handlers[rule.message_type].append({
                            "handler": handler,
                            "rule": rule,
                            "name": attr_name,
                        })

    async def _dispatch_filtered_message(self, message_type: str, event: Any) -> bool:
        matched = False

        for item in self._message_handlers.get(message_type, []):
            rule: MessageFilterRule = item["rule"]
            handler: MessageHandler = item["handler"]
            name: str = item["name"]

            try:
                if rule.match(event):
                    matched = True
                    await handler(event)
            except Exception as e:
                logger.error(f"[{self.name}] filter handler {name} error: {e}", exc_info=True)

        return matched

    # ==================== 生命周期 ====================

    async def on_load(self, api: IClient, event_bus: EventBus, plugin_dir: Optional[Path] = None) -> None:
        """插件加载时调用

        Args:
            api: IClient 接口实例
            event_bus: EventBus 实例
            plugin_dir: 插件目录路径
        """
        self.api = api
        self.event_bus = event_bus
        if plugin_dir is not None:
            self._plugin_dir = plugin_dir
        self._subscribe_events()
        logger.info(f"插件 {self.name} 加载成功")

    async def on_unload(self) -> None:
        """插件卸载时调用"""
        self._unsubscribe_events()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._executor.shutdown(wait=False)
        logger.info(f"插件 {self.name} 已卸载")

    def _subscribe_events(self) -> None:
        """向 EventBus 订阅事件"""
        if self.event_bus is None:
            return
        self.event_bus.subscribe(GroupMessageEvent, self._on_group_message_wrapper)
        self.event_bus.subscribe(PrivateMessageEvent, self._on_private_message_wrapper)
        self.event_bus.subscribe(NoticeEvent, self._on_notice_wrapper)
        self.event_bus.subscribe(RequestEvent, self._on_request_wrapper)

    def _unsubscribe_events(self) -> None:
        """从 EventBus 取消订阅"""
        if self.event_bus is None:
            return
        self.event_bus.unsubscribe(GroupMessageEvent, self._on_group_message_wrapper)
        self.event_bus.unsubscribe(PrivateMessageEvent, self._on_private_message_wrapper)
        self.event_bus.unsubscribe(NoticeEvent, self._on_notice_wrapper)
        self.event_bus.unsubscribe(RequestEvent, self._on_request_wrapper)

    async def _on_group_message_wrapper(self, event: GroupMessageEvent) -> None:
        if self.enabled:
            try:
                await self._dispatch_filtered_message("group", event)
            except Exception as e:
                logger.error(f"[{self.name}] group message error: {e}", exc_info=True)

    async def _on_private_message_wrapper(self, event: PrivateMessageEvent) -> None:
        if self.enabled:
            try:
                await self._dispatch_filtered_message("private", event)
            except Exception as e:
                logger.error(f"[{self.name}] private message error: {e}", exc_info=True)

    async def _on_notice_wrapper(self, event: NoticeEvent) -> None:
        if self.enabled:
            try:
                await self.on_notice(event)
            except Exception as e:
                logger.error(f"[{self.name}] on_notice error: {e}", exc_info=True)

    async def _on_request_wrapper(self, event: RequestEvent) -> None:
        if self.enabled:
            try:
                await self.on_request(event)
            except Exception as e:
                logger.error(f"[{self.name}] on_request error: {e}", exc_info=True)

    # ==================== 事件回调 ====================

    async def on_notice(self, event: NoticeEvent) -> None:
        """通知事件处理（子类可重写）"""
        pass

    async def on_request(self, event: RequestEvent) -> None:
        """请求事件处理（子类可重写）"""
        pass

    # ==================== 工具方法 ====================

    def create_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """创建后台任务

        Args:
            coro: 协程对象

        Returns:
            asyncio.Task
        """
        task: asyncio.Task[Any] = asyncio.create_task(coro)
        self._tasks.append(task)
        return task

    async def load_config(
        self, config_name: str = "config.json", bot: Optional[Any] = None
    ) -> PluginConfig:
        """异步加载插件配置（带缓存）

        Args:
            config_name: 配置文件名
            bot: 兼容旧接口，已废弃，可忽略

        Returns:
            配置字典
        """
        cache_key: str = f"{self.name}_{config_name}"
        now: float = time.time()

        if cache_key in self._config_cache:
            cached_at: float = self._config_cache_time.get(cache_key, 0.0)
            if now - cached_at < self._config_ttl:
                return dict(self._config_cache[cache_key])

        plugin_dir: Path = self._resolve_plugin_dir()
        config_path: Path = plugin_dir / config_name

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data: PluginConfig = json.load(f)
                self._config_cache[cache_key] = dict(data)
                self._config_cache_time[cache_key] = now
                return data
            except Exception as e:
                logger.error(f"加载插件 {self.name} 配置失败: {e}")

        return {}

    async def save_config(
        self,
        config: PluginConfig,
        config_name: str = "config.json",
        bot: Optional[Any] = None,
    ) -> bool:
        """异步保存插件配置

        Args:
            config: 配置字典
            config_name: 配置文件名
            bot: 兼容旧接口，已废弃，可忽略

        Returns:
            是否成功
        """
        plugin_dir: Path = self._resolve_plugin_dir()
        config_path: Path = plugin_dir / config_name

        try:
            plugin_dir.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            cache_key: str = f"{self.name}_{config_name}"
            self._config_cache[cache_key] = dict(config)
            self._config_cache_time[cache_key] = time.time()
            return True
        except Exception as e:
            logger.error(f"保存插件 {self.name} 配置失败: {e}")
            return False

    def sync_run(self, func: F) -> Callable[..., Coroutine[Any, Any, Any]]:
        """同步运行装饰器 —— 将同步函数包装为协程

        Args:
            func: 同步函数

        Returns:
            包装后的异步函数
        """
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self.run_in_executor(func, *args, **kwargs)
        return wrapper

    async def get_plugin_stats(self) -> Dict[str, Any]:
        """获取插件统计信息

        Returns:
            统计信息字典
        """
        return {
            "name": self.name,
            "enabled": self.enabled,
            "pending_tasks": len([t for t in self._tasks if not t.done()]),
        }

    async def safe_save_data(
        self,
        data: Dict[str, Any],
        filename: str,
        bot: Optional[Any] = None,
    ) -> bool:
        """安全保存数据到文件

        Args:
            data: 数据字典
            filename: 文件名
            bot: 兼容旧接口，已废弃，可忽略

        Returns:
            是否成功
        """
        try:
            plugin_dir: Path = self._resolve_plugin_dir()
            plugin_dir.mkdir(parents=True, exist_ok=True)
            file_path: Path = plugin_dir / filename
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"保存数据失败: {e}")
            return False

    async def safe_load_data(
        self,
        filename: str,
        default: Optional[Dict[str, Any]] = None,
        bot: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """安全从文件加载数据

        Args:
            filename: 文件名
            default: 默认值
            bot: 兼容旧接口，已废弃，可忽略

        Returns:
            数据字典
        """
        try:
            plugin_dir: Path = self._resolve_plugin_dir()
            file_path: Path = plugin_dir / filename
            if not file_path.exists():
                return default if default is not None else {}
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            return default if default is not None else {}

    async def delay(self, seconds: float) -> None:
        """异步延迟

        Args:
            seconds: 延迟秒数
        """
        await asyncio.sleep(seconds)

    # ==================== 消息分发（兼容旧接口，已废弃） ====================

    async def handle_message_dispatch(
        self, bot: Any, message: Dict[str, Any]
    ) -> None:
        """兼容旧接口，已废弃。新插件请重写 on_group_message / on_private_message。"""
        pass

    async def reply(self, message: Dict[str, Any], content: str) -> None:
        """回复消息（根据消息类型自动选择发送方式）

        Args:
            message: 消息数据（原始 dict，兼容旧接口）
            content: 回复内容
        """
        if self.api is None:
            logger.error(f"[{self.name}] API 未初始化，无法发送消息")
            return

        msg_type: str = str(message.get("message_type", ""))

        if msg_type == "group":
            group_id: int = int(message.get("group_id", 0))
            await self.api.send_group_message(group_id, content)
        elif msg_type == "private":
            user_id: int = int(message.get("user_id", 0))
            await self.api.send_private_message(user_id, content)

    async def reply_with_event(self, event: Any, content: str) -> None:
        if self.api is None:
            logger.error(f"[{self.name}] API 未初始化，无法发送消息")
            return

        group_id = getattr(event, "group_id", None)
        if group_id is not None:
            await self.api.send_group_message(int(group_id), content)
            return

        user_id = getattr(event, "user_id", None)
        if user_id is not None:
            await self.api.send_private_message(int(user_id), content)


# ==================== 插件管理器 ====================

class PluginManager:
    """插件管理器 —— 负责插件的注册、加载与卸载。
    
    只依赖 IClient 和 EventBus，不持有 BotClient 引用。
    """

    def __init__(self, api: IClient, event_bus: EventBus) -> None:
        self.api: IClient = api
        self.event_bus: EventBus = event_bus
        self.plugins: Dict[str, PluginBase] = {}
        self._loaded_plugins: List[str] = []

    # ==================== 注册 / 注销 ====================

    def register_plugin(self, plugin: PluginBase, plugin_dir: Optional[Path] = None) -> bool:
        """注册插件

        Args:
            plugin: 插件实例
            plugin_dir: 插件目录路径（可选，用于配置文件定位）

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
                asyncio.create_task(plugin.on_load(self.api, self.event_bus, plugin_dir))
            else:
                logger.warning(f"事件循环未运行，延迟加载插件 {pname}")
        except RuntimeError:
            logger.warning(f"没有运行的事件循环，延迟加载插件 {pname}")

        return True

    def unregister_plugin(self, plugin_name: str) -> bool:
        """注销插件

        Args:
            plugin_name: 插件名称

        Returns:
            是否成功
        """
        pname: str = plugin_name.lower()

        if pname not in self.plugins:
            logger.warning(f"插件 {pname} 未注册")
            return False

        plugin: PluginBase = self.plugins[pname]
        asyncio.create_task(plugin.on_unload())

        del self.plugins[pname]
        self._loaded_plugins = [
            p for p in self._loaded_plugins if p.lower() != pname
        ]

        logger.info(f"注销插件: {pname}")
        return True

    # ==================== 加载 ====================

    def load_plugin_from_file(self, plugin_path: str) -> Optional[PluginBase]:
        """从文件加载插件

        Args:
            plugin_path: 插件文件路径

        Returns:
            插件实例或 None
        """
        try:
            pp: Path = Path(plugin_path)

            if not pp.exists():
                logger.error(f"插件文件不存在: {pp}")
                return None

            plugin_dir: Path = pp.parent
            plugin_dir_str: str = str(plugin_dir)

            if plugin_dir_str not in sys.path:
                sys.path.insert(0, plugin_dir_str)

            module_name: str = f"plugin_{plugin_dir.name}"

            spec = importlib.util.spec_from_file_location(
                module_name,
                pp,
                submodule_search_locations=[plugin_dir_str],
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(module_name, None)
                raise

            for attr_name in dir(module):
                attr: Any = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, PluginBase)
                    and attr is not PluginBase
                ):
                    instance = attr()
                    instance._plugin_dir = plugin_dir
                    return instance

            logger.error(f"插件文件中未找到插件类: {pp}")
            return None

        except Exception as e:
            logger.error(f"加载插件失败: {e}")
            return None

    async def load_plugins_from_dir_async(self, plugins_dir: str) -> List[str]:
        """从目录异步加载所有插件

        Args:
            plugins_dir: 插件目录路径

        Returns:
            成功加载的插件名称列表
        """
        loaded: List[str] = []
        plugins_path: Path = Path(plugins_dir)

        if not plugins_path.exists():
            logger.warning(f"插件目录不存在: {plugins_dir}")
            return loaded

        for plugin_file in plugins_path.glob("*/main.py"):
            try:
                plugin: Optional[PluginBase] = self.load_plugin_from_file(
                    str(plugin_file)
                )
                if plugin and self.register_plugin(plugin, plugin._plugin_dir):
                    loaded.append(plugin.name)
                    self._loaded_plugins.append(plugin.name)
            except Exception as e:
                logger.error(f"加载插件失败 {plugin_file}: {e}")

        return loaded

    # ==================== 查询 ====================

    def get_all_plugins(self) -> Dict[str, PluginBase]:
        """获取所有已注册的插件"""
        return self.plugins

    def get_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        """获取指定插件"""
        return self.plugins.get(plugin_name.lower())

    def unload_plugin(self, plugin_name: str) -> bool:
        """卸载指定插件"""
        return self.unregister_plugin(plugin_name)
