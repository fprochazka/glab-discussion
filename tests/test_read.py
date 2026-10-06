from __future__ import annotations

import copy
import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from glab_discussion.commands.read import run
from glab_discussion.models import MrContext, UserInfo

from .conftest import SAMPLE_DIFF_NOTE_DATA, SAMPLE_NOTE_DATA

DISCUSSION_A = {"id": "a" * 40, "individual_note": False, "notes": [SAMPLE_NOTE_DATA]}
DISCUSSION_B = {"id": "b" * 40, "individual_note": False, "notes": [SAMPLE_DIFF_NOTE_DATA]}
EMPTY_POSITION = {
    "base_sha": None,
    "start_sha": None,
    "head_sha": None,
    "old_path": None,
    "new_path": None,
    "position_type": "text",
    "old_line": None,
    "new_line": None,
    "line_range": None,
}
USERS = {
    1: UserInfo(id=1, username="alice", name="Alice", is_bot=False),
    2: UserInfo(id=2, username="bob", name="Bob", is_bot=False),
    9: UserInfo(id=9, username="review-bot", name="Review Bot", is_bot=True),
}


def _draft(draft_id: int, note: str, *, discussion_id=None, resolve=False, position=None) -> dict:
    return {
        "id": draft_id,
        "author_id": 9,
        "merge_request_id": 1,
        "resolve_discussion": resolve,
        "discussion_id": discussion_id,
        "note": note,
        "commit_id": None,
        "line_code": None,
        "position": position or EMPTY_POSITION,
    }


class FakeGitLab:
    """Serves discussions and drafts the way glab_api would, from lists a test can change between runs."""

    def __init__(self) -> None:
        self.discussions: list[dict] = [copy.deepcopy(DISCUSSION_A), copy.deepcopy(DISCUSSION_B)]
        self.drafts: list[dict] = []

    def __call__(self, endpoint: str, **kwargs):
        if endpoint.endswith("/discussions"):
            return copy.deepcopy(self.discussions)
        if endpoint.endswith("/draft_notes"):
            return copy.deepcopy(self.drafts)
        raise AssertionError(f"unexpected endpoint {endpoint}")


@pytest.fixture
def gitlab(mr_context: MrContext, tmp_path: Path):
    fake = FakeGitLab()
    with (
        patch("glab_discussion.commands.read.resolve_mr_context", return_value=mr_context),
        patch("glab_discussion.commands.read.glab_api", side_effect=fake),
        patch("glab_discussion.users.get_user_info", side_effect=lambda uid, host: USERS[uid]),
        patch("glab_discussion.commands.read.tempfile.gettempdir", return_value=str(tmp_path)),
    ):
        yield fake


@pytest.fixture
def dump_dir(tmp_path: Path) -> Path:
    return tmp_path / "glab-discussion" / "gitlab.com" / "mr-7"


def _read(capsys, *, dump: bool = True, full: bool = False) -> str:
    capsys.readouterr()
    run(Namespace(dump=dump, no_dump=not dump, full=full))
    return capsys.readouterr().out


def _files(dump_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(dump_dir.iterdir()) if p.name != ".meta.json"}


@pytest.mark.usefixtures("gitlab")
class TestDumpChangeDetection:
    def test_first_run_writes_all_threads(self, capsys, dump_dir: Path) -> None:
        out = _read(capsys)
        assert "synced 2 discussion threads" in out
        assert len(_files(dump_dir)) == 2
        meta = json.loads((dump_dir / ".meta.json").read_text())
        assert set(meta) == {"a" * 40, "b" * 40}
        assert all(set(entry) == {"filename", "hash"} for entry in meta.values())

    def test_dump_files_are_utf8_whatever_the_locale_is(self, capsys, gitlab: FakeGitLab, dump_dir: Path) -> None:
        body = "Janeček says 🔎 rows × 20 → fine"
        gitlab.discussions[0]["notes"][0]["body"] = body

        _read(capsys)
        out = _read(capsys)

        assert "(2 discussions up to date)" in out
        texts = [p.read_bytes().decode("utf-8") for p in dump_dir.iterdir() if p.name != ".meta.json"]
        assert any(body in text for text in texts)
        json.loads((dump_dir / ".meta.json").read_bytes().decode("utf-8"))

    def test_second_run_rewrites_nothing(self, capsys, dump_dir: Path) -> None:
        _read(capsys)
        mtimes = {p.name: p.stat().st_mtime_ns for p in dump_dir.iterdir()}
        out = _read(capsys)
        assert "(2 discussions up to date)" in out
        for p in dump_dir.iterdir():
            if p.name != ".meta.json":
                assert p.stat().st_mtime_ns == mtimes[p.name]

    def test_changed_thread_is_rewritten(self, capsys, gitlab: FakeGitLab, dump_dir: Path) -> None:
        _read(capsys)
        gitlab.discussions[0]["notes"][0]["body"] = "Edited comment"
        out = _read(capsys)
        assert "updated:" in out
        assert "(1 discussions up to date)" in out
        assert any("Edited comment" in content for content in _files(dump_dir).values())

    def test_vanished_thread_file_is_deleted(self, capsys, gitlab: FakeGitLab, dump_dir: Path) -> None:
        _read(capsys)
        gitlab.discussions.pop(1)
        out = _read(capsys)
        assert "deleted:" in out
        assert len(_files(dump_dir)) == 1

    def test_old_format_meta_keeps_unchanged_files(self, capsys, gitlab: FakeGitLab, dump_dir: Path) -> None:
        _read(capsys)
        meta = json.loads((dump_dir / ".meta.json").read_text())
        old_meta = {
            key: {"max_timestamp": "2025-01-15T10:30:00.000Z", "filename": e["filename"]} for key, e in meta.items()
        }
        (dump_dir / ".meta.json").write_text(json.dumps(old_meta))
        mtimes = {p.name: p.stat().st_mtime_ns for p in dump_dir.iterdir()}

        out = _read(capsys)

        assert "(2 discussions up to date)" in out
        for name, content in _files(dump_dir).items():
            assert (dump_dir / name).stat().st_mtime_ns == mtimes[name], content
        new_meta = json.loads((dump_dir / ".meta.json").read_text())
        assert all("hash" in entry and "max_timestamp" not in entry for entry in new_meta.values())

    def test_old_format_meta_with_missing_file_rewrites_it(self, capsys, dump_dir: Path) -> None:
        _read(capsys)
        meta = json.loads((dump_dir / ".meta.json").read_text())
        old_meta = {key: {"max_timestamp": "x", "filename": e["filename"]} for key, e in meta.items()}
        (dump_dir / ".meta.json").write_text(json.dumps(old_meta))
        missing = meta["a" * 40]["filename"]
        (dump_dir / missing).unlink()

        out = _read(capsys)

        assert f"updated: {missing}" in out
        assert (dump_dir / missing).exists()


@pytest.mark.usefixtures("gitlab")
class TestDrafts:
    def test_reply_drafts_follow_published_notes_in_id_order(self, capsys, gitlab: FakeGitLab) -> None:
        gitlab.drafts = [
            _draft(12, "Second draft", discussion_id="a" * 40, resolve=True),
            _draft(11, "First draft", discussion_id="a" * 40),
        ]
        out = _read(capsys, dump=False)

        published = out.index("(note:12345)")
        first = out.index("@review-bot [BOT] [DRAFT] (draft:11):")
        second = out.index("@review-bot [BOT] [DRAFT, resolves thread] (draft:12):")
        assert published < first < second
        assert out.index("Discussion: " + "b" * 40) > second

    def test_new_thread_drafts_get_their_own_file(self, capsys, gitlab: FakeGitLab, dump_dir: Path) -> None:
        inline_position = dict(SAMPLE_DIFF_NOTE_DATA["position"], new_line=7)
        gitlab.drafts = [_draft(21, "General draft"), _draft(22, "Inline draft", position=inline_position)]

        _read(capsys)
        files = _files(dump_dir)

        assert files["draft-21.txt"].startswith("Discussion: (draft, not published)\nType: General\n---\n")
        assert "@review-bot [BOT] [DRAFT] (draft:21):\nGeneral draft" in files["draft-21.txt"]
        assert "File: src/main.py\nLine: new:7" in files["draft-22.txt"]
        assert "URL:" not in files["draft-22.txt"]
        meta = json.loads((dump_dir / ".meta.json").read_text())
        assert meta["draft-21"]["filename"] == "draft-21.txt"

    def test_reply_draft_to_unknown_discussion_is_its_own_thread(self, capsys, gitlab: FakeGitLab) -> None:
        gitlab.drafts = [_draft(31, "Orphan", discussion_id="c" * 40)]
        out = _read(capsys, dump=False)
        assert "Discussion: (draft, not published)\nType: General\nReply to: " + "c" * 40 in out

    def test_publish_replaces_draft_file_with_discussion(self, capsys, gitlab: FakeGitLab, dump_dir: Path) -> None:
        gitlab.drafts = [_draft(21, "General draft"), _draft(23, "Reply draft", discussion_id="a" * 40)]
        _read(capsys)
        assert "draft-21.txt" in _files(dump_dir)

        # Publishing turns draft 21 into a new discussion and draft 23 into a note in thread A.
        gitlab.drafts = []
        published_reply = dict(
            SAMPLE_NOTE_DATA, id=12399, author={"id": 9, "username": "review-bot"}, body="Reply draft"
        )
        gitlab.discussions[0]["notes"].append(published_reply)
        published_thread = dict(
            SAMPLE_NOTE_DATA, id=12400, author={"id": 9, "username": "review-bot"}, body="General draft"
        )
        gitlab.discussions.append({"id": "e" * 40, "individual_note": False, "notes": [published_thread]})

        out = _read(capsys)

        assert "deleted: draft-21.txt" in out
        assert "updated:" in out
        assert "new:" in out
        files = _files(dump_dir)
        assert "draft-21.txt" not in files
        assert not any("[DRAFT]" in content for content in files.values())
