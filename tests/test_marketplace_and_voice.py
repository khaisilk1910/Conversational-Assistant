"""Dependency-free regression tests for metadata and Vietnamese parsing."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "conversational_assistant"


def _load_pure_helper(module_name: str):
    """Load one standalone helper without importing Home Assistant."""
    package = "custom_components.conversational_assistant"
    if package not in sys.modules:
        stub = types.ModuleType(package)
        stub.__path__ = [str(COMPONENT)]
        sys.modules[package] = stub
    spec = importlib.util.spec_from_file_location(
        f"{package}.{module_name}", COMPONENT / f"{module_name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_marketplace_metadata():
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == COMPONENT.name
    assert manifest["config_flow"] is True
    assert manifest["version"] == "2026.11.7.1"
    assert manifest["integration_type"] == "service"
    assert manifest["documentation"].startswith("https://")
    assert manifest["issue_tracker"].startswith("https://")
    assert len(manifest["categories"]) in range(1, 4)
    assert hacs["name"] == manifest["name"]
    assert (COMPONENT / "brand" / "icon.png").is_file()
    assert (COMPONENT / "diagnostics.py").is_file()


def test_all_flow_results_have_step_id():
    tree = ast.parse((COMPONENT / "config_flow.py").read_text(encoding="utf-8"))
    methods = {"async_show_form", "async_show_menu", "async_show_progress", "async_external_step"}
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in methods
    ]
    assert calls
    assert all(any(keyword.arg == "step_id" for keyword in call.keywords) for call in calls)


def test_vietnamese_stt_selection_and_target_names():
    helper = _load_pure_helper("targeting")
    names = ["Loa phòng khách", "Loa phòng ngủ", "Camera 1", "Camera 10", "Điện thoại"]
    assert helper.normalize_text("CHỌN SỐ NĂM") == "chon so nam"
    assert helper.parse_target_selection("chọn số lăm", names) == [4]
    assert helper.parse_target_selection("chọn thứ hai", names) == [1]
    assert helper.parse_target_selection("camera 10", names) == [3]
    assert helper.parse_target_selection("camera 1", names) == [2]
    assert helper.parse_target_selection("chọn 1 và 3", names) == [0, 2]
    assert helper.parse_target_selection("tất cả loa", names) == [0, 1]
    assert helper.parse_target_selection("số 9", names) == []


def test_chat_start_is_narrow_not_unrelated_text():
    helper = _load_pure_helper("chat_flow")
    assert helper.chat_start_request("Nói chuyện với tôi hôm nay") == "hôm nay"
    assert helper.chat_start_request("trò chuyện đi") == ""
    assert helper.chat_start_request("Tám giờ mở đèn") is None
    assert helper.chat_start_request("Bật đèn phòng khách") is None


def test_startup_defers_assist_and_store_operations():
    """Guard the performance-sensitive startup and reload design."""
    tree = ast.parse((COMPONENT / "manager.py").read_text(encoding="utf-8"))
    manager = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ConversationalAssistantManager")
    methods = {node.name: node for node in manager.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    setup = methods["async_setup"]
    direct_calls = [node.func.attr for node in ast.walk(setup) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert "_register_static_trigger" not in direct_calls
    assert "_sync_learned_command_triggers" not in direct_calls
    trigger_register = methods["_async_register_assist_triggers"]
    assert any(isinstance(node, ast.Await) for node in ast.walk(trigger_register))
    unload = methods["async_unload"]
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "cancel" for node in ast.walk(unload))
    store_restore = methods["_start_background_storage_restore"]
    background = [node for node in ast.walk(store_restore) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "async_create_background_task"]
    assert len(background) == 1
    assert any(kw.arg == "eager_start" and isinstance(kw.value, ast.Constant) and kw.value.value is False for kw in background[0].keywords)


def test_release_workflow_does_not_force_move_tags():
    workflow = (ROOT / ".github/workflows/update-manifest-version.yml").read_text(encoding="utf-8")
    assert "git push -f" not in workflow
    assert "RELEASE_TAG" in workflow
    assert "manifest.json" in workflow
    assert "hacs/action@main" in (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")


def _isolated_manager_method(name: str, globals_dict: dict):
    """Extract a manager method for state-machine tests without Home Assistant."""
    import textwrap

    source = (COMPONENT / "manager.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    manager = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ConversationalAssistantManager"
    )
    method = next(
        node for node in manager.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )
    src = textwrap.dedent(ast.get_source_segment(source, method))
    namespace = dict(globals_dict)
    exec(compile("from __future__ import annotations\n" + src, "<method-test>", "exec"), namespace)
    return namespace[name]


def test_storage_restore_state_machine_preserves_data_on_failure():
    from types import SimpleNamespace

    events = []
    core_running = object()
    logger = SimpleNamespace(
        info=lambda *a: events.append("logged"),
        warning=lambda *a: events.append("warning"),
        exception=lambda *a: events.append("exception"),
    )
    method = _isolated_manager_method(
        "_finish_storage_load_task",
        {
            "_LOGGER": logger,
            "CoreState": SimpleNamespace(running=core_running),
            "STORAGE_LOAD_TIMEOUT_SECONDS": 12,
        },
    )

    class Task:
        def __init__(self, payload=None, error=None, cancelled=False):
            self.payload = payload
            self.error = error
            self.is_cancelled = cancelled

        def cancelled(self):
            return self.is_cancelled

        def result(self):
            if self.error is not None:
                raise self.error
            return self.payload

    def state(task, apply_error=None):
        manager = SimpleNamespace(
            _storage_load_task=task,
            _storage_loaded=False,
            _storage_error=None,
            _storage_load_retries=0,
            _assist_triggers_ready=True,
            hass=SimpleNamespace(state=core_running),
            reminders={},
            learned_commands={},
            notes={},
            camera_snapshot_schedules={},
        )

        def apply(payload):
            events.append("applied")
            if apply_error:
                raise apply_error

        manager._apply_stored_data = apply
        manager._schedule_storage_retry = lambda: events.append("retry")
        manager._sync_learned_command_triggers = lambda: events.append("learned")
        manager._schedule_next = lambda: events.append("reminders")
        manager._schedule_next_camera_snapshot = lambda: events.append("camera")
        manager._schedule_all_device_actions = lambda: events.append("devices")
        manager._notify_update = lambda: events.append("notify")
        manager._save_later = lambda: events.append("save")
        return manager

    failed_task = Task(error=OSError("private storage filename"))
    manager = state(failed_task)
    method(manager, failed_task)
    assert not manager._storage_loaded
    assert manager._storage_error == "OSError"
    assert "retry" in events and "save" not in events

    events.clear()
    corrupted_task = Task(payload={"notes": "not a list"})
    manager = state(corrupted_task, apply_error=ValueError("invalid schema"))
    method(manager, corrupted_task)
    assert not manager._storage_loaded
    assert manager._storage_error == "ValueError"
    assert "retry" in events and "save" not in events

    events.clear()
    valid_task = Task(payload={"reminders": []})
    manager = state(valid_task)
    method(manager, valid_task)
    assert manager._storage_loaded
    assert manager._storage_error is None
    assert events.index("applied") < events.index("save")
    assert "retry" not in events
    assert "learned" in events

    events.clear()
    cancelled = Task(cancelled=True)
    manager = state(cancelled)
    method(manager, cancelled)
    assert events == []
    assert manager._storage_load_task is None


def test_deferred_assist_registration_logs_failure_and_readiness():
    import asyncio
    from time import monotonic
    from types import SimpleNamespace

    events = []
    logger = SimpleNamespace(
        info=lambda *a: events.append("registered"),
        exception=lambda *a: events.append("exception"),
    )
    method = _isolated_manager_method(
        "_async_register_assist_triggers",
        {
            "asyncio": asyncio,
            "monotonic": monotonic,
            "get_agent_manager": lambda hass: "fake-agent",
            "_LOGGER": logger,
        },
    )
    manager = SimpleNamespace(
        hass=object(),
        _assist_trigger_specs=[(["a"], None, "first"), (["b"], None, "second")],
        _assist_triggers_ready=False,
        _assist_groups_registered=0,
        _assist_groups_failed=0,
        _assist_setup_ms=None,
    )

    def register(_agent, _sentences, _handler, label):
        events.append(label)
        manager._assist_groups_registered += 1

    manager._register_static_trigger = register
    manager._sync_learned_command_triggers = lambda _agent: events.append("learned")
    asyncio.run(method(manager))
    assert manager._assist_triggers_ready
    assert manager._assist_groups_registered == 2
    assert manager._assist_setup_ms >= 0
    assert events == ["first", "second", "learned", "registered"]

    events.clear()
    manager._assist_triggers_ready = False
    manager._sync_learned_command_triggers = lambda _agent: (_ for _ in ()).throw(
        RuntimeError("fake failure")
    )
    asyncio.run(method(manager))
    assert not manager._assist_triggers_ready
    assert manager._assist_groups_failed == 1
    assert "exception" in events
