from __future__ import annotations

import argparse

import pytest

from glab_discussion.ids import NoteRef, parse_note_ref


class TestParseNoteRef:
    def test_note(self) -> None:
        assert parse_note_ref("note:123") == NoteRef(kind="note", id=123)

    def test_draft(self) -> None:
        ref = parse_note_ref("draft:45")
        assert ref == NoteRef(kind="draft", id=45)
        assert ref.is_draft
        assert str(ref) == "draft:45"

    def test_bare_number_is_ambiguous(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError) as exc_info:
            parse_note_ref("123")
        assert str(exc_info.value) == (
            "Ambiguous ID '123': pass 'note:123' for a published note or 'draft:123' for your pending draft."
            " 'read' prints IDs in this form."
        )

    @pytest.mark.parametrize("value", ["", "note:", "draft:abc", "comment:1", "note:-1", "abc"])
    def test_unrecognized(self, value: str) -> None:
        with pytest.raises(argparse.ArgumentTypeError, match="Unrecognized ID"):
            parse_note_ref(value)
