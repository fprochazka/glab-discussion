from __future__ import annotations

from glab_discussion.formatter import format_discussion, format_discussions
from glab_discussion.models import Discussion, Note, Position

MR_URL = "https://gitlab.com/group/project/-/merge_requests/42"


class TestFormatDiscussion:
    def test_general_discussion(self, general_discussion: Discussion) -> None:
        result = format_discussion(general_discussion, MR_URL)
        assert "Discussion: abc123def456" in result
        assert "Type: General" in result
        assert "Resolved: no" in result
        assert f"URL: {MR_URL}#note_12345" in result
        assert "@alice:" in result
        assert "This is a comment" in result
        assert "[2025-01-15 10:30:00]" in result

    def test_diff_note_discussion(self, diff_discussion: Discussion) -> None:
        result = format_discussion(diff_discussion, MR_URL)
        assert "Type: DiffNote" in result
        assert "File: src/main.py" in result
        assert "Line: new:42" in result
        assert "Commit: def456" in result
        assert "Resolved: no" in result
        assert "@bob:" in result
        assert "Fix this line" in result

    def test_system_discussion(self, system_discussion: Discussion) -> None:
        result = format_discussion(system_discussion, MR_URL)
        assert "Type: System" in result
        assert "assigned to @alice" in result

    def test_bot_author(self, general_discussion: Discussion) -> None:
        general_discussion.notes[0].is_bot = True
        result = format_discussion(general_discussion, MR_URL)
        assert "[BOT]" in result

    def test_resolved_discussion(self, general_discussion: Discussion) -> None:
        general_discussion.notes[0].resolved = True
        result = format_discussion(general_discussion, MR_URL)
        assert "Resolved: yes" in result

    def test_diff_note_with_old_line(self) -> None:
        pos = Position(
            base_sha="aaa",
            head_sha="bbb",
            start_sha="aaa",
            old_path="old.py",
            new_path="new.py",
            position_type="text",
            old_line=10,
            new_line=None,
        )
        note = Note(
            id=100,
            author_username="carol",
            author_id=3,
            is_bot=False,
            body="Old line comment",
            created_at="2025-01-15T12:00:00.000Z",
            updated_at="2025-01-15T12:00:00.000Z",
            system=False,
            resolvable=True,
            resolved=False,
            note_type="DiffNote",
            position=pos,
        )
        disc = Discussion(id="oldline123", individual_note=False, notes=[note])
        result = format_discussion(disc, MR_URL)
        assert "Line: old:10" in result
        assert "new:" not in result

    def test_diff_note_with_both_lines(self) -> None:
        pos = Position(
            base_sha="aaa",
            head_sha="bbb",
            start_sha="aaa",
            old_path="file.py",
            new_path="file.py",
            position_type="text",
            old_line=10,
            new_line=15,
        )
        note = Note(
            id=101,
            author_username="dave",
            author_id=4,
            is_bot=False,
            body="Both lines",
            created_at="2025-01-15T12:00:00.000Z",
            updated_at="2025-01-15T12:00:00.000Z",
            system=False,
            resolvable=True,
            resolved=False,
            note_type="DiffNote",
            position=pos,
        )
        disc = Discussion(id="bothlines123", individual_note=False, notes=[note])
        result = format_discussion(disc, MR_URL)
        assert "Line: new:15 / old:10" in result


class TestFormatDiscussions:
    def test_skips_system_discussions(
        self,
        general_discussion: Discussion,
        system_discussion: Discussion,
    ) -> None:
        result = format_discussions([general_discussion, system_discussion], MR_URL)
        assert "Type: General" in result
        assert "Type: System" not in result

    def test_multiple_discussions(
        self,
        general_discussion: Discussion,
        diff_discussion: Discussion,
    ) -> None:
        result = format_discussions([general_discussion, diff_discussion], MR_URL)
        assert "abc123def456" in result
        assert "diff123def456" in result

    def test_empty_discussions(self) -> None:
        result = format_discussions([], MR_URL)
        assert result == ""

    def test_only_system_discussions(self, system_discussion: Discussion) -> None:
        result = format_discussions([system_discussion], MR_URL)
        assert result == ""
