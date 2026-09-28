"""rqhshen 修仙插件回归测试（缺陷 1/2/3）。

所有玩家数据都写在 pytest 的 tmp_path 下，绝不落到 plugins/rqhshen/data/。
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from plugins.rqhshen import game
from plugins.rqhshen.game import Cultivator, CultivationSystem
from plugins.rqhshen.main import RqhshenPlugin
from sdk.core.events import GroupMessageEvent, Message


# ==================== 辅助 ====================


def _opened(**kwargs) -> Cultivator:
    """创建一个已开灵的修士（测试用）。"""
    kwargs.setdefault("username", "tester")
    kwargs.setdefault("qq_id", 1001)
    kwargs.setdefault("is_soul_opened", True)
    return Cultivator(**kwargs)


def _make_plugin(tmp_path) -> RqhshenPlugin:
    plugin = RqhshenPlugin()
    plugin.cultivation_system = CultivationSystem(data_dir=str(tmp_path))
    plugin.api = MagicMock()
    plugin.api.send_group_message = AsyncMock()
    plugin.api.send_private_message = AsyncMock()
    return plugin


def _last_reply(plugin: RqhshenPlugin) -> str:
    assert plugin.api.send_group_message.await_count == 1, "期望恰好回复一条消息"
    return plugin.api.send_group_message.await_args.args[1]


def _event(user_id: int, text: str, group_id: int = 1001) -> GroupMessageEvent:
    return GroupMessageEvent(group_id=group_id, user_id=user_id, message=Message(plain_text=text))


# ==================== 缺陷 1：打坐冷却 + 突破消耗修为 ====================


def test_meditate_cooldown_blocks_immediate_second_call() -> None:
    player = _opened()

    first = player.meditate()
    assert "修为增加" in first
    exp_after_first = player.exp
    gained_first = player.total_exp_gained
    assert gained_first > 0

    second = player.meditate()
    assert "修为增加" not in second, f"冷却期内不应再获得修为：{second!r}"
    assert player.exp == exp_after_first
    assert player.total_exp_gained == gained_first
    assert player.can_meditate() is False


def test_meditate_cooldown_is_persisted_and_reloaded(tmp_path) -> None:
    system = CultivationSystem(data_dir=str(tmp_path))
    player = system.load_player(1001, "1001")
    player.is_soul_opened = True
    player.meditate()
    assert player.last_meditate, "打坐后必须记录 last_meditate"
    system.save_player(player)

    reloaded = system.load_player(1001, "1001")
    assert reloaded.last_meditate == player.last_meditate
    assert reloaded.can_meditate() is False
    assert "修为增加" not in reloaded.meditate()


def test_meditate_cooldown_expires() -> None:
    player = _opened()
    player.last_meditate = (
        game.datetime.now() - timedelta(seconds=game.MEDITATION_COOLDOWN_SECONDS + 5)
    ).isoformat(timespec="seconds")

    assert player.can_meditate() is True
    assert "修为增加" in player.meditate()


def test_six_rapid_meditations_cannot_reach_realm_53() -> None:
    player = _opened()

    for _ in range(6):
        player.meditate()

    assert player.realm_index < 10, (
        f"连续 6 次打坐就冲到 realm_index={player.realm_index}，冷却没有生效"
    )
    assert player.total_breakthroughs == player.realm_index


def test_breakthrough_consumes_experience(monkeypatch) -> None:
    player = _opened(exp=game.SUB_REALM_THRESHOLDS[0])
    monkeypatch.setattr(game.random, "random", lambda: 0.0)  # 必定突破成功

    result = player.attempt_breakthrough()

    assert player.realm_index == 1
    assert player.exp == 0, f"突破必须扣除门槛修为，实际 exp={player.exp}"
    assert "突破成功" in result


def test_auto_breakthrough_in_meditate_consumes_experience(monkeypatch) -> None:
    player = _opened(exp=0)
    monkeypatch.setattr(game.random, "random", lambda: 0.0)  # 必定突破成功
    monkeypatch.setattr(game.random, "randint", lambda a, b: 100)  # 固定获得 100 修为

    player.meditate()

    # 前 9 个子境界每个门槛 11：9 * 11 = 99，剩余 1 点修为后卡在门槛 22。
    assert player.realm_index == 9, f"realm_index={player.realm_index}"
    assert player.exp == 1, f"突破必须消耗修为，实际 exp={player.exp}"


def test_meditation_gain_uses_experience_config() -> None:
    """jingjie.json 的 experience_settings 必须真正被使用。"""
    cfg = game.EXPERIENCE_CONFIG
    assert cfg, "EXPERIENCE_CONFIG 未加载"

    player = _opened(exp=1000)
    min_gain, max_gain = player._meditation_gain_range()
    assert min_gain == max(cfg["meditation_base_min"], int(1000 * cfg["meditation_relative_min_percent"]))
    assert max_gain == max(cfg["meditation_base_max"], int(1000 * cfg["meditation_relative_max_percent"]))


# ==================== 缺陷 2：损坏存档自愈 ====================


def test_corrupt_player_file_is_quarantined_and_reseeded(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    corrupted = data_dir / "player_999.json"
    original = '{"username": "999", "exp": 12, "realm_index": 3'
    corrupted.write_text(original, encoding="utf-8")

    system = CultivationSystem(data_dir=str(data_dir))
    player = system.load_player(999, "User_999")  # 不得抛异常

    assert player.realm_index == 0 and player.exp == 0
    assert player.recovery_notice, "恢复后必须给玩家一次提示"

    backups = [p for p in data_dir.glob("player_999.json*") if p.name != "player_999.json"]
    assert backups, "损坏的存档必须被备份而不是丢弃"
    assert backups[0].read_text(encoding="utf-8") == original

    # 新存档可用，且第二次加载不再提示（只提示一次）
    assert (data_dir / "player_999.json").exists()
    reloaded = system.load_player(999, "User_999")
    assert reloaded.recovery_notice is None
    assert reloaded.exp == 0


def test_undecodable_player_file_is_recovered(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "player_7.json").write_bytes(b"\xff\xfe\x00\x00bad bytes")

    system = CultivationSystem(data_dir=str(data_dir))
    player = system.load_player(7, "User_7")

    assert player is not None
    assert player.recovery_notice
    assert list(data_dir.glob("player_7.json.corrupt-*.bak"))


def test_non_object_player_file_is_recovered(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "player_8.json").write_text("[1, 2, 3]", encoding="utf-8")

    system = CultivationSystem(data_dir=str(data_dir))
    player = system.load_player(8, "User_8")

    assert player.exp == 0
    assert player.recovery_notice


@pytest.mark.asyncio
async def test_corrupt_file_does_not_brick_commands(tmp_path) -> None:
    plugin = _make_plugin(tmp_path)
    (tmp_path / "player_555.json").write_text('{"username": "555", "exp"', encoding="utf-8")

    await plugin.rqhbase_group(_event(555, "修仙状态"))
    first = _last_reply(plugin)
    assert "操作失败" not in first, f"损坏存档把玩家永久锁死了：{first!r}"
    assert "存档" in first

    plugin.api.send_group_message.reset_mock()
    await plugin.rqhbase_group(_event(555, "修仙状态"))
    second = _last_reply(plugin)
    assert "操作失败" not in second
    assert "存档" not in second, "恢复提示只应出现一次"


# ==================== 缺陷 3：README 命令接线 ====================


@pytest.mark.asyncio
async def test_router_ascension_reachable_and_persisted(tmp_path, monkeypatch) -> None:
    plugin = _make_plugin(tmp_path)
    system = plugin.cultivation_system
    player = system.load_player(1001, "1001")
    player.is_soul_opened = True
    player.realm_index = 72  # 主境界 9，可飞升
    player.exp = 100
    system.save_player(player)

    monkeypatch.setattr(game.random, "randint", lambda a, b: 1)  # 必定飞升成功
    await plugin.rqhbase_group(_event(1001, "飞升"))

    reply = _last_reply(plugin)
    assert "成功飞升" in reply, reply
    assert system.load_player(1001, "1001").is_ascended is True


@pytest.mark.asyncio
async def test_router_ascension_rejects_invalid_realm(tmp_path) -> None:
    plugin = _make_plugin(tmp_path)
    system = plugin.cultivation_system
    player = system.load_player(1001, "1001")
    player.is_soul_opened = True
    system.save_player(player)

    await plugin.rqhbase_group(_event(1001, "飞升"))

    assert "无法飞升" in _last_reply(plugin)


@pytest.mark.asyncio
async def test_router_challenge_and_attack_reachable(tmp_path) -> None:
    plugin = _make_plugin(tmp_path)
    system = plugin.cultivation_system
    me = system.load_player(1001, "1001")
    me.is_soul_opened = True
    me.exp = 500
    system.save_player(me)
    foe = system.load_player(2002, "User_2002")
    foe.is_soul_opened = True
    foe.exp = 100
    system.save_player(foe)

    await plugin.rqhbase_group(_event(1001, "挑战 2002"))
    reply = _last_reply(plugin)
    assert "战斗" in reply, reply

    plugin.api.send_group_message.reset_mock()
    await plugin.rqhbase_group(_event(1001, "攻击 2002"))
    reply = _last_reply(plugin)
    assert "攻击" in reply and ("成功" in reply or "失败" in reply), reply


@pytest.mark.asyncio
async def test_router_challenge_by_nickname(tmp_path) -> None:
    plugin = _make_plugin(tmp_path)
    system = plugin.cultivation_system
    me = system.load_player(1001, "1001")
    me.is_soul_opened = True
    me.exp = 500
    system.save_player(me)
    foe = system.load_player(2002, "剑仙道友")
    foe.is_soul_opened = True
    foe.exp = 100
    system.save_player(foe)

    await plugin.rqhbase_group(_event(1001, "挑战 剑仙道友"))

    assert "战斗" in _last_reply(plugin)


@pytest.mark.asyncio
async def test_router_challenge_unknown_target(tmp_path) -> None:
    plugin = _make_plugin(tmp_path)
    me = plugin.cultivation_system.load_player(1001, "1001")
    me.is_soul_opened = True
    plugin.cultivation_system.save_player(me)

    await plugin.rqhbase_group(_event(1001, "挑战 不存在的人"))

    assert "未找到玩家" in _last_reply(plugin)


@pytest.mark.asyncio
async def test_router_xiuxian_paihang_uses_ranking(tmp_path) -> None:
    plugin = _make_plugin(tmp_path)
    system = plugin.cultivation_system
    player = system.load_player(1001, "榜一大哥")
    player.is_soul_opened = True
    player.exp = 500
    system.save_player(player)

    await plugin.rqhbase_group(_event(1001, "修仙排行"))

    reply = _last_reply(plugin)
    assert "修仙排行榜" in reply, reply
    assert "榜一大哥" in reply


def test_router_help_lists_documented_commands() -> None:
    help_text = game.get_help_text()
    for keyword in ("飞升", "挑战", "攻击", "排行"):
        assert keyword in help_text, f"帮助里缺少 README 记载的 {keyword}"


# ==================== 文档/常量一致性 ====================


def test_realm_counts_match_readme() -> None:
    assert len(game.REALM_NAMES) == 279
    assert len(game.SUB_REALMS) == 279 * 9 + 1 == 2512

    readme = (Path(game.__file__).parent / "README.md").read_text(encoding="utf-8")
    assert "279" in readme
    assert "2512" in readme
