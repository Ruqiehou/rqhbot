from __future__ import annotations

from plugins.rqhmain.logic import (
    extract_city_from_forecast,
    extract_city_from_weather,
    match_keyword,
)


def test_match_keyword() -> None:
    assert match_keyword("北京天气", ["天气"])
    assert not match_keyword("北京", ["天气"])


def test_extract_city_from_weather() -> None:
    assert extract_city_from_weather("天气 北京") == "北京"
    assert extract_city_from_weather("上海气温") == "上海"
    assert extract_city_from_weather("天气") is None


def test_extract_city_from_forecast() -> None:
    assert extract_city_from_forecast("北京预报") == "北京"
    assert extract_city_from_forecast("上海降雨") == "上海"
    assert extract_city_from_forecast("预报") is None
