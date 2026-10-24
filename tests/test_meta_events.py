"""meta_event 事件解析回归测试"""

from sdk.core.events import HeartbeatEvent, LifecycleEvent, MetaEvent


def test_heartbeat_event_parsed() -> None:
    event = MetaEvent.from_dict(
        {
            "time": 1730000000,
            "self_id": "123456",
            "post_type": "meta_event",
            "meta_event_type": "heartbeat",
            "interval": 5000,
            "status": {"online": True, "good": True},
        }
    )
    assert isinstance(event, HeartbeatEvent)
    assert event.self_id == 123456
    assert event.interval == 5000
    assert event.status["online"] is True


def test_lifecycle_event_parsed() -> None:
    event = MetaEvent.from_dict(
        {
            "post_type": "meta_event",
            "meta_event_type": "lifecycle",
            "sub_type": "connect",
        }
    )
    assert isinstance(event, LifecycleEvent)
    assert event.sub_type == "connect"


def test_unknown_meta_event_falls_back() -> None:
    event = MetaEvent.from_dict(
        {
            "post_type": "meta_event",
            "meta_event_type": "weird",
        }
    )
    assert type(event) is MetaEvent
    assert event.meta_event_type == "weird"
