from __future__ import annotations

from plugins.pintu.logic import CORRECT_ORDER, GameService


def test_parse_swap() -> None:
    assert GameService.parse_swap("9换1") == (9, 1)
    assert GameService.parse_swap("9 换 1") == (9, 1)
    assert GameService.parse_swap("交换 4 7") == (4, 7)
    assert GameService.parse_swap("交换4 7") is None
    assert GameService.parse_swap("abc") is None


def test_count_correct_tiles() -> None:
    assert GameService.count_correct_tiles(CORRECT_ORDER) == 9
    assert GameService.count_correct_tiles([2, 1, 3, 4, 5, 6, 7, 8, 9]) == 7


def test_get_session_reuses_group_session() -> None:
    service = GameService()
    first = service.get_session(1001)
    second = service.get_session(1001)
    other = service.get_session(1002)

    assert first is second
    assert first is not other
    assert first.group_id == 1001


def test_extract_target_user_id_from_text_and_at_segment() -> None:
    assert GameService.extract_target_user_id("拼图加管 12345", "拼图加管", []) == "12345"
    assert GameService.extract_target_user_id("拼图加管 abc", "拼图加管", []) is None
    assert GameService.extract_target_user_id(
        "拼图加管 [CQ:at,qq=67890]",
        "拼图加管",
        [{"type": "at", "data": {"qq": "67890"}}],
    ) == "67890"
