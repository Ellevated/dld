"""stderr CLI ложится на диск, а не только в память умирающего процесса.

Аудит отказов оркестратора 30.08.2026, причина 3: четыре прогона 25–26.08 умерли
с `Command failed with exit code 1 … Check stderr output for details`, из них два
после 95 и 38 ходов ($30.27 и $22.41 сожжено). Коллектор stderr (BUG-188) стоял
и был ПУСТ: SDK отменяет свой stderr-reader в `close()`, а run-лог собирается уже
после этого. Отсылка «check stderr output» вела ровно никуда — диагностировать
было нечем.

Проверяется:
1. файл создаётся с шапкой ещё до первой строки — пустой файл отличает
   «CLI ничего не сказал» от «мы забыли подписаться»;
2. строки попадают на диск немедленно, а не при закрытии;
3. путь и число строк уезжают в run-лог;
4. сообщение ProcessError называет файл;
5. недоступный путь не роняет прогон — диагностика не имеет права быть фатальной.

Фейковый SDK ставится тем же способом, что в test_claude_runner_refusal.py:
настоящий цикл прогоняется целиком, утверждения — на файлах, которые он оставил.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))


@pytest.fixture
def loop_module():
    """runner_loop с подменённым SDK — импорт биндит имена SDK на уровне модуля."""
    import importlib
    import types

    fake_sdk = types.ModuleType("claude_agent_sdk")

    class FakeOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeCLIConnectionError(Exception):
        pass

    class FakeProcessError(Exception):
        def __init__(self, message, exit_code=None, stderr=None):
            super().__init__(message)
            self.exit_code = exit_code
            self.stderr = stderr

    fake_sdk.ClaudeAgentOptions = FakeOptions
    fake_sdk.AssistantMessage = type("AssistantMessage", (), {})
    fake_sdk.ResultMessage = type("ResultMessage", (), {})
    fake_sdk.SystemMessage = type("SystemMessage", (), {})
    fake_sdk.TextBlock = type("TextBlock", (), {})
    fake_sdk.ToolUseBlock = type("ToolUseBlock", (), {})
    fake_sdk.TaskNotificationMessage = type("TaskNotificationMessage", (), {})
    fake_sdk.CLIConnectionError = FakeCLIConnectionError
    fake_sdk.ProcessError = FakeProcessError

    async def _unused_query(**_kwargs):
        return
        yield  # pragma: no cover — makes this an async generator

    fake_sdk.query = _unused_query

    fake_errors = types.ModuleType("claude_agent_sdk._errors")
    fake_errors.CLIConnectionError = FakeCLIConnectionError
    fake_errors.ProcessError = FakeProcessError

    saved = {
        name: sys.modules.get(name) for name in ("claude_agent_sdk", "claude_agent_sdk._errors")
    }
    sys.modules["claude_agent_sdk"] = fake_sdk
    sys.modules["claude_agent_sdk._errors"] = fake_errors
    sys.modules.pop("runner_loop", None)
    try:
        mod = importlib.import_module("runner_loop")
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev
    mod._fake_process_error = FakeProcessError
    yield mod
    sys.modules.pop("runner_loop", None)


def test_file_is_created_with_a_header_before_any_line(loop_module, tmp_path: Path) -> None:
    """Пустой файл — тоже показание. Раньше «ничего не пришло» и «не подписались»
    выглядели одинаково: никак."""
    path = tmp_path / "proj-20260831-120000.stderr.txt"

    lines, _collector = loop_module.make_stderr_collector(path)

    assert path.exists(), "файл обязан появиться до первой строки"
    assert path.read_text(encoding="utf-8").startswith("# claude-runner stderr")
    assert lines == []


def test_lines_reach_disk_immediately(loop_module, tmp_path: Path) -> None:
    """Строка на диске ДО конца прогона — иначе улика умирает вместе с процессом."""
    path = tmp_path / "proj.stderr.txt"
    lines, collector = loop_module.make_stderr_collector(path)

    collector("Error: something exploded")
    collector("  at frame 2")

    content = path.read_text(encoding="utf-8")
    assert "Error: something exploded" in content
    assert "at frame 2" in content
    assert lines == ["Error: something exploded", "  at frame 2"]


def test_memory_tail_stays_capped_while_file_keeps_everything(loop_module, tmp_path: Path) -> None:
    """Кап на 200 строк защищает память, но не имеет права резать файл."""
    path = tmp_path / "proj.stderr.txt"
    lines, collector = loop_module.make_stderr_collector(path)

    for i in range(250):
        collector(f"line {i}")

    assert len(lines) == 200, "в памяти — хвост, а не всё"
    body = path.read_text(encoding="utf-8")
    assert "line 249" in body, "на диске обязано быть всё"
    assert body.count("line ") == 250


def test_unwritable_path_does_not_break_the_run(loop_module, tmp_path: Path) -> None:
    """Диагностика не имеет права ронять прогон, ради которого она заведена."""
    blocker = tmp_path / "blocker"
    blocker.write_text("я файл, а не каталог", encoding="utf-8")
    path = blocker / "nested" / "proj.stderr.txt"

    lines, collector = loop_module.make_stderr_collector(path)
    collector("строка в никуда")

    assert lines == ["строка в никуда"]


def test_collector_without_a_path_still_works(loop_module) -> None:
    """Обратная совместимость: вызов без пути ведёт себя как раньше."""
    lines, collector = loop_module.make_stderr_collector()
    collector("x")
    assert lines == ["x"]


def test_process_error_message_names_the_stderr_file(loop_module, tmp_path: Path) -> None:
    """«Check stderr output for details» обязано отсылать к конкретному файлу."""
    path = tmp_path / "proj.stderr.txt"
    state = loop_module.runner_result.new_run_state()
    exc = loop_module._fake_process_error("Command failed with exit code 1", exit_code=1)

    loop_module.handle_sdk_exception(exc, state, [], "/autopilot X", "proj", None, path)

    assert state["exit_code"] == 3
    assert str(path) in state["result_text"]


def test_process_error_with_captured_lines_still_inlines_them(loop_module, tmp_path: Path) -> None:
    """Когда строки всё-таки пришли, они остаются в result_text — как и было."""
    state = loop_module.runner_result.new_run_state()
    exc = loop_module._fake_process_error("Command failed with exit code 1", exit_code=1)

    loop_module.handle_sdk_exception(
        exc, state, ["boom"], "/autopilot X", "proj", None, tmp_path / "p.stderr.txt"
    )

    assert "boom" in state["result_text"]


def test_run_log_carries_the_stderr_path_and_count() -> None:
    """Оператору нужно знать И где смотреть, И сколько строк там оказалось.

    Ноль при ненулевом exit_code — это конкретное показание («SDK не доставил
    ничего»), а не отсутствие данных.
    """
    import runner_result

    state = runner_result.new_run_state()
    log_data = runner_result.build_log_data(
        state,
        project_name="proj",
        skill="autopilot",
        task="/autopilot X",
        prompt="/autopilot X",
        cli_path=None,
        cli_version="",
        model="claude-opus-5",
        effort="high",
        salvage_info=None,
        stderr_log="/logs/proj-1.stderr.txt",
        stderr_line_count=0,
    )

    assert log_data["stderr_log"] == "/logs/proj-1.stderr.txt"
    assert log_data["stderr_lines"] == 0
