"""
pintu 插件 - 九宫格拼图游戏接口
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from sdk.core.events import GroupMessageEvent
from sdk.pluginsystem import PluginBase, filter_registry

from .logic import (
    CORRECT_ORDER,
    HELP_TEXT,
    GameService,
    GameSession,
)

PLUGIN_DIR = Path(__file__).resolve().parent


class PintuPlugin(PluginBase):
    """九宫格拼图游戏插件"""

    def __init__(self) -> None:
        super().__init__()
        self.name = "Pintu"
        self.version = "1.0.0"
        self.description = "九宫格拼图游戏，支持多人协作完成拼图"
        self.author = "pintu"
        self.game = GameService()

    async def on_load(self, api, event_bus, plugin_dir: Optional[Path] = None) -> None:
        await super().on_load(api, event_bus, plugin_dir)
        print(f"{self.name} 插件已加载 (v{self.version})")

    # ==================== 消息路由 ====================

    @filter_registry.group_server()
    async def on_group_message(self, event: GroupMessageEvent) -> None:
        text = event.message.plain_text.strip()
        if not text:
            return

        group_id = event.group_id
        user_id = event.user_id

        if text in {"帮助", "/help"}:
            await self.api.send_group_message(group_id, HELP_TEXT)
            return

        if text in {"状态", "/puzzle"}:
            await self._send_status(group_id)
            return

        if text in {"得分", "/score"}:
            await self._send_score(group_id)
            return

        if text in {"开拼图", "开始拼图", "/startgame"}:
            await self._start_game(event)
            return

        if text in {"结算", "结束拼图", "/endgame"}:
            await self._end_game(event)
            return

        if text in {"重开", "重置拼图", "/resetpuzzle"}:
            await self._reset_puzzle(event)
            return

        if text.startswith("拼图加管"):
            await self._add_admin(event, text)
            return

        if text.startswith("拼图删管"):
            await self._remove_admin(event, text)
            return

        if text == "拼图管理":
            await self._list_admins(event)
            return

        swap = self.game.parse_swap(text)
        if swap:
            await self._handle_swap(event, *swap)
            return

        if text.startswith("交换") or "换" in text:
            await self.api.send_group_message(group_id, "指令格式错误，示例：9换1 或 交换 4 7")

    # ==================== 游戏管理 ====================

    async def _start_game(self, event: GroupMessageEvent) -> None:
        group_id = event.group_id
        if not self.game.is_admin(event.user_id):
            await self.api.send_group_message(group_id, "只有拼图管理员可以开始游戏。")
            return

        session = self.game.get_session(group_id)
        if session.active:
            await self.api.send_group_message(group_id, "已有进行中的游戏，请先使用 结算 结束当前对局。")
            return

        image_path = self.game.choose_image()
        if not image_path:
            await self.api.send_group_message(group_id, "本地图片文件夹为空，请先向 plugins/pintu/tupina 添加图片。")
            return

        try:
            tiles, piece_size = self.game.load_tiles(image_path)
        except Exception:
            await self.api.send_group_message(group_id, "图片加载失败，请检查图片文件是否损坏。")
            return

        session.active = True
        session.original_image_path = str(image_path)
        session.tiles = tiles
        session.piece_size = piece_size
        session.scores = {}
        self.game.shuffle(session)
        image = self.game.save_puzzle_image(session)

        await self._send_image(
            group_id, image,
            '游戏开始！图片已随机选择并打乱。发送"9换1"或"交换 4 7"交换碎片。当前拼图如下：',
        )

    async def _end_game(self, event: GroupMessageEvent) -> None:
        group_id = event.group_id
        if not self.game.is_admin(event.user_id):
            await self.api.send_group_message(group_id, "只有拼图管理员可以结束游戏。")
            return

        session = self.game.get_session(group_id)
        if not session.active:
            await self.api.send_group_message(group_id, "当前没有进行中的游戏，无需结束。")
            return

        session.active = False
        scores = session.scores.copy()

        if not scores:
            await self.api.send_group_message(group_id, "游戏结束！本局暂无玩家得分。")
            return

        ranking = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        highest = ranking[0][1]
        winners = [self.game.mention(int(uid)) for uid, score in ranking if score == highest]
        detail = "，".join(f"{self.game.mention(int(uid))}({score}分)" for uid, score in ranking)
        if len(winners) > 1:
            text = f"游戏结束！并列第一：{'，'.join(winners)}，得分 {highest}。完整排行：{detail}。恭喜！"
        else:
            text = f"游戏结束！胜利者：{winners[0]}，得分 {highest}。完整排行：{detail}。恭喜！"
        await self.api.send_group_message(group_id, text)

    async def _reset_puzzle(self, event: GroupMessageEvent) -> None:
        group_id = event.group_id
        if not self.game.is_admin(event.user_id):
            await self.api.send_group_message(group_id, "只有拼图管理员可以重置拼图。")
            return

        session = self.game.get_session(group_id)
        if not session.active:
            await self.api.send_group_message(group_id, "当前没有进行中的游戏，请管理员使用 开拼图 开始新对局。")
            return

        self.game.shuffle(session)
        image = self.game.save_puzzle_image(session)
        await self._send_image(group_id, image, "拼图已重新打乱，游戏继续！")

    async def _handle_swap(self, event: GroupMessageEvent, first: int, second: int) -> None:
        group_id = event.group_id
        user_id = event.user_id

        if first == second:
            await self.api.send_group_message(group_id, "不能交换同一个位置，请输入两个不同的数字。")
            return

        if not 1 <= first <= 9 or not 1 <= second <= 9:
            await self.api.send_group_message(group_id, "交换位置必须在 1~9 范围内。")
            return

        session = self.game.get_session(group_id)
        gained = False
        completed = False
        score = 0

        if not session.active:
            await self.api.send_group_message(group_id, "当前没有进行中的游戏，请管理员使用 开拼图 开始新对局。")
            return

        before_correct = self.game.count_correct_tiles(session.arrangement)
        session.arrangement[first - 1], session.arrangement[second - 1] = (
            session.arrangement[second - 1],
            session.arrangement[first - 1],
        )
        after_correct = self.game.count_correct_tiles(session.arrangement)
        if after_correct > before_correct:
            gained = True
            session.scores[str(user_id)] = session.scores.get(str(user_id), 0) + 1
            score = session.scores[str(user_id)]
        if session.arrangement == CORRECT_ORDER:
            completed = True
            self.game.shuffle(session)
        image = self.game.save_puzzle_image(session)

        if completed and gained:
            text = f"{self.game.mention(user_id)} 操作正确，获得 1 分，当前总分：{score}。拼图已完成并重新打乱，游戏继续！"
        elif gained:
            text = f"{self.game.mention(user_id)} 操作正确，获得 1 分，当前总分：{score}。"
        else:
            text = f"已交换位置 {first} 和 {second}，本次未得分。"
        await self._send_image(group_id, image, text)

    # ==================== 状态查询 ====================

    async def _send_status(self, group_id: int) -> None:
        session = self.game.get_session(group_id)
        if not session.active:
            await self.api.send_group_message(group_id, "当前没有进行中的游戏，请管理员使用 开拼图 开始新对局。")
            return
        image = self.game.save_puzzle_image(session)
        await self._send_image(group_id, image, "当前拼图状态：")

    async def _send_score(self, group_id: int) -> None:
        session = self.game.get_session(group_id)
        scores = session.scores.copy()

        if not session.active:
            await self.api.send_group_message(group_id, "当前没有进行中的游戏，请管理员使用 开拼图 开始新对局。")
            return

        if not scores:
            await self.api.send_group_message(group_id, "当前还没有玩家得分。")
            return

        ranking = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        lines = ["当前得分排行："]
        for index, (uid, s) in enumerate(ranking, 1):
            lines.append(f"{index}. {self.game.mention(int(uid))}：{s} 分")
        await self.api.send_group_message(group_id, "\n".join(lines))

    # ==================== 权限管理 ====================

    async def _add_admin(self, event: GroupMessageEvent, text: str) -> None:
        group_id = event.group_id
        if not self.game.is_admin(event.user_id):
            await self.api.send_group_message(group_id, "只有拼图管理员可以管理拼图权限。")
            return

        target = self.game.extract_target_user_id(text, "拼图加管", event.message.segments)
        if not target:
            await self.api.send_group_message(group_id, "格式错误，请使用：拼图加管 QQ号 或 拼图加管 @用户")
            return

        if self.game.add_admin(target):
            await self.api.send_group_message(group_id, f"已将 {target} 添加为拼图管理员。")
        else:
            await self.api.send_group_message(group_id, f"{target} 已经是拼图管理员。")

    async def _remove_admin(self, event: GroupMessageEvent, text: str) -> None:
        group_id = event.group_id
        if not self.game.is_admin(event.user_id):
            await self.api.send_group_message(group_id, "只有拼图管理员可以管理拼图权限。")
            return

        target = self.game.extract_target_user_id(text, "拼图删管", event.message.segments)
        if not target:
            await self.api.send_group_message(group_id, "格式错误，请使用：拼图删管 QQ号 或 拼图删管 @用户")
            return

        if str(target) == str(event.user_id) and len(self.game.get_admins()) <= 1:
            await self.api.send_group_message(group_id, "不能移除最后一个拼图管理员。")
            return

        if self.game.remove_admin(target):
            await self.api.send_group_message(group_id, f"已移除拼图管理员 {target}。")
        else:
            await self.api.send_group_message(group_id, f"{target} 不是拼图管理员。")

    async def _list_admins(self, event: GroupMessageEvent) -> None:
        group_id = event.group_id
        if not self.game.is_admin(event.user_id):
            await self.api.send_group_message(group_id, "只有拼图管理员可以查看拼图权限。")
            return

        admins = self.game.get_admins()
        if not admins:
            await self.api.send_group_message(group_id, "暂无拼图管理员。")
            return

        admin_list = "\n".join(f"- {a}" for a in admins)
        await self.api.send_group_message(group_id, f"拼图管理员名单：\n{admin_list}")

    # ==================== 消息发送 ====================

    async def _send_image(self, group_id: int, image_path: Path, text: str) -> None:
        await self.api.send_group_message(group_id, text, image_path=str(image_path))
