from __future__ import annotations

from argparse import Namespace
from unittest.mock import patch

import pytest

from glab_discussion.commands.write import run
from glab_discussion.models import MrContext

CTX = MrContext(
    hostname="gitlab.com",
    project_id=42,
    project_path="group/project",
    mr_iid=7,
    mr_url="https://gitlab.com/group/project/-/merge_requests/7",
)


def args(**over) -> Namespace:
    base = {
        "body": "text",
        "reply_to": None,
        "file": None,
        "new_line": None,
        "old_line": None,
        "commit": None,
        "note": False,
    }
    return Namespace(**{**base, **over})


class TestWrite:
    def test_general_discussion(self, capsys) -> None:
        with (
            patch("glab_discussion.commands.write.resolve_mr_context", return_value=CTX),
            patch(
                "glab_discussion.commands.write.glab_api", return_value={"id": "d1", "notes": [{"id": 500}]}
            ) as mock_api,
        ):
            run(args(body="Starting a thread"))
            mock_api.assert_called_once_with(
                "projects/42/merge_requests/7/discussions",
                method="POST",
                raw_fields={"body": "Starting a thread"},
                hostname="gitlab.com",
            )
        assert "Created discussion d1" in capsys.readouterr().out

    def test_plain_note_posts_to_notes_not_discussions(self, capsys) -> None:
        with (
            patch("glab_discussion.commands.write.resolve_mr_context", return_value=CTX),
            patch("glab_discussion.commands.write.glab_api", return_value={"id": 777}) as mock_api,
        ):
            run(args(body="Review summary", note=True))
            mock_api.assert_called_once_with(
                "projects/42/merge_requests/7/notes",
                method="POST",
                raw_fields={"body": "Review summary"},
                hostname="gitlab.com",
            )
        out = capsys.readouterr().out
        assert "Created note 777" in out
        assert "#note_777" in out

    def test_plain_note_reads_stdin(self) -> None:
        with (
            patch("glab_discussion.commands.write.resolve_mr_context", return_value=CTX),
            patch("glab_discussion.commands.write.glab_api", return_value={"id": 1}) as mock_api,
            patch("glab_discussion.commands.write.sys") as mock_sys,
        ):
            mock_sys.stdin.read.return_value = "From stdin"
            run(args(body="-", note=True))
            assert mock_api.call_args.kwargs["raw_fields"] == {"body": "From stdin"}

    @pytest.mark.parametrize(
        ("over", "message"),
        [
            ({"note": True, "reply_to": "d1"}, "--reply-to and --note are mutually exclusive"),
            ({"note": True, "file": "a.py", "new_line": 1}, "--file and --note are mutually exclusive"),
            ({"reply_to": "d1", "file": "a.py", "new_line": 1}, "--reply-to and --file are mutually exclusive"),
        ],
    )
    def test_modes_are_mutually_exclusive(self, capsys, over, message) -> None:
        with (
            patch("glab_discussion.commands.write.resolve_mr_context", return_value=CTX),
            patch("glab_discussion.commands.write.glab_api") as mock_api,
            pytest.raises(SystemExit),
        ):
            run(args(**over))
        mock_api.assert_not_called()
        assert message in capsys.readouterr().err
