"""
OneBot API 封装

把常用的 OneBot 11 动作（发消息 / 群管 / 查询 / 请求处理）收拢为强类型方法，
底层统一走 ``TransportMixin.call()``，本模块不关心连接与重连细节。
"""

from __future__ import annotations

import logging
from typing import Any

from sdk.core.interfaces import APIResponse, MessageSegmentType
from sdk.core.messages import MessageSegment

logger = logging.getLogger(__name__)


class APIMixin:
    """OneBot 动作封装（与 :class:`~sdk.core.transport.TransportMixin` 组合使用）"""

    # ======================== 发送消息 ========================

    async def send_private_message(
        self,
        user_id: int,
        message: str = "",
        image_path: str | None = None,
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送私聊消息（数组格式，更安全可靠）

        Args:
            user_id: 用户ID
            message: 消息内容
            image_path: 图片文件路径（可选）
            reply_message_id: 回复的消息ID（可选）

        Returns:
            API响应数据
        """
        segments: list[MessageSegmentType] = []

        if reply_message_id is not None:
            segments.append(MessageSegment.reply(reply_message_id))

        if message:
            segments.append(MessageSegment.text(message))

        if image_path:
            segments.append(MessageSegment.image(image_path))

        return await self.call("send_private_msg", {
            "user_id": user_id,
            "message": segments,
        })

    async def send_group_message(
        self,
        group_id: int,
        message: str = "",
        image_path: str | None = None,
        at_user_id: int | None = None,
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送群聊消息（数组格式，更安全可靠）

        Args:
            group_id: 群ID
            message: 消息内容
            image_path: 图片文件路径（可选）
            at_user_id: @的用户ID（可选）
            reply_message_id: 回复的消息ID（可选）

        Returns:
            API响应数据
        """
        segments: list[MessageSegmentType] = []

        if reply_message_id is not None:
            segments.append(MessageSegment.reply(reply_message_id))

        if at_user_id is not None:
            segments.append(MessageSegment.at(at_user_id))

        if message:
            segments.append(MessageSegment.text(message))

        if image_path:
            segments.append(MessageSegment.image(image_path))

        return await self.call("send_group_msg", {
            "group_id": group_id,
            "message": segments,
        })

    async def send_group_message_segments(
        self,
        group_id: int,
        segments: list[MessageSegmentType],
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送图文混排群消息（数组格式，推荐）

        Args:
            group_id: 群号
            segments: 消息段列表，使用 MessageSegment 构建
            reply_message_id: 回复的消息 ID（可选）

        Example:
            ```python
            await client.send_group_message_segments(
                group_id=123,
                segments=[
                    MessageSegment.text("你好，"),
                    MessageSegment.image("https://example.com/pic.png"),
                    MessageSegment.text("这是图片！"),
                ]
            )
            ```
        """
        msg_segments = list(segments)
        if reply_message_id is not None:
            msg_segments.insert(0, MessageSegment.reply(reply_message_id))

        return await self.call("send_group_msg", {
            "group_id": group_id,
            "message": msg_segments,
        })

    async def send_private_message_segments(
        self,
        user_id: int,
        segments: list[MessageSegmentType],
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送图文混排私聊消息（数组格式，推荐）

        Args:
            user_id: 用户ID
            segments: 消息段列表，使用 MessageSegment 构建
            reply_message_id: 回复的消息 ID（可选）

        Example:
            ```python
            await client.send_private_message_segments(
                user_id=123,
                segments=[
                    MessageSegment.text("你好，"),
                    MessageSegment.image("https://example.com/pic.png"),
                    MessageSegment.text("这是图片！"),
                ]
            )
            ```
        """
        msg_segments = list(segments)
        if reply_message_id is not None:
            msg_segments.insert(0, MessageSegment.reply(reply_message_id))

        return await self.call("send_private_msg", {
            "user_id": user_id,
            "message": msg_segments,
        })

    # ======================== post_ 风格别名（简洁调用） ========================

    async def post_group_message(
        self,
        group_id: int,
        message: str = "",
        image_path: str | None = None,
        at_user_id: int | None = None,
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送群聊消息（send_group_message 别名）"""
        return await self.send_group_message(
            group_id, message, image_path, at_user_id, reply_message_id
        )

    async def post_private_message(
        self,
        user_id: int,
        message: str = "",
        image_path: str | None = None,
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送私聊消息（send_private_message 别名）"""
        return await self.send_private_message(
            user_id, message, image_path, reply_message_id
        )

    async def post_group_message_segments(
        self,
        group_id: int,
        segments: list[MessageSegmentType],
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送群聊消息（消息段，send_group_message_segments 别名）"""
        return await self.send_group_message_segments(
            group_id, segments, reply_message_id
        )

    async def post_private_message_segments(
        self,
        user_id: int,
        segments: list[MessageSegmentType],
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """发送私聊消息（消息段，send_private_message_segments 别名）"""
        return await self.send_private_message_segments(
            user_id, segments, reply_message_id
        )

    async def send_event_message(
        self,
        event: Any,
        message: str = "",
        message_segments: list[MessageSegmentType] | None = None,
        image_path: str | None = None,
        reply_message_id: int | None = None,
    ) -> APIResponse:
        """按事件来源统一回复（自动识别群聊/私聊）

        Args:
            event: 事件对象（需有 group_id 或 user_id 属性）
            message: 文本消息（与 message_segments 二选一）
            message_segments: 消息段列表（与 message 二选一）
            image_path: 图片路径（可选）
            reply_message_id: 回复消息 ID（可选）

        Returns:
            API 调用结果
        """
        group_id = getattr(event, "group_id", None)
        user_id = getattr(event, "user_id", None)

        if group_id:
            if message_segments is not None:
                return await self.send_group_message_segments(
                    group_id, message_segments, reply_message_id=reply_message_id,
                )
            return await self.send_group_message(
                group_id, message, image_path=image_path,
                reply_message_id=reply_message_id,
            )

        if user_id:
            if message_segments is not None:
                return await self.send_private_message_segments(
                    user_id, message_segments, reply_message_id=reply_message_id,
                )
            return await self.send_private_message(
                user_id, message, image_path=image_path,
                reply_message_id=reply_message_id,
            )

        logger.warning("send_event_message: 事件无 group_id 或 user_id，无法回复")
        return {}

    # ======================== 消息管理 ========================

    async def delete_message(self, message_id: int) -> APIResponse:
        """撤回/删除消息

        Args:
            message_id: 消息ID

        Returns:
            API响应数据
        """
        return await self.call("delete_msg", {"message_id": message_id})

    async def get_message(self, message_id: int) -> APIResponse:
        """获取指定消息

        Args:
            message_id: 消息ID

        Returns:
            API响应数据
        """
        return await self.call("get_msg", {"message_id": message_id})

    async def get_group_message_history(
        self,
        group_id: int,
        message_seq: int | None = None,
        count: int = 20,
        reverse_order: bool = False,
    ) -> APIResponse:
        """获取群消息历史记录

        Args:
            group_id: 群号
            message_seq: 消息序号，提供则从该消息开始获取
            count: 获取数量，默认20
            reverse_order: 是否倒序，默认False

        Returns:
            API响应数据
        """
        params: dict[str, Any] = {
            "group_id": group_id,
            "count": count,
            "reverseOrder": reverse_order,
        }
        if message_seq is not None:
            params["message_seq"] = message_seq

        return await self.call("get_group_msg_history", params)

    async def get_private_message_history(
        self,
        user_id: int,
        message_seq: int,
        count: int = 20,
        reverse_order: bool = False,
    ) -> APIResponse:
        """获取私聊消息历史记录

        Args:
            user_id: 用户ID
            message_seq: 消息序号
            count: 获取数量，默认20
            reverse_order: 是否倒序，默认False

        Returns:
            API响应数据
        """
        return await self.call("get_friend_msg_history", {
            "user_id": user_id,
            "message_seq": message_seq,
            "count": count,
            "reverseOrder": reverse_order,
        })

    # ======================== 互动 ========================

    async def group_poke(self, group_id: int, user_id: int) -> APIResponse:
        """群内戳一戳

        Args:
            group_id: 群号
            user_id: 要戳的用户ID

        Returns:
            API响应数据
        """
        return await self.call("group_poke", {
            "group_id": group_id,
            "user_id": user_id,
        })

    async def friend_poke(self, user_id: int) -> APIResponse:
        """好友戳一戳

        Args:
            user_id: 要戳的用户ID

        Returns:
            API响应数据
        """
        return await self.call("friend_poke", {"user_id": user_id})

    async def send_group_dice(self, group_id: int) -> APIResponse:
        """发送群骰子消息

        Args:
            group_id: 群号

        Returns:
            API响应数据
        """
        return await self.call("send_group_msg", {
            "group_id": group_id,
            "message": [MessageSegment.dice()],
        })

    async def send_group_rps(self, group_id: int) -> APIResponse:
        """发送群猜拳消息

        Args:
            group_id: 群号

        Returns:
            API响应数据
        """
        return await self.call("send_group_msg", {
            "group_id": group_id,
            "message": [MessageSegment.rps()],
        })

    async def send_private_dice(self, user_id: int) -> APIResponse:
        """发送私聊骰子消息

        Args:
            user_id: 用户ID

        Returns:
            API响应数据
        """
        return await self.call("send_private_msg", {
            "user_id": user_id,
            "message": [MessageSegment.dice()],
        })

    async def send_private_rps(self, user_id: int) -> APIResponse:
        """发送私聊猜拳消息

        Args:
            user_id: 用户ID

        Returns:
            API响应数据
        """
        return await self.call("send_private_msg", {
            "user_id": user_id,
            "message": [MessageSegment.rps()],
        })

    # ======================== 群组管理 ========================

    async def get_group_list(self) -> APIResponse:
        """获取群列表

        Returns:
            API响应数据
        """
        return await self.call("get_group_list")

    async def get_group_member_list(self, group_id: int) -> APIResponse:
        """获取群成员列表

        Args:
            group_id: 群号

        Returns:
            API响应数据
        """
        return await self.call("get_group_member_list", {"group_id": group_id})

    async def get_group_member_info(self, group_id: int, user_id: int) -> APIResponse:
        """获取群成员信息

        Args:
            group_id: 群号
            user_id: 用户ID

        Returns:
            API响应数据
        """
        return await self.call("get_group_member_info", {
            "group_id": group_id,
            "user_id": user_id,
        })

    async def set_group_ban(
        self, group_id: int, user_id: int, duration: int = 1800
    ) -> APIResponse:
        """设置群禁言

        Args:
            group_id: 群号
            user_id: 用户ID
            duration: 禁言时长（秒），默认1800秒

        Returns:
            API响应数据
        """
        return await self.call("set_group_ban", {
            "group_id": group_id,
            "user_id": user_id,
            "duration": duration,
        })

    async def set_group_kick(
        self, group_id: int, user_id: int, reject_add_request: bool = False
    ) -> APIResponse:
        """踢出群成员

        Args:
            group_id: 群号
            user_id: 用户ID
            reject_add_request: 是否拒绝后续加群请求

        Returns:
            API响应数据
        """
        return await self.call("set_group_kick", {
            "group_id": group_id,
            "user_id": user_id,
            "reject_add_request": reject_add_request,
        })

    async def set_group_card(
        self, group_id: int, user_id: int, card: str = ""
    ) -> APIResponse:
        """设置群成员名片

        Args:
            group_id: 群号
            user_id: 用户ID
            card: 名片内容，空字符串表示取消

        Returns:
            API响应数据
        """
        return await self.call("set_group_card", {
            "group_id": group_id,
            "user_id": user_id,
            "card": card,
        })

    async def get_group_info(
        self, group_id: int, no_cache: bool = False
    ) -> APIResponse:
        """获取群信息

        Args:
            group_id: 群号
            no_cache: 是否不使用缓存

        Returns:
            API响应数据
        """
        return await self.call("get_group_info", {
            "group_id": group_id,
            "no_cache": no_cache,
        })

    async def set_group_whole_ban(
        self, group_id: int, enable: bool = True
    ) -> APIResponse:
        """设置群全员禁言

        Args:
            group_id: 群号
            enable: 是否开启

        Returns:
            API响应数据
        """
        return await self.call("set_group_whole_ban", {
            "group_id": group_id,
            "enable": enable,
        })

    async def set_group_admin(
        self, group_id: int, user_id: int, enable: bool = True
    ) -> APIResponse:
        """设置群管理员

        Args:
            group_id: 群号
            user_id: 用户ID
            enable: 是否设为管理员

        Returns:
            API响应数据
        """
        return await self.call("set_group_admin", {
            "group_id": group_id,
            "user_id": user_id,
            "enable": enable,
        })

    async def set_group_name(self, group_id: int, group_name: str) -> APIResponse:
        """设置群名

        Args:
            group_id: 群号
            group_name: 新群名

        Returns:
            API响应数据
        """
        return await self.call("set_group_name", {
            "group_id": group_id,
            "group_name": group_name,
        })

    async def set_group_leave(
        self, group_id: int, is_dismiss: bool = False
    ) -> APIResponse:
        """退出群聊

        Args:
            group_id: 群号
            is_dismiss: 是否解散（仅群主有效）

        Returns:
            API响应数据
        """
        return await self.call("set_group_leave", {
            "group_id": group_id,
            "is_dismiss": is_dismiss,
        })

    async def set_group_special_title(
        self, group_id: int, user_id: int, special_title: str = ""
    ) -> APIResponse:
        """设置群专属头衔

        Args:
            group_id: 群号
            user_id: 用户ID
            special_title: 头衔（空串移除）

        Returns:
            API响应数据
        """
        return await self.call("set_group_special_title", {
            "group_id": group_id,
            "user_id": user_id,
            "special_title": special_title,
        })

    async def get_group_honor_info(self, group_id: int, type_: str) -> APIResponse:
        """获取群荣誉信息

        Args:
            group_id: 群号
            type_: 类型（talk / performer / legend / strong_newbie / emotion / all）

        Returns:
            API响应数据
        """
        return await self.call("get_group_honor_info", {
            "group_id": group_id,
            "type": type_,
        })

    async def get_group_at_all_remain(self, group_id: int) -> APIResponse:
        """获取群 @全体成员 剩余次数

        Args:
            group_id: 群号

        Returns:
            API响应数据
        """
        return await self.call("get_group_at_all_remain", {"group_id": group_id})

    async def send_group_notice(
        self, group_id: int, content: str, image: str = ""
    ) -> APIResponse:
        """发送群公告（扩展 API）

        Args:
            group_id: 群号
            content: 公告内容
            image: 公告图片路径（可选）

        Returns:
            API响应数据
        """
        params: dict[str, Any] = {
            "group_id": group_id,
            "content": content,
        }
        if image:
            params["image"] = image
        return await self.call("send_group_notice", params)

    async def set_essence_msg(self, message_id: int) -> APIResponse:
        """设置精华消息（扩展 API）

        Args:
            message_id: 消息ID

        Returns:
            API响应数据
        """
        return await self.call("set_essence_msg", {"message_id": message_id})

    # ======================== 好友管理 ========================

    async def get_friend_list(self) -> APIResponse:
        """获取好友列表

        Returns:
            API响应数据
        """
        return await self.call("get_friend_list")

    async def get_login_info(self) -> APIResponse:
        """获取登录信息

        Returns:
            API响应数据
        """
        return await self.call("get_login_info")

    async def get_stranger_info(self, user_id: int) -> APIResponse:
        """获取陌生人信息

        Args:
            user_id: 用户ID

        Returns:
            API响应数据
        """
        return await self.call("get_stranger_info", {"user_id": user_id})

    # ======================== 状态查询 ========================

    async def get_status(self) -> APIResponse:
        """获取运行状态

        Returns:
            API响应数据
        """
        return await self.call("get_status")

    async def can_send_image(self) -> bool:
        """检测是否可以发送图片

        Returns:
            是否可以发送图片
        """
        result = await self.call("can_send_image")
        return bool(result.get("yes", False))

    async def can_send_record(self) -> bool:
        """检测是否可以发送语音

        Returns:
            是否可以发送语音
        """
        result = await self.call("can_send_record")
        return bool(result.get("yes", False))

    async def get_image(self, file: str) -> APIResponse:
        """获取图片信息

        Args:
            file: 图片文件名（收到消息中的 image 段 file 字段）

        Returns:
            API响应数据（含 file 本地路径、size、filename、url）
        """
        return await self.call("get_image", {"file": file})

    async def get_record(self, file: str, out_format: str = "mp3") -> APIResponse:
        """获取语音信息

        Args:
            file: 语音文件名（收到消息中的 record 段 file 字段）
            out_format: 输出格式（mp3/amr/wma/m4a/spx/ogg/wav/flac）

        Returns:
            API响应数据（含 file 本地路径）
        """
        return await self.call("get_record", {
            "file": file,
            "out_format": out_format,
        })

    async def get_forward_msg(self, message_id: str) -> APIResponse:
        """获取合并转发消息内容

        Args:
            message_id: 转发消息 ID（forward 段的 id 字段）

        Returns:
            API响应数据（含 messages 节点列表）
        """
        return await self.call("get_forward_msg", {"message_id": message_id})

    async def get_credentials(self, domain: str = "") -> APIResponse:
        """获取登录凭证（Cookies 与 CSRF Token）

        Args:
            domain: 需要获取 cookies 的域名（空串为全部）

        Returns:
            API响应数据
        """
        return await self.call("get_credentials", {"domain": domain})

    # ======================== 请求处理 ========================

    async def set_friend_add_request(
        self, flag: str, approve: bool = True, remark: str = ""
    ) -> APIResponse:
        """处理好友请求

        Args:
            flag: 请求标识
            approve: 是否同意
            remark: 备注名

        Returns:
            API响应数据
        """
        return await self.call("set_friend_add_request", {
            "flag": flag,
            "approve": approve,
            "remark": remark,
        })

    async def set_group_add_request(
        self, flag: str, sub_type: str, approve: bool = True, reason: str = ""
    ) -> APIResponse:
        """处理群请求

        Args:
            flag: 请求标识
            sub_type: 请求子类型（add/invite）
            approve: 是否同意
            reason: 拒绝理由

        Returns:
            API响应数据
        """
        return await self.call("set_group_add_request", {
            "flag": flag,
            "sub_type": sub_type,
            "approve": approve,
            "reason": reason,
        })

    async def send_like(self, user_id: int, times: int = 1) -> APIResponse:
        """发送赞

        Args:
            user_id: 用户ID
            times: 点赞次数

        Returns:
            API响应数据
        """
        return await self.call("send_like", {
            "user_id": user_id,
            "times": times,
        })

    async def get_version_info(self) -> APIResponse:
        """获取版本信息

        Returns:
            API响应数据
        """
        return await self.call("get_version_info")

    # ======================== 上层契约 ========================

    async def call(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        max_retries: int | None = None,
        retry_delay: float = 1.0,
        timeout: float | None = None,
    ) -> APIResponse:
        """调用底层 API（由 ``TransportMixin`` 提供实现）"""
        raise NotImplementedError


__all__: list[str] = ["APIMixin"]
