from __future__ import annotations

from glab_discussion.models import Discussion, Note, parse_discussion, parse_note, parse_position

from .conftest import (
    SAMPLE_DIFF_NOTE_DATA,
    SAMPLE_DISCUSSION_DATA,
    SAMPLE_NOTE_DATA,
    SAMPLE_SYSTEM_NOTE_DATA,
)


class TestParsePosition:
    def test_parse_position_basic(self) -> None:
        data = {
            "base_sha": "abc123",
            "head_sha": "def456",
            "start_sha": "abc123",
            "old_path": "src/main.py",
            "new_path": "src/main.py",
            "position_type": "text",
            "old_line": None,
            "new_line": 42,
        }
        pos = parse_position(data)
        assert pos.base_sha == "abc123"
        assert pos.head_sha == "def456"
        assert pos.start_sha == "abc123"
        assert pos.old_path == "src/main.py"
        assert pos.new_path == "src/main.py"
        assert pos.position_type == "text"
        assert pos.old_line is None
        assert pos.new_line == 42

    def test_parse_position_defaults(self) -> None:
        data = {
            "base_sha": "aaa",
            "head_sha": "bbb",
            "start_sha": "aaa",
            "old_path": "a.py",
            "new_path": "b.py",
        }
        pos = parse_position(data)
        assert pos.position_type == "text"
        assert pos.old_line is None
        assert pos.new_line is None

    def test_parse_position_with_both_lines(self) -> None:
        data = {
            "base_sha": "aaa",
            "head_sha": "bbb",
            "start_sha": "aaa",
            "old_path": "x.py",
            "new_path": "x.py",
            "position_type": "text",
            "old_line": 10,
            "new_line": 15,
        }
        pos = parse_position(data)
        assert pos.old_line == 10
        assert pos.new_line == 15


class TestParseNote:
    def test_parse_regular_note(self) -> None:
        note = parse_note(SAMPLE_NOTE_DATA)
        assert note.id == 12345
        assert note.author_username == "alice"
        assert note.author_id == 1
        assert note.is_bot is False
        assert note.body == "This is a comment"
        assert note.system is False
        assert note.resolvable is True
        assert note.resolved is False
        assert note.note_type is None
        assert note.position is None

    def test_parse_diff_note(self) -> None:
        note = parse_note(SAMPLE_DIFF_NOTE_DATA)
        assert note.id == 12346
        assert note.author_username == "bob"
        assert note.note_type == "DiffNote"
        assert note.position is not None
        assert note.position.new_line == 42
        assert note.position.old_line is None
        assert note.position.new_path == "src/main.py"

    def test_parse_system_note(self) -> None:
        note = parse_note(SAMPLE_SYSTEM_NOTE_DATA)
        assert note.id == 12347
        assert note.system is True
        assert note.resolvable is False
        assert note.body == "assigned to @alice"

    def test_parse_note_with_is_bot(self) -> None:
        note = parse_note(SAMPLE_NOTE_DATA, is_bot=True)
        assert note.is_bot is True

    def test_parse_note_missing_author(self) -> None:
        data = {
            "id": 99999,
            "type": None,
            "body": "orphan note",
            "created_at": "2025-01-15T10:00:00.000Z",
            "updated_at": "2025-01-15T10:00:00.000Z",
            "system": False,
            "resolvable": False,
            "resolved": False,
        }
        note = parse_note(data)
        assert note.author_username == "unknown"
        assert note.author_id == 0


class TestParseDiscussion:
    def test_parse_discussion(self) -> None:
        disc = parse_discussion(SAMPLE_DISCUSSION_DATA)
        assert disc.id == "abc123def456"
        assert disc.individual_note is False
        assert len(disc.notes) == 1
        assert disc.notes[0].id == 12345

    def test_parse_discussion_with_multiple_notes(self) -> None:
        data = {
            "id": "multi123",
            "individual_note": False,
            "notes": [SAMPLE_NOTE_DATA, SAMPLE_DIFF_NOTE_DATA],
        }
        disc = parse_discussion(data)
        assert len(disc.notes) == 2
        assert disc.notes[0].id == 12345
        assert disc.notes[1].id == 12346


class TestDiscussionProperties:
    def test_is_diff_note_true(self, diff_discussion: Discussion) -> None:
        assert diff_discussion.is_diff_note is True

    def test_is_diff_note_false(self, general_discussion: Discussion) -> None:
        assert general_discussion.is_diff_note is False

    def test_is_system_true(self, system_discussion: Discussion) -> None:
        assert system_discussion.is_system is True

    def test_is_system_false(self, general_discussion: Discussion) -> None:
        assert general_discussion.is_system is False

    def test_resolved_when_unresolved(self, general_discussion: Discussion) -> None:
        assert general_discussion.resolved is False

    def test_resolved_when_resolved(self, sample_note: Note) -> None:
        note = Note(
            id=sample_note.id,
            author_username=sample_note.author_username,
            author_id=sample_note.author_id,
            is_bot=False,
            body=sample_note.body,
            created_at=sample_note.created_at,
            updated_at=sample_note.updated_at,
            system=False,
            resolvable=True,
            resolved=True,
            note_type=None,
        )
        disc = Discussion(id="resolved123", individual_note=False, notes=[note])
        assert disc.resolved is True

    def test_resolved_when_no_resolvable_notes(self, system_discussion: Discussion) -> None:
        # All notes are non-resolvable, so all() on empty iterable returns True
        assert system_discussion.resolved is True

    def test_first_note(self, general_discussion: Discussion) -> None:
        assert general_discussion.first_note.id == 12345

    def test_max_timestamp_single_note(self, general_discussion: Discussion) -> None:
        assert general_discussion.max_timestamp == "2025-01-15T10:30:00.000Z"

    def test_max_timestamp_multiple_notes(self, sample_note: Note, sample_diff_note: Note) -> None:
        disc = Discussion(
            id="multi123",
            individual_note=False,
            notes=[sample_note, sample_diff_note],
        )
        # diff note has later timestamp (11:00 vs 10:30)
        assert disc.max_timestamp == "2025-01-15T11:00:00.000Z"
