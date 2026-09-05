import asyncio
import json
import threading
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from plugins.group_summary.main import GroupSummaryPlugin
from plugins.rqhspeech import data_manager as speech
from plugins.rqhspeech import main as speech_main
from plugins.rqhwenda import main as wenda
from plugins.rqhwenda.answer_manager import AnswerManager
from sdk.pluginsystem import PluginBase, filter_registry
from sdk.pluginsystem.plugin_manager import HotReloadPluginManager


@pytest.mark.parametrize("day,key", [("2018-12-31", "2019-W01"), ("2021-01-01", "2020-W53")])
def test_iso_week_keys(monkeypatch, day, key):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(day)

    monkeypatch.setattr(speech, "datetime", Clock)
    assert speech.get_weekly_file().endswith(f"weekly_{key}.json")
    assert speech.check_and_handle_week_transition({})[1] == key


async def test_speech_awaits_update(monkeypatch):
    plugin = speech_main.RqhSpeechPlugin()
    update = AsyncMock(return_value=True)
    monkeypatch.setattr(speech_main, "user_exists", lambda uid: True)
    monkeypatch.setattr(speech_main.user_manager, "update_user_message", update)
    monkeypatch.setattr(plugin, "_load_and_log", lambda *args: None)
    monkeypatch.setattr(plugin, "_route_command", AsyncMock())
    event = SimpleNamespace(message=SimpleNamespace(plain_text="hello"), group_id=1, user_id=2, user_name="user")
    await plugin.rqhbase_group(event)
    update.assert_awaited_once_with("2", "1")
    await plugin.on_unload()


def test_log_rotation(monkeypatch, tmp_path):
    monkeypatch.setattr(speech.SpeechConfig, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(speech.SpeechConfig, "ENABLE_LOGGING", True)
    monkeypatch.setattr(speech.SpeechConfig, "get_log_filename", lambda: "first.log")
    manager = speech.LogManager()
    manager.log_message("1", "user", "2", 1, 1)
    monkeypatch.setattr(speech.SpeechConfig, "get_log_filename", lambda: "second.log")
    manager.log_message("1", "user", "2", 2, 2)
    assert (tmp_path / "first.log").exists()
    assert (tmp_path / "second.log").exists()


async def test_inherited_filters_and_override():
    calls = []

    class Parent(PluginBase):
        @filter_registry.group_server
        async def inherited(self, event):
            calls.append("parent")

        @filter_registry.group_server
        async def overridden(self, event):
            calls.append("wrong")

    class Child(Parent):
        async def overridden(self, event):
            calls.append("child")

        @property
        def unsafe(self):
            raise AssertionError("property evaluated")

    plugin = Child()
    await plugin._dispatch_filtered_message("group", SimpleNamespace())
    assert calls == ["parent"]
    await plugin.on_unload()


async def test_registered_load_cancelled_before_unload(tmp_path):
    manager = HotReloadPluginManager(tmp_path)
    started = asyncio.Event()
    order = []

    class Slow(PluginBase):
        async def on_load(self, *args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                order.append("cancelled")

        async def on_unload(self):
            order.append("unloaded")
            await super().on_unload()

    plugin = Slow()
    assert manager.register_plugin(plugin)
    await started.wait()
    await manager.unload_plugin("slow")
    assert order == ["cancelled", "unloaded"]
    assert not manager._load_tasks
    assert not manager.plugins


async def test_registered_load_failure_cleanup(tmp_path):
    manager = HotReloadPluginManager(tmp_path)

    class Broken(PluginBase):
        async def on_load(self, *args):
            raise ValueError("load failed")

    plugin = Broken()
    plugin.on_unload = AsyncMock(wraps=plugin.on_unload)
    manager.register_plugin(plugin)
    await manager._load_tasks["broken"]
    await asyncio.sleep(0)
    assert not manager.plugins
    assert not manager._load_tasks
    plugin.on_unload.assert_awaited_once()


async def test_watchdog_thread_uses_main_loop(tmp_path):
    manager = HotReloadPluginManager(tmp_path)
    manager._main_loop = asyncio.get_running_loop()
    manager._file_watcher_enabled = True
    manager._api = object()
    manager._event_bus = object()
    manager._debounce_delay = 0
    called = asyncio.Event()

    async def reload(name):
        assert asyncio.get_running_loop() is manager._main_loop
        called.set()
        return True

    manager.reload_plugin = reload
    thread = threading.Thread(target=manager._schedule_reload, args=("demo",))
    thread.start()
    thread.join()
    await asyncio.wait_for(called.wait(), 2)
    await asyncio.sleep(0)
    assert not manager._debounce_tasks
    manager._file_watcher_enabled = False
    manager._schedule_reload("demo")
    assert not manager._debounce_tasks


@pytest.mark.parametrize("results", [(False, True), (True, False), (True, True)])
def test_save_attempts_both_files(tmp_path, monkeypatch, results):
    manager = AnswerManager(str(tmp_path / "precise.json"), str(tmp_path / "fuzzy.json"))
    calls = []

    def save(path, data):
        calls.append(path)
        return results[len(calls) - 1]

    monkeypatch.setattr(manager, "_save_file", save)
    manager.dirty = True
    assert manager.save_if_dirty() == all(results)
    assert len(calls) == 2
    assert manager.dirty != all(results)


async def test_answer_lists_keep_both_categories(tmp_path, monkeypatch, mock_api):
    manager = AnswerManager(str(tmp_path / "precise.json"), str(tmp_path / "fuzzy.json"))
    manager.add_precise_answer("same", "precise answer")
    manager.add_fuzzy_answer("same", "fuzzy answer")
    monkeypatch.setattr(wenda, "answer_manager", manager)
    plugin = wenda.RqhWendaPlugin()
    plugin.api = mock_api
    for method in (plugin._list_all_answers, plugin._list_random_answers):
        await method(1, "user")
        text = mock_api.send_group_message.call_args.args[1]
        assert "precise answer" in text
        assert "fuzzy answer" in text
    await plugin.on_unload()


async def test_group_summary_write_survives_cancellation(tmp_path, monkeypatch):
    plugin = GroupSummaryPlugin()
    plugin.data_dir = tmp_path
    started = threading.Event()
    release = threading.Event()
    original = plugin._write_file

    def write(path, line):
        started.set()
        release.wait(3)
        original(path, line)

    monkeypatch.setattr(plugin, "_write_file", write)
    event = SimpleNamespace(group_id=1, user_id=2, user_name="user", message_id=3)
    task = asyncio.create_task(plugin._record_message(event, "hello"))
    while not started.is_set():
        await asyncio.sleep(0.001)
    task.cancel()
    await asyncio.sleep(0)
    assert plugin._write_lock.locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not plugin._write_lock.locked()
    rows = [json.loads(line) for path in tmp_path.glob("*.jsonl") for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["text"] == "hello"
    await plugin.on_unload()


async def test_speech_persists_concurrent_messages(monkeypatch, tmp_path):
    for name in ("USERS_DIR", "DAILY_DATA_DIR", "WEEKLY_DATA_DIR"):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setattr(speech.SpeechConfig, name, str(directory))
    for name in ("LEGACY_USERS_DIR", "LEGACY_DAILY_DATA_DIR", "LEGACY_WEEKLY_DATA_DIR"):
        monkeypatch.setattr(speech.SpeechConfig, name, str(tmp_path / "absent"))
    manager = speech.UserDataManager()
    for uid in ("1", "2"):
        assert speech.save_user_data(uid, manager.create_user(uid, uid))
    results = await asyncio.gather(*(manager.update_user_message(str(i % 2 + 1), "3") for i in range(10)))
    assert all(results)
    daily = speech.load_daily_data()
    weekly = speech.load_weekly_data()
    for uid in ("1", "2"):
        assert daily["users"][uid]["groups"]["3"] == 5
        assert weekly["users"][uid]["groups"]["3"]["total"] == 5
        assert speech.load_user_data(uid)["summary"]["total_messages"] == 5


def test_invalid_iso_week_rejected(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2021, 6, 1)

    monkeypatch.setattr(speech, "datetime", Clock)
    rows, info = speech.user_manager.get_historical_weekly_rankings("1", "W53")
    assert not rows
    assert "错误" in info
