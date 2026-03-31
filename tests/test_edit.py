from __future__ import annotations

from argparse import Namespace
from unittest.mock import patch

from glab_discussion.commands.edit import run
from glab_discussion.models import MrContext


class TestEdit:
    def test_edit_note(self, capsys) -> None:
        ctx = MrContext(
            hostname="gitlab.com",
            project_id=42,
            project_path="group/project",
            mr_iid=7,
            mr_url="https://gitlab.com/group/project/-/merge_requests/7",
        )

        with (
            patch("glab_discussion.commands.edit.resolve_mr_context", return_value=ctx),
            patch("glab_discussion.commands.edit.glab_api") as mock_api,
        ):
            args = Namespace(note_id=99999, body="Updated text")
            run(args)

            mock_api.assert_called_once_with(
                "projects/42/merge_requests/7/notes/99999",
                method="PUT",
                raw_fields={"body": "Updated text"},
                hostname="gitlab.com",
            )

        captured = capsys.readouterr()
        assert "Edited note 99999" in captured.out

    def test_edit_note_stdin(self, capsys) -> None:
        ctx = MrContext(
            hostname="gitlab.com",
            project_id=42,
            project_path="group/project",
            mr_iid=7,
            mr_url="https://gitlab.com/group/project/-/merge_requests/7",
        )

        with (
            patch("glab_discussion.commands.edit.resolve_mr_context", return_value=ctx),
            patch("glab_discussion.commands.edit.glab_api") as mock_api,
            patch("glab_discussion.commands.edit.sys") as mock_sys,
        ):
            mock_sys.stdin.read.return_value = "Body from stdin"
            args = Namespace(note_id=88888, body="-")
            run(args)

            mock_api.assert_called_once_with(
                "projects/42/merge_requests/7/notes/88888",
                method="PUT",
                raw_fields={"body": "Body from stdin"},
                hostname="gitlab.com",
            )

        captured = capsys.readouterr()
        assert "Edited note 88888" in captured.out
