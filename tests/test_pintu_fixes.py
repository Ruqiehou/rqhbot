"""回归测试：pintu 插件的刷分、引导管理员、分群管理员与消息/临时文件健壮性修复"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from PIL import Image

from plugins.pintu import config_manager, logic
from plugins.pintu.logic import CORRECT_ORDER, GameService
from plugins.pintu.main import PintuPlugin

# 单条消息里最多展示的 at 人数（与实现约定一致）
AT_LIMIT = 10


def _event(group_id: int, user_id: int, text: str = "") -> MagicMock:
    event = MagicMock()
    event.group_id = group_id
    event.user_id = user_id
    event.message.plain_text = text
    event.message.segments = []
    return event


def _make_plugin(tmp_path, monkeypatch) -> PintuPlugin:
    """构造插件，并把临时图片目录指向 tmp_path，绝不写真实插件目录"""
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    monkeypatch.setattr(logic, "TEMP_DIR", temp_dir)
    plugin = PintuPlugin()
    plugin.api = MagicMock()
    plugin.api.send_group_message = AsyncMock(return_value={"status": "ok"})
    plugin.api.send_group_message_segments = AsyncMock(return_value={"status": "ok"})
    return plugin


def _use_config(tmp_path, monkeypatch, payload: dict):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_manager, "_config", None)
    return config_path


# ==================== DEFECT 1：重复交换刷分 ====================


async def test_repeat_swap_cannot_farm_points(tmp_path, monkeypatch) -> None:
    plugin = _make_plugin(tmp_path, monkeypatch)
    session = plugin.game.get_session(1001)
    session.active = True
    session.tiles = [Image.new("RGB", (30, 30), (i * 10, 0, 0)) for i in range(9)]
    session.piece_size = (30, 30)
    session.arrangement = [2, 1, 4, 3, 5, 6, 7, 8, 9]
    session.scores = {}

    event = _event(1001, 2001, "1换2")
    await plugin._handle_swap(event, 1, 2)
    score_after_first = session.scores.get("2001", 0)
    assert score_after_first == 1

    # 反复来回交换同一个位置，分数不得再增长
    for _ in range(7):
        await plugin._handle_swap(event, 1, 2)

    assert session.scores.get("2001", 0) == score_after_first


async def test_new_correct_placement_still_scores(tmp_path, monkeypatch) -> None:
    plugin = _make_plugin(tmp_path, monkeypatch)
    session = plugin.game.get_session(1001)
    session.active = True
    session.tiles = [Image.new("RGB", (30, 30), (i * 10, 0, 0)) for i in range(9)]
    session.piece_size = (30, 30)
    session.arrangement = [2, 1, 4, 3, 5, 6, 7, 8, 9]
    session.scores = {}

    event = _event(1001, 2001)
    await plugin._handle_swap(event, 1, 2)  # 修正位置 1、2
    await plugin._handle_swap(event, 3, 4)  # 修正位置 3、4（首次）

    assert session.scores.get("2001", 0) == 2


# ==================== DEFECT 2：开箱即用的管理员引导 ====================


async def test_fresh_install_default_admin_can_start_game(tmp_path, monkeypatch) -> None:
    # 复现随包发布的空管理员列表
    _use_config(tmp_path, monkeypatch, {"admins": []})

    plugin = _make_plugin(tmp_path, monkeypatch)
    source = tmp_path / "source.png"
    Image.new("RGB", (90, 90), (10, 20, 30)).save(source)
    monkeypatch.setattr(plugin.game, "choose_image", lambda: source)

    default_admin = int(config_manager.DEFAULT_CONFIG["admins"][0])
    assert plugin.game.is_admin(default_admin) is True

    await plugin._start_game(_event(1001, default_admin, "开拼图"))

    session = plugin.game.get_session(1001)
    assert session.active is True


async def test_random_user_cannot_self_promote(tmp_path, monkeypatch) -> None:
    config_path = _use_config(tmp_path, monkeypatch, {"admins": []})

    plugin = _make_plugin(tmp_path, monkeypatch)
    await plugin._add_admin(_event(1001, 999999, "拼图加管 999999"), "拼图加管 999999")

    assert config_manager.is_puzzle_admin(999999) is False
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert "999999" not in saved.get("admins", [])
    # 默认管理员仍然是隐式/内置管理员，不会因为空列表而丢失
    assert config_manager.is_puzzle_admin(config_manager.DEFAULT_CONFIG["admins"][0]) is True


# ==================== DEFECT 3：管理员按群隔离（兼容旧扁平配置） ====================


async def test_group_admins_are_isolated_per_group(tmp_path, monkeypatch) -> None:
    _use_config(tmp_path, monkeypatch, {"admins": ["111"]})

    plugin = _make_plugin(tmp_path, monkeypatch)
    source = tmp_path / "source.png"
    Image.new("RGB", (90, 90), (10, 20, 30)).save(source)
    monkeypatch.setattr(plugin.game, "choose_image", lambda: source)

    # 全局管理员 111 在 A 群把 222 提升为管理员
    await plugin._add_admin(_event(2001, 111, "拼图加管 222"), "拼图加管 222")

    # 222 不能管理 B 群
    await plugin._start_game(_event(2002, 222, "开拼图"))
    assert plugin.game.get_session(2002).active is False

    await plugin._add_admin(_event(2002, 222, "拼图加管 333"), "拼图加管 333")
    assert plugin.game.is_admin(333, 2002) is False

    # 222 在 A 群是管理员，全局管理员 111 在所有群都是管理员
    assert plugin.game.is_admin(222, 2001) is True
    assert plugin.game.is_admin(222, 2002) is False
    assert plugin.game.is_admin(111, 2002) is True


def test_legacy_flat_admin_list_still_reads_as_global(tmp_path, monkeypatch) -> None:
    _use_config(tmp_path, monkeypatch, {"admins": ["111"]})

    assert config_manager.is_puzzle_admin("111") is True
    assert config_manager.is_puzzle_admin("111", group_id=999) is True


# ==================== DEFECT 4.1：at 段数量上限 ====================


def test_mention_and_ranking_segments_are_capped() -> None:
    users = [1000 + i for i in range(25)]
    mention_segments = PintuPlugin._mention_segments(users)
    assert sum(1 for seg in mention_segments if seg.get("type") == "at") <= AT_LIMIT
    mention_text = "".join(
        seg["data"]["text"] for seg in mention_segments if seg.get("type") == "text"
    )
    assert "25" in mention_text

    ranking = [(str(1000 + i), 1) for i in range(25)]
    ranking_segments = PintuPlugin._ranking_segments(ranking)
    assert sum(1 for seg in ranking_segments if seg.get("type") == "at") <= AT_LIMIT


async def test_score_ranking_caps_at_segments(tmp_path, monkeypatch) -> None:
    plugin = _make_plugin(tmp_path, monkeypatch)
    session = plugin.game.get_session(1001)
    session.active = True
    session.scores = {str(1000 + i): i for i in range(1, 26)}

    await plugin._send_score(1001)

    segments = plugin.api.send_group_message_segments.await_args.args[1]
    assert sum(1 for seg in segments if seg.get("type") == "at") <= AT_LIMIT
    text = "".join(seg["data"]["text"] for seg in segments if seg.get("type") == "text")
    assert "等25人" in text


# ==================== DEFECT 4.2：每次渲染唯一临时图 + 清理 ====================


def test_temp_board_path_unique_per_render(tmp_path, monkeypatch) -> None:
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    monkeypatch.setattr(logic, "TEMP_DIR", temp_dir)

    service = GameService()
    session = service.get_session(1001)
    session.tiles = [Image.new("RGB", (30, 30), (i * 10, 0, 0)) for i in range(9)]
    session.piece_size = (30, 30)

    session.arrangement = CORRECT_ORDER.copy()
    first = service.save_puzzle_image(session)
    session.arrangement = list(reversed(CORRECT_ORDER))
    second = service.save_puzzle_image(session)

    assert first != second
    assert first.exists() and second.exists()


async def test_sent_temp_image_is_cleaned_up(tmp_path, monkeypatch) -> None:
    plugin = _make_plugin(tmp_path, monkeypatch)
    image = tmp_path / "temp" / "board.jpg"
    image.write_bytes(b"fake-jpeg")

    await plugin._send_image(1001, image, "当前拼图状态：")

    assert image.exists() is False
