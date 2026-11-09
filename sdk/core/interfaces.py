"""
核心接口定义
提供抽象接口与 Protocol，降低模块间耦合度，所有接口均为强类型声明
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import (
    Any,
    Protocol,
    TypeAlias,
    runtime_checkable,
)

# 消息段类型
MessageSegmentType = dict[str, Any]

logger = logging.getLogger(__name__)

# ---- 基础类型别名 ----
APIResponse: TypeAlias = dict[str, Any]
EventHandler: TypeAlias = Callable[[dict[str, Any]], Awaitable[None]]


# ==================== 客户端接口 ====================

@runtime_checkable
class IClient(Protocol):
    """客户端 Protocol —— 定义所有客户端必须实现的方法签名"""

    # ---- 连接状态 ----
    @property
    def connected(self) -> bool:
        """是否已连接到服务端"""
        ...

    async def connect(self, max_retries: int | None = None) -> bool:
        """建立连接（支持重试）

        Args:
            max_retries: 最大重试次数，None 使用默认值

        Returns:
            bool —— 是否连接成功
        """
        ...

    async def disconnect(self, force: bool = False) -> None:
        """断开连接

        Args:
            force: 是否强制断开
        """
        ...

    # ---- API 调用 ----
    async def call(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        max_retries: int | None = None,
        retry_delay: float = 1.0,
        timeout: float | None = None,
    ) -> APIResponse:
        """调用底层 API

        Args:
            action: API 动作名称
            params: 参数
            max_retries: 最大尝试次数（含首次），缺省由实现决定
            retry_delay: 重试间隔（秒）
            timeout: 单次调用超时（秒）

        Returns:
            APIResponse —— API 返回的 data 字段

        Raises:
            ConnectionError: 未连接到服务端
            TimeoutError: 调用超时
        """
        ...

    # ---- 消息发送 ----
    async def send_private_message(
        self,
        user_id: int,
        message: str = "",
        image_path: str | None = None,
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送私聊消息

        Args:
            user_id: 用户 ID
            message: 文字内容
            image_path: 图片路径（可选）
            reply_message_id: 回复的消息 ID（可选）

        Returns:
            APIResponse
        """
        ...

    async def send_group_message(
        self,
        group_id: int,
        message: str = "",
        image_path: str | None = None,
        at_user_id: int | None = None,
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送群聊消息

        Args:
            group_id: 群 ID
            message: 文字内容
            image_path: 图片路径（可选）
            at_user_id: @ 的用户 ID（可选）
            reply_message_id: 回复的消息 ID（可选）

        Returns:
            APIResponse
        """
        ...

    # ---- 段消息发送 ----
    async def send_group_message_segments(
        self,
        group_id: int,
        segments: list[MessageSegmentType],
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送图文混排群消息（数组格式）"""
        ...

    async def send_private_message_segments(
        self,
        user_id: int,
        segments: list[MessageSegmentType],
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送图文混排私聊消息（数组格式）"""
        ...

    async def send_event_message(
        self,
        event: Any,
        message: str = "",
        message_segments: list[MessageSegmentType] | None = None,
        image_path: str | None = None,
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """按事件来源统一回复（自动识别群聊/私聊）"""
        ...

    # ---- 发送消息（post_ 风格别名）----
    async def post_group_message(
        self,
        group_id: int,
        message: str = "",
        image_path: str | None = None,
        at_user_id: int | None = None,
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送群聊消息（``send_group_message`` 别名）"""
        ...

    async def post_private_message(
        self,
        user_id: int,
        message: str = "",
        image_path: str | None = None,
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送私聊消息（``send_private_message`` 别名）"""
        ...

    async def post_group_message_segments(
        self,
        group_id: int,
        segments: list[MessageSegmentType],
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送群聊消息段（``send_group_message_segments`` 别名）"""
        ...

    async def post_private_message_segments(
        self,
        user_id: int,
        segments: list[MessageSegmentType],
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送私聊消息段（``send_private_message_segments`` 别名）"""
        ...

    # ---- 消息管理 ----
    async def delete_message(self, message_id: int) -> APIResponse:
        """撤回/删除消息"""
        ...

    async def get_message(self, message_id: int) -> APIResponse:
        """获取指定消息"""
        ...

    # ---- 群组管理 ----
    async def get_group_list(self) -> APIResponse:
        """获取群列表"""
        ...

    async def get_group_member_list(self, group_id: int) -> APIResponse:
        """获取群成员列表"""
        ...

    async def get_group_member_info(self, group_id: int, user_id: int) -> APIResponse:
        """获取群成员信息"""
        ...

    async def set_group_ban(self, group_id: int, user_id: int, duration: int = 1800) -> APIResponse:
        """设置群禁言"""
        ...

    async def set_group_kick(self, group_id: int, user_id: int, reject_add_request: bool = False) -> APIResponse:
        """踢出群成员"""
        ...

    async def set_group_card(self, group_id: int, user_id: int, card: str = "") -> APIResponse:
        """设置群成员名片"""
        ...

    async def get_group_info(self, group_id: int, no_cache: bool = False) -> APIResponse:
        """获取群信息"""
        ...

    async def set_group_whole_ban(self, group_id: int, enable: bool = True) -> APIResponse:
        """设置群全员禁言"""
        ...

    async def set_group_admin(self, group_id: int, user_id: int, enable: bool = True) -> APIResponse:
        """设置群管理员"""
        ...

    async def set_group_name(self, group_id: int, group_name: str) -> APIResponse:
        """设置群名"""
        ...

    async def set_group_leave(self, group_id: int, is_dismiss: bool = False) -> APIResponse:
        """退出群聊"""
        ...

    # ---- 好友管理 ----
    async def get_friend_list(self) -> APIResponse:
        """获取好友列表"""
        ...

    async def get_login_info(self) -> APIResponse:
        """获取登录信息"""
        ...

    async def get_stranger_info(self, user_id: int) -> APIResponse:
        """获取陌生人信息"""
        ...

    # ---- 请求处理 ----
    async def set_friend_add_request(self, flag: str, approve: bool = True, remark: str = "") -> APIResponse:
        """处理好友请求"""
        ...

    async def set_group_add_request(self, flag: str, sub_type: str, approve: bool = True, reason: str = "") -> APIResponse:
        """处理群请求"""
        ...

    async def send_like(self, user_id: int, times: int = 1) -> APIResponse:
        """发送赞"""
        ...

    async def get_version_info(self) -> APIResponse:
        """获取版本信息"""
        ...

    # ---- 状态查询 ----
    async def get_status(self) -> APIResponse:
        """获取运行状态"""
        ...

    async def can_send_image(self) -> bool:
        """检测是否可以发送图片"""
        ...

    async def can_send_record(self) -> bool:
        """检测是否可以发送语音"""
        ...

    async def get_image(self, file: str) -> APIResponse:
        """获取图片信息"""
        ...

    async def get_record(self, file: str, out_format: str = "mp3") -> APIResponse:
        """获取语音信息"""
        ...

    async def get_forward_msg(self, message_id: str) -> APIResponse:
        """获取合并转发消息内容"""
        ...

    # ---- 事件注册 ----
    def on_message(self, message_type: str) -> Callable[[EventHandler], EventHandler]:
        """装饰器 —— 注册消息处理器

        Args:
            message_type: 消息类型（'group' / 'private' / 'notice' / 'request'）

        Returns:
            装饰器函数，接收 EventHandler 并返回 EventHandler
        """
        ...

    # ---- 连接事件监听 ----
    def add_connection_listener(self, listener: Any) -> None:
        """添加连接事件监听器"""
        ...

    def remove_connection_listener(self, listener: Any) -> None:
        """移除连接事件监听器"""
        ...

    # ---- 性能统计 ----
    def get_performance_stats(self) -> dict[str, Any]:
        """获取性能统计信息"""
        ...


# ==================== 连接事件监听器接口 ====================

class IConnectionEventListener(ABC):
    """连接事件监听器接口 —— 观察 WebSocket 连接状态变化"""

    @abstractmethod
    async def on_connected(self) -> None:
        """连接建立回调"""
        ...

    @abstractmethod
    async def on_disconnected(self) -> None:
        """连接断开回调"""
        ...

    @abstractmethod
    async def on_reconnecting(self, attempt: int) -> None:
        """开始重连回调

        Args:
            attempt: 当前重连尝试次数
        """
        ...

    @abstractmethod
    async def on_reconnect_success(self) -> None:
        """重连成功回调"""
        ...

    @abstractmethod
    async def on_reconnect_failed(self, error: Exception) -> None:
        """重连失败回调（已达最大次数）

        Args:
            error: 失败原因
        """
        ...
