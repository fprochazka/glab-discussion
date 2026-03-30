from __future__ import annotations

import pytest

from glab_discussion.models import Discussion, Note, Position

SAMPLE_NOTE_DATA = {
    "id": 12345,
    "type": None,
    "body": "This is a comment",
    "author": {"id": 1, "username": "alice", "name": "Alice"},
    "created_at": "2025-01-15T10:30:00.000Z",
    "updated_at": "2025-01-15T10:30:00.000Z",
    "system": False,
    "resolvable": True,
    "resolved": False,
}

SAMPLE_DIFF_NOTE_DATA = {
    "id": 12346,
    "type": "DiffNote",
    "body": "Fix this line",
    "author": {"id": 2, "username": "bob", "name": "Bob"},
    "created_at": "2025-01-15T11:00:00.000Z",
    "updated_at": "2025-01-15T11:00:00.000Z",
    "system": False,
    "resolvable": True,
    "resolved": False,
    "position": {
        "base_sha": "abc123",
        "head_sha": "def456",
        "start_sha": "abc123",
        "old_path": "src/main.py",
        "new_path": "src/main.py",
        "position_type": "text",
        "old_line": None,
        "new_line": 42,
    },
}

SAMPLE_SYSTEM_NOTE_DATA = {
    "id": 12347,
    "type": None,
    "body": "assigned to @alice",
    "author": {"id": 1, "username": "alice", "name": "Alice"},
    "created_at": "2025-01-15T09:00:00.000Z",
    "updated_at": "2025-01-15T09:00:00.000Z",
    "system": True,
    "resolvable": False,
    "resolved": False,
}

SAMPLE_DISCUSSION_DATA = {
    "id": "abc123def456",
    "individual_note": False,
    "notes": [SAMPLE_NOTE_DATA],
}

SAMPLE_DIFF = """@@ -10,7 +10,8 @@ class Foo:
     def bar(self):
         x = 1
-        y = old()
+        y = new_method()
+        z = extra()
         return x
"""


@pytest.fixture
def sample_position() -> Position:
    return Position(
        base_sha="abc123",
        head_sha="def456",
        start_sha="abc123",
        old_path="src/main.py",
        new_path="src/main.py",
        position_type="text",
        old_line=None,
        new_line=42,
    )


@pytest.fixture
def sample_note() -> Note:
    return Note(
        id=12345,
        author_username="alice",
        author_id=1,
        is_bot=False,
        body="This is a comment",
        created_at="2025-01-15T10:30:00.000Z",
        updated_at="2025-01-15T10:30:00.000Z",
        system=False,
        resolvable=True,
        resolved=False,
        note_type=None,
        position=None,
    )


@pytest.fixture
def sample_diff_note(sample_position: Position) -> Note:
    return Note(
        id=12346,
        author_username="bob",
        author_id=2,
        is_bot=False,
        body="Fix this line",
        created_at="2025-01-15T11:00:00.000Z",
        updated_at="2025-01-15T11:00:00.000Z",
        system=False,
        resolvable=True,
        resolved=False,
        note_type="DiffNote",
        position=sample_position,
    )


@pytest.fixture
def sample_system_note() -> Note:
    return Note(
        id=12347,
        author_username="alice",
        author_id=1,
        is_bot=False,
        body="assigned to @alice",
        created_at="2025-01-15T09:00:00.000Z",
        updated_at="2025-01-15T09:00:00.000Z",
        system=True,
        resolvable=False,
        resolved=False,
        note_type=None,
        position=None,
    )


@pytest.fixture
def general_discussion(sample_note: Note) -> Discussion:
    return Discussion(
        id="abc123def456",
        individual_note=False,
        notes=[sample_note],
    )


@pytest.fixture
def diff_discussion(sample_diff_note: Note) -> Discussion:
    return Discussion(
        id="diff123def456",
        individual_note=False,
        notes=[sample_diff_note],
    )


@pytest.fixture
def system_discussion(sample_system_note: Note) -> Discussion:
    return Discussion(
        id="sys123def456",
        individual_note=True,
        notes=[sample_system_note],
    )
