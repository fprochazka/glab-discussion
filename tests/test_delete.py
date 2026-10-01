from __future__ import annotations

from argparse import Namespace
from unittest.mock import patch

from glab_discussion.commands.delete import run
from glab_discussion.ids import NoteRef
from glab_discussion.models import MrContext


class TestDelete:
    def test_delete_note(self, capsys, mr_context: MrContext) -> None:
        with (
            patch("glab_discussion.commands.delete.resolve_mr_context", return_value=mr_context),
            patch("glab_discussion.commands.delete.glab_api") as mock_api,
        ):
            args = Namespace(note_ref=NoteRef("note", 99999))
            run(args)

            mock_api.assert_called_once_with(
                "projects/42/merge_requests/7/notes/99999",
                method="DELETE",
                hostname="gitlab.com",
            )

        captured = capsys.readouterr()
        assert "Deleted note:99999" in captured.out

    def test_delete_draft(self, capsys, mr_context: MrContext) -> None:
        with (
            patch("glab_discussion.commands.delete.resolve_mr_context", return_value=mr_context),
            patch("glab_discussion.commands.delete.glab_api") as mock_api,
        ):
            args = Namespace(note_ref=NoteRef("draft", 15))
            run(args)

            mock_api.assert_called_once_with(
                "projects/42/merge_requests/7/draft_notes/15",
                method="DELETE",
                hostname="gitlab.com",
            )

        assert "Deleted draft:15" in capsys.readouterr().out
