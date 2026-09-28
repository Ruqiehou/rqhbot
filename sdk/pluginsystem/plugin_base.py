"""
插件系统核心模块
提供 PluginBase 基类与 PluginManager 管理器，全部采用强类型声明
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial, wraps
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
        self._unloading: bool = False
        self._message_handlers: Dict[str, List[Dict[str, Any]]] = {
            "group": [],
            "private": [],
        }
        self._collect_message_handlers()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """把子类重写的 on_unload 收编为模板方法的一环

        插件常在 on_unload 中先做业务清理再 await super().on_unload()。若子类实现
        中途抛异常、或干脆没有调用 super()，基类的退订/任务取消就永远不会执行，
        死掉的插件实例会继续挂在 EventBus 上重复回复消息。

        因此这里把子类定义的 on_unload 改名为 _on_unload_impl，由基类 on_unload
        在 finally 中统一保证资源释放；子类里的 super().on_unload() 依然可用
        （基类有重入保护，不会递归）。
        """
        super().__init_subclass__(**kwargs)

        impl = cls.__dict__.get("on_unload")
        if impl is not None and asyncio.iscoroutinefunction(impl):
            cls._on_unload_impl = impl
            # 删掉子类自己的 on_unload，让实例继续解析到基类的模板方法
            delattr(cls, "on_unload")

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

    def _atomic_write_json(self, path: Path, data: Any) -> None:
        """原子写入 JSON 文件

        直接 open(path, "w") 会立刻截断目标文件，若 json.dump 中途失败，
        旧内容已经丢失、磁盘上只剩半截 JSON，下次读取就会静默回退成默认值。
        这里先写同目录临时文件，成功后再 os.replace 覆盖，
        保证目标文件要么是完整的旧内容、要么是完整的新内容。

        Raises:
            写入或替换失败时原样抛出，由调用方转成 False
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Path = path.with_name(f"{path.name}.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except BaseException:
            # 失败时清掉临时文件，避免污染插件目录
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise

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
        """插件卸载时调用（模板方法）

        无论子类实现是否调用了 super()、是否抛异常，基类都会在 finally 中
        释放事件订阅、取消后台任务并关闭线程池，避免卸载失败留下僵尸插件。
        子类可继续重写本方法做额外清理。
        """
        if getattr(self, "_unloading", False):
            # 子类实现里 await super().on_unload() 时走到这里：
            # 资源释放由最外层调用统一负责，避免重复与递归
            return

        self._unloading = True
        try:
            impl = self._resolve_on_unload_impl()
            if impl is not None:
                await impl(self)
        finally:
            self._unloading = False
            self._release_plugin_resources()
            logger.info(f"插件 {self.name} 已卸载")

    def _resolve_on_unload_impl(self) -> Optional[Callable[[Any], Coroutine[Any, Any, Any]]]:
        """查找子类通过 __init_subclass__ 登记的 on_unload 实现"""
        for klass in type(self).__mro__:
            impl = klass.__dict__.get("_on_unload_impl")
            if impl is not None:
                return impl
        return None

    def _release_plugin_resources(self) -> None:
        """释放插件占用的资源（幂等，可重复调用）"""
        self._unsubscribe_events()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()
        self._executor.shutdown(wait=False)

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
            self._atomic_write_json(config_path, config)

            cache_key: str = f"{self.name}_{config_name}"
            self._config_cache[cache_key] = dict(config)
            self._config_cache_time[cache_key] = time.time()
            return True
        except Exception as e:
            logger.error(f"保存插件 {self.name} 配置失败: {e}")
            return False

    async def run_in_executor(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """在线程池中执行同步函数，避免阻塞事件循环

        Args:
            func: 同步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            同步函数的返回值
        """
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, partial(func, *args, **kwargs))

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
            self._atomic_write_json(file_path, data)
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
        self._load_tasks: Dict[str, asyncio.Task[Any]] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # ==================== 后台任务 ====================

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> Optional[asyncio.Task[Any]]:
        """在当前事件循环中创建任务并持有强引用

        必须持有引用，否则任务可能被 GC 提前回收；同时统一取回异常，
        避免出现 "Task exception was never retrieved"。

        Returns:
            创建的任务；当前没有运行中的事件循环时返回 None
        """
        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        except RuntimeError:
            return None

        task: asyncio.Task[Any] = loop.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)
        return task

    def _on_background_task_done(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(task)
        if task.cancelled():
            return
        exc: Optional[BaseException] = task.exception()
        if exc is not None:
            logger.error(f"插件后台任务异常: {exc}", exc_info=exc)

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
            asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(f"没有运行的事件循环，延迟加载插件 {pname}")
            return True

        task: asyncio.Task[Any] = asyncio.create_task(
            plugin.on_load(self.api, self.event_bus, plugin_dir)
        )
        self._load_tasks[pname] = task
        task.add_done_callback(partial(self._on_load_done, pname, plugin))
        return True

    def _on_load_done(
        self, pname: str, plugin: PluginBase, task: asyncio.Task[Any]
    ) -> None:
        """加载任务收尾：取回异常，清理失败的插件

        加载失败或被取消的插件不能留在注册表里，否则会变成只挂订阅、
        不受管理的僵尸插件（重载后重复回复）。
        """
        if self._load_tasks.get(pname) is task:
            self._load_tasks.pop(pname, None)

        if task.cancelled():
            logger.warning(f"插件 {pname} 加载被取消，清理可能已建立的订阅")
        else:
            exc: Optional[BaseException] = task.exception()
            if exc is None:
                return
            logger.error(f"插件 {pname} 加载失败: {exc}", exc_info=exc)

        # 取消或异常都可能发生在“已订阅事件、尚未登记完成”的中间态，
        # 因此必须显式释放资源，而不是只从字典里删掉
        try:
            plugin._release_plugin_resources()
        except Exception as cleanup_error:
            logger.error(
                f"清理加载失败的插件 {pname} 出错: {cleanup_error}", exc_info=True
            )

        if self.plugins.get(pname) is plugin:
            self.plugins.pop(pname, None)
        self._loaded_plugins = [p for p in self._loaded_plugins if p.lower() != pname]

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

        # 1. 取消仍在进行中的加载：否则加载会在注销完成后才订阅事件，留下僵尸
        load_task: Optional[asyncio.Task[Any]] = self._load_tasks.pop(pname, None)
        if load_task is not None and not load_task.done():
            load_task.cancel()

        # 2. 从内部记录中移除
        del self.plugins[pname]
        self._loaded_plugins = [
            p for p in self._loaded_plugins if p.lower() != pname
        ]

        # 3. 卸载清理：有事件循环则异步执行，没有则同步释放，保证订阅不泄漏
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            plugin._release_plugin_resources()
        else:
            self._spawn(plugin.on_unload())

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
