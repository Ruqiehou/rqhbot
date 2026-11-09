"""
传输层 —— WebSocket 连接、重连与请求/响应匹配

负责与 OneBot 后端的物理连接生命周期：
连接建立、断线重连、消息接收入队、``call()`` 的 echo 请求响应匹配。
事件如何分发给业务处理器由客户端层（``client.py``）决定。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Final

import websockets
from websockets.exceptions import ConnectionClosed

from sdk.adapter import BackendSpec
from sdk.core.interfaces import (
    APIResponse,
    IConnectionEventListener,
)
from sdk.core.settings import DEFAULT_ACTION_TIMEOUTS, ClientSettings

logger = logging.getLogger(__name__)


class TransportMixin:
    """连接与请求传输能力

    与 :class:`~sdk.core.client.OneBotClient` 组合使用，依赖宿主类提供：

    - ``settings``：``ClientSettings`` 实例
    - ``backend``：``BackendSpec`` 实例
    - ``_handle_message(data)``：把非响应消息交给上层分发
    """

    # ---- 重连配置（类级默认值，实例值来自 settings）----
    MAX_RECONNECT_ATTEMPTS: Final[int] = 5
    RECONNECT_DELAY: Final[float] = 3.0       # 秒
    RECONNECT_MAX_ROUNDS: Final[int] = 3      # 断线后自动重连的最大轮数
    PING_INTERVAL: Final[float] = 25.0
    PING_TIMEOUT: Final[float] = 10.0
    CLOSE_TIMEOUT: Final[float] = 5.0

    # ---- API 调用超时 ----
    DEFAULT_API_TIMEOUT: Final[float] = 30.0
    ACTION_TIMEOUTS: Final[dict[str, float]] = DEFAULT_ACTION_TIMEOUTS

    # 非幂等接口：重试可能造成重复发送/重复点赞，默认只尝试一次
    NON_IDEMPOTENT_ACTIONS: Final[frozenset[str]] = frozenset({
        "send_msg",
        "send_group_msg",
        "send_private_msg",
        "send_group_forward_msg",
        "send_private_forward_msg",
        "send_like",
        "send_group_notice",
        "send_group_file",  # 上传群文件，重复上传会造成副作用
    })

    # 仅传输层异常允许重试；业务失败（status != ok）重试通常无意义
    RETRYABLE_EXCEPTIONS: Final[tuple[type[BaseException], ...]] = (
        asyncio.TimeoutError,
        ConnectionClosed,
        ConnectionError,
        OSError,
    )

    settings: ClientSettings
    backend: BackendSpec
    ws: Any
    ws_url: str
    access_token: str

    # ==================== 初始化 ====================

    def _init_transport_state(self) -> None:
        """初始化连接相关状态（由宿主类 ``__init__`` 调用）"""
        self.ws = None
        self._connected: bool = False
        self.echo_map: dict[str, asyncio.Future[Any]] = {}

        # ---- 消息处理队列 ----
        self.msg_queue: asyncio.Queue[str | bytes] | None = None
        self._processing_task: asyncio.Task[None] | None = None
        self._listen_task: asyncio.Task[None] | None = None

        # ---- 性能监控 ----
        self._perf_stats: dict[str, int | float] = {
            "total_messages": 0,
            "total_processing_time": 0.0,
            "avg_latency": 0.0,
        }

        # ---- 重连控制 ----
        self.auto_reconnect: bool = self.settings.auto_reconnect
        self.max_reconnect_attempts: int = self.settings.max_reconnect_attempts
        self.reconnect_delay: float = self.settings.reconnect_delay
        self._reconnect_attempts: int = 0
        self._reconnect_task: asyncio.Task[None] | None = None
        self._closing: bool = False  # 主动关闭后不再自动重连

        # ---- 连接事件监听器 ----
        self._connection_listeners: list[IConnectionEventListener] = []

        # ---- echo_map 保护（最多 1000 条，防止内存泄漏）----
        self._echo_maxsize: int = 1000

    # ==================== 连接状态 ====================

    @property
    def connected(self) -> bool:
        """是否已连接"""
        return self._connected

    @property
    def reconnecting(self) -> bool:
        """是否正在进行自动重连"""
        return self._reconnect_task is not None and not self._reconnect_task.done()

    async def _cancel_connection_tasks(self) -> None:
        """回收上一轮遗留的监听/处理任务

        重连时必须先取消旧任务，否则旧的监听/处理协程可能与新任务并存，
        造成同一条消息被重复处理。
        """
        for attr in ("_processing_task", "_listen_task"):
            task: asyncio.Task[None] | None = getattr(self, attr)
            if task is None or task is asyncio.current_task():
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"回收旧连接任务时出错: {e}")
            finally:
                setattr(self, attr, None)

    async def _cancel_reconnect_task(self) -> None:
        """取消进行中的自动重连任务"""
        task = self._reconnect_task
        self._reconnect_task = None
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"取消重连任务时出错: {e}")

    def _schedule_reconnect(self) -> None:
        """监听循环结束后安排自动重连（保证同一时间只有一个重连任务）"""
        if self._closing:
            return
        if not self.auto_reconnect:
            logger.info("自动重连已禁用（settings.auto_reconnect=false），不再重连")
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("事件循环已关闭，跳过自动重连")
            return
        self._reconnect_task = loop.create_task(self._reconnect_loop())
        self._reconnect_task.add_done_callback(self._on_reconnect_task_done)

    @staticmethod
    def _on_reconnect_task_done(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f"自动重连任务异常: {exc}", exc_info=exc)

    async def _reconnect_loop(self) -> None:
        """断线后的自动重连：带退避地重试，直到成功或放弃

        每一轮调用 connect()，由 connect() 负责通知连接监听器；
        达到最大轮数仍失败则结束，使 run_frontend 得以正常退出。
        """
        max_rounds: int = self.settings.reconnect_max_rounds
        for round_index in range(1, max_rounds + 1):
            delay = min(self.reconnect_delay * round_index, 30.0)
            logger.info(
                f"连接已断开，{delay:.0f} 秒后进行第 {round_index}/{max_rounds} 轮重连..."
            )
            await asyncio.sleep(delay)
            if self._closing:
                return
            # 标记为重连，connect() 会走 on_reconnect_success 通知分支
            self._reconnect_attempts = round_index
            if await self.connect():
                logger.info(f"第 {round_index} 轮重连成功")
                return
        self._reconnect_attempts = 0
        logger.error(f"自动重连失败，已尝试 {max_rounds} 轮")

    async def connect(self, max_retries: int | None = None) -> bool:
        """建立连接（支持重连）

        Args:
            max_retries: 最大重试次数，None 使用配置值

        Returns:
            是否连接成功
        """
        self._closing = False
        # 重连前先回收上一轮的监听/处理任务，避免新旧任务同时消费消息
        await self._cancel_connection_tasks()

        retries = 0
        max_retries = max_retries or self.max_reconnect_attempts

        while retries < max_retries:
            try:
                if retries > 0:
                    self._reconnect_attempts = retries
                    logger.info(f"尝试重连 ({retries}/{max_retries})...")
                    for listener in self._connection_listeners:
                        try:
                            await listener.on_reconnecting(retries)
                        except Exception as e:
                            logger.error(f"重连监听器执行失败: {e}")

                headers: dict[str, str] = {}
                if self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    headers["access_token"] = self.access_token

                self.ws = await websockets.connect(
                    self.ws_url,
                    ping_interval=self.settings.ping_interval,
                    ping_timeout=self.settings.ping_timeout,
                    close_timeout=self.settings.close_timeout,
                    additional_headers=headers,
                )

                # 初始化消息队列
                self.msg_queue = asyncio.Queue(maxsize=1000)

                self._connected = True

                # 启动接收任务
                self._listen_task = asyncio.create_task(self._listen_messages())

                # 启动处理任务
                self._processing_task = asyncio.create_task(self._process_messages())

                was_reconnect = self._reconnect_attempts > 0
                self._reconnect_attempts = 0

                logger.info(f"成功连接到{self.backend.display_name}服务器: {self.ws_url}")

                # 通知连接成功
                for listener in self._connection_listeners:
                    try:
                        if was_reconnect and hasattr(listener, "on_reconnect_success"):
                            await listener.on_reconnect_success()
                        else:
                            await listener.on_connected()
                    except Exception as e:
                        logger.error(f"连接监听器执行失败: {e}")

                return True

            except Exception as e:
                retries += 1
                logger.error(f"连接失败 ({retries}/{max_retries}): {e}")

                if retries < max_retries:
                    wait_time = self.reconnect_delay * retries
                    logger.info(f"{wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)

        logger.error(f"连接失败，已达到最大重试次数 ({max_retries})")

        # 通知重连失败
        for listener in self._connection_listeners:
            try:
                await listener.on_reconnect_failed(
                    Exception(f"连接失败，已达到最大重试次数 ({max_retries})")
                )
            except Exception as e:
                logger.error(f"重连失败监听器执行失败: {e}")

        return False

    async def disconnect(self, force: bool = False) -> None:
        """断开连接

        异常断线时 _connected 已被置为 False，但监听/处理任务、WebSocket 引用、
        消息队列和未完成的 API 请求可能仍然存在，此时也必须清理，
        不能仅凭连接标志提前返回。

        Args:
            force: 是否强制断开
        """
        self._closing = True
        await self._cancel_reconnect_task()

        has_resources = (
            self._processing_task is not None
            or self._listen_task is not None
            or self.ws is not None
            or self.msg_queue is not None
            or bool(self.echo_map)
        )
        if not self._connected and not force and not has_resources:
            return

        self._connected = False

        # 关闭消息队列处理
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"关闭处理任务时出错: {e}")
            finally:
                self._processing_task = None

        # 关闭监听任务
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"关闭监听任务时出错: {e}")
            finally:
                self._listen_task = None

        # 关闭 WebSocket 连接
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.error(f"关闭WebSocket连接时出错: {e}")
            finally:
                self.ws = None

        # 清空消息队列引用（防止重连时旧 Queue 泄漏）
        self.msg_queue = None

        # 清空未完成的 echo Future，用 ConnectionError 而非 CancelledError
        # 让调用方能够区分"连接断开导致的失败"和"被外部取消"
        failed = 0
        for future in self.echo_map.values():
            if not future.done():
                future.set_exception(
                    ConnectionError(f"连接已断开: {self.backend.display_name}")
                )
                failed += 1
        self.echo_map.clear()
        if failed:
            logger.warning(f"断开连接时失败了 {failed} 个未完成的 API 请求")

        logger.info("WebSocket 连接已关闭")

        # 通知断开连接
        for listener in self._connection_listeners:
            try:
                await listener.on_disconnected()
            except Exception as e:
                logger.error(f"断开连接监听器执行失败: {e}")

    def add_connection_listener(self, listener: IConnectionEventListener) -> None:
        """添加连接事件监听器

        Args:
            listener: IConnectionEventListener 实例
        """
        if listener not in self._connection_listeners:
            self._connection_listeners.append(listener)

    def remove_connection_listener(self, listener: IConnectionEventListener) -> None:
        """移除连接事件监听器

        Args:
            listener: IConnectionEventListener 实例
        """
        if listener in self._connection_listeners:
            self._connection_listeners.remove(listener)

    # ==================== 收发循环 ====================

    async def _listen_messages(self) -> None:
        """监听消息 —— 接收循环（入队时带超时，避免静默丢消息）"""
        ws = self.ws
        if ws is None:
            return
        try:
            async for message in ws:
                try:
                    if self.msg_queue:
                        # 先尝试快速入队；队列满时最多等 2 秒，仍失败才丢弃
                        try:
                            self.msg_queue.put_nowait(message)
                        except asyncio.QueueFull:
                            try:
                                await asyncio.wait_for(
                                    self.msg_queue.put(message), timeout=2.0
                                )
                            except asyncio.TimeoutError:
                                logger.warning(
                                    "消息队列持续拥堵，丢弃消息（队列大小=%d）",
                                    self.msg_queue.maxsize,
                                )
                except Exception as e:
                    logger.error(f"消息入队失败: {e}")
        except asyncio.CancelledError:
            raise
        except ConnectionClosed:
            logger.warning("WebSocket连接已关闭")
        except Exception as e:
            logger.error(f"监听消息时发生错误: {e}")
        else:
            # websockets 在正常关闭（1000/1001）时会把 ConnectionClosedOK
            # 转成 StopAsyncIteration 让 async for 正常结束，
            # 不会进入上面的 ConnectionClosed 分支，必须在此更新状态
            logger.warning("WebSocket连接已正常关闭")
        finally:
            # 无论正常关闭、异常还是被取消，都要标记断开，
            # 否则 run_frontend 会一直等待一个已经死掉的连接
            self._connected = False
            # 非主动关闭时安排自动重连
            if not self._closing:
                self._schedule_reconnect()

    async def _process_messages(self) -> None:
        """消息处理循环 —— 与接收分离"""
        while self._connected:
            try:
                if not self.msg_queue:
                    await asyncio.sleep(0.1)
                    continue

                # 带超时获取，保证断开后处理循环能在一个周期内自行退出
                try:
                    message = await asyncio.wait_for(self.msg_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # 性能监控 - 开始
                start_time = time.perf_counter()

                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"消息解析失败: {e}")
                except Exception as e:
                    logger.error(f"处理消息时发生错误: {e}")
                finally:
                    # 性能监控 - 结束
                    processing_time = time.perf_counter() - start_time
                    self._perf_stats["total_messages"] += 1
                    self._perf_stats["total_processing_time"] += processing_time
                    self._perf_stats["avg_latency"] = (
                        self._perf_stats["total_processing_time"]
                        / self._perf_stats["total_messages"]
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理循环错误: {e}")

    # ==================== 请求/响应 ====================

    def _resolve_echo(self, data: dict[str, Any]) -> bool:
        """若数据是 API 响应（含 echo），完成对应 Future 并返回 True"""
        if "echo" not in data:
            return False
        echo_id = data["echo"]
        if echo_id not in self.echo_map:
            return False
        future = self.echo_map.pop(echo_id)
        if not future.done():
            future.set_result(data)
        return True

    def _evict_oldest_echo(self) -> None:
        """淘汰 echo_map 中最旧的 pending Future，防止内存泄漏"""
        oldest_key = next(iter(self.echo_map), None)
        if oldest_key is not None:
            old_future = self.echo_map.pop(oldest_key, None)
            if old_future is not None and not old_future.done():
                old_future.set_exception(
                    TimeoutError(f"echo_map 超限，旧请求 {oldest_key!r} 被自动淘汰")
                )
            logger.warning(
                f"echo_map 已达上限 {self._echo_maxsize}，已淘汰最旧条目: {oldest_key!r}"
            )

    def _resolve_timeout(self, action: str, override: float | None = None) -> float:
        """解析单次 API 调用的超时（秒）

        优先级：显式 override > _call_timeout（测试钩子）>
        ``settings.api_timeout`` > 内置 ACTION_TIMEOUTS 表 > DEFAULT_API_TIMEOUT。
        """
        if override is not None:
            return override
        # 测试钩子：_call_timeout 可以是 float 或 callable
        call_timeout = getattr(self, "_call_timeout", None)
        if call_timeout is not None:
            return call_timeout() if callable(call_timeout) else float(call_timeout)
        fallback: float = self.ACTION_TIMEOUTS.get(action, self.DEFAULT_API_TIMEOUT)
        return self.settings.timeout_for(action, fallback)

    async def call(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        max_retries: int | None = None,
        retry_delay: float = 1.0,
        timeout: float | None = None,
    ) -> APIResponse:
        """调用 OneBot API

        Args:
            action: API动作名称
            params: 参数字典
            max_retries: 最大尝试次数（含首次），缺省时幂等接口 3 次、
                非幂等接口（发送消息/点赞等）1 次
            retry_delay: 重试延迟（秒）
            timeout: 单次调用超时（秒），缺省按 action 查表

        Returns:
            API响应数据

        Raises:
            ConnectionError: 未连接
            TimeoutError: API调用超时
            RuntimeError: 服务端返回业务错误（不重试）
        """
        if not self.connected or not self.ws:
            raise ConnectionError(f"未连接到{self.backend.display_name}服务器")

        # 非幂等接口强制只尝试一次，无论调用方传入什么 max_retries
        # 防止重复发送消息/点赞等造成副作用
        if action in self.NON_IDEMPOTENT_ACTIONS:
            attempts = 1
        elif max_retries is None:
            attempts = 3
        else:
            attempts = max(1, max_retries)
        call_timeout: float = self._resolve_timeout(action, timeout)

        last_error: BaseException | None = None

        for attempt in range(attempts):
            echo_id = f"rqhbot-{uuid.uuid4().hex}"
            message = {
                "action": action,
                "params": params or {},
                "echo": echo_id,
            }

            future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

            # 插入前淘汰最旧的，防止 echo_map 无限增长
            if len(self.echo_map) >= self._echo_maxsize:
                self._evict_oldest_echo()

            self.echo_map[echo_id] = future

            try:
                await self.ws.send(json.dumps(message))
                result = await asyncio.wait_for(future, timeout=call_timeout)

                if result.get("status") == "ok":
                    payload = result.get("data", {})
                    return payload if isinstance(payload, dict) else {}
                # 业务错误重试无意义，直接抛出
                raise RuntimeError(f"API调用失败: {result.get('msg', '未知错误')}")

            except RuntimeError:
                raise
            except self.RETRYABLE_EXCEPTIONS as e:
                if isinstance(e, asyncio.TimeoutError):
                    last_error = TimeoutError(
                        f"API调用超时 (尝试 {attempt + 1}/{attempts})"
                    )
                else:
                    last_error = e
            finally:
                self.echo_map.pop(echo_id, None)

            # 如果不是最后一次尝试，等待后重试
            if attempt < attempts - 1:
                if not self.connected or not self.ws:
                    raise ConnectionError(
                        f"重试前连接已断开，放弃调用 {action}"
                    )
                logger.warning(
                    f"API调用失败，{retry_delay}秒后重试 "
                    f"({attempt + 1}/{attempts}): {last_error}"
                )
                await asyncio.sleep(retry_delay)

        # 所有重试都失败
        if last_error:
            raise last_error
        raise RuntimeError(f"API调用失败: 未知错误 (action={action})")

    # ==================== 上层契约 ====================

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """把非响应消息交给上层分发（由客户端层实现）"""
        raise NotImplementedError

    def get_performance_stats(self) -> dict[str, int | float | bool]:
        """获取性能统计信息

        Returns:
            性能统计字典
        """
        stats: dict[str, int | float | bool] = dict(self._perf_stats.copy())
        stats["reconnect_attempts"] = self._reconnect_attempts
        stats["is_connected"] = self._connected
        return stats


__all__: list[str] = ["TransportMixin"]
