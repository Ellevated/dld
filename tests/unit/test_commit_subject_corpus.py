"""Корпус субъектов коммитов — Python-сторона паритета с хуком.

Правило «subject обязан объявлять spec-id» живёт в ДВУХ реализациях:

* `scripts/vps/gate_logic.py:match_subject` — читает, гейт реализации;
* `.claude/hooks/commit-msg-spec-id.mjs` — пишет, хук commit-msg.

Разъехавшись, они начнут врать в разные стороны: хук пропустит субъект, который
гейт не прочитает, — и спека уйдёт в `blocked` при сделанной работе, ровно тот
отказ, ради которого хук и появился (аудит 30.08.2026, причина 1: 9 даунстримов
из 15). Поэтому таблица форм одна на обе стороны:
`test/fixtures/commit-subject-corpus.json`. JS-сторона гоняет её в
`test/scripts/commit-msg-spec-id.test.mjs`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "vps"))

from gate_logic import match_subject  # noqa: E402

CORPUS_PATH = REPO_ROOT / "test" / "fixtures" / "commit-subject-corpus.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
SPEC_ID = CORPUS["spec_id"]


@pytest.mark.parametrize("subject", CORPUS["accepted"])
def test_gate_accepts_every_form_the_hook_accepts(subject: str) -> None:
    """Хук пропускает такой субъект — гейт обязан его увидеть."""
    assert match_subject(subject, SPEC_ID) is True


@pytest.mark.parametrize("subject", CORPUS["rejected"])
def test_gate_rejects_every_form_the_hook_rejects(subject: str) -> None:
    """Хук отвергает такой субъект — гейт его и не должен читать."""
    assert match_subject(subject, SPEC_ID) is False


def test_corpus_covers_both_verdicts() -> None:
    """Пустая половина корпуса сделала бы паритет декоративным."""
    assert CORPUS["accepted"], "нет ни одной принимаемой формы"
    assert CORPUS["rejected"], "нет ни одной отвергаемой формы"
