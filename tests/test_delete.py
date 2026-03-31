from __future__ import annotations

from argparse import Namespace
from unittest.mock import patch

from glab_discussion.commands.delete import run
from glab_discussion.models import MrContext


class TestDelete:
    def test_delete_note(self, capsys) -> None:
        ctx = MrContext(
            hostname="gitlab.com",
            project_id=42,
            project_path="group/project",
            mr_iid=7,
            mr_url="https://gitlab.com/group/project/-/merge_requests/7",
        )

        with (
            patch("glab_discussion.commands.delete.resolve_mr_context", return_value=ctx),
            patch("glab_discussion.commands.delete.glab_api") as mock_api,
        ):
            args = Namespace(note_id=99999)
            run(args)

            mock_api.assert_called_once_with(
                "projects/42/merge_requests/7/notes/99999",
                method="DELETE",
                hostname="gitlab.com",
            )

        captured = capsys.readouterr()
        assert "Deleted note 99999" in captured.out
