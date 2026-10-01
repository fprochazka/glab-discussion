from __future__ import annotations

from argparse import Namespace
from unittest.mock import call, patch

from glab_discussion.commands.edit import run
from glab_discussion.ids import NoteRef
from glab_discussion.models import MrContext


class TestEdit:
    def test_edit_note(self, capsys, mr_context: MrContext) -> None:
        with (
            patch("glab_discussion.commands.edit.resolve_mr_context", return_value=mr_context),
            patch("glab_discussion.commands.edit.glab_api") as mock_api,
        ):
            args = Namespace(note_ref=NoteRef("note", 99999), body="Updated text")
            run(args)

            mock_api.assert_called_once_with(
                "projects/42/merge_requests/7/notes/99999",
                method="PUT",
                raw_fields={"body": "Updated text"},
                hostname="gitlab.com",
            )

        captured = capsys.readouterr()
        assert "Edited note:99999" in captured.out

    def test_edit_note_stdin(self, capsys, mr_context: MrContext) -> None:
        with (
            patch("glab_discussion.commands.edit.resolve_mr_context", return_value=mr_context),
            patch("glab_discussion.commands.edit.glab_api") as mock_api,
            patch("glab_discussion.commands.edit.sys") as mock_sys,
        ):
            mock_sys.stdin.read.return_value = "Body from stdin"
            args = Namespace(note_ref=NoteRef("note", 88888), body="-")
            run(args)

            mock_api.assert_called_once_with(
                "projects/42/merge_requests/7/notes/88888",
                method="PUT",
                raw_fields={"body": "Body from stdin"},
                hostname="gitlab.com",
            )

        captured = capsys.readouterr()
        assert "Edited note:88888" in captured.out

    def test_edit_general_draft_sends_only_note(self, capsys, mr_context: MrContext) -> None:
        draft = {"id": 15, "note": "Old", "position": {"base_sha": None, "old_path": None, "new_path": None}}
        with (
            patch("glab_discussion.commands.edit.resolve_mr_context", return_value=mr_context),
            patch("glab_discussion.commands.edit.glab_api", side_effect=[draft, None]) as mock_api,
        ):
            run(Namespace(note_ref=NoteRef("draft", 15), body="Reworded"))

            assert mock_api.call_args_list == [
                call("projects/42/merge_requests/7/draft_notes/15", hostname="gitlab.com"),
                call(
                    "projects/42/merge_requests/7/draft_notes/15",
                    method="PUT",
                    raw_fields={"note": "Reworded"},
                    hostname="gitlab.com",
                ),
            ]

        assert "Edited draft:15" in capsys.readouterr().out

    def test_edit_inline_draft_keeps_position(self, capsys, mr_context: MrContext) -> None:
        line_range = {
            "start": {"line_code": "abc_40_40", "type": None, "old_line": 40, "new_line": 40},
            "end": {"line_code": "abc_40_42", "type": "new", "old_line": None, "new_line": 42},
        }
        draft = {
            "id": 16,
            "note": "Old",
            "line_code": "abc_40_42",
            "position": {
                "base_sha": "base",
                "start_sha": "start",
                "head_sha": "head",
                "old_path": "src/a.py",
                "new_path": "src/a.py",
                "position_type": "text",
                "old_line": None,
                "new_line": 42,
                "line_range": line_range,
            },
        }
        with (
            patch("glab_discussion.commands.edit.resolve_mr_context", return_value=mr_context),
            patch("glab_discussion.commands.edit.glab_api", side_effect=[draft, None]) as mock_api,
        ):
            run(Namespace(note_ref=NoteRef("draft", 16), body="Reworded"))

            assert mock_api.call_args_list[1] == call(
                "projects/42/merge_requests/7/draft_notes/16",
                method="PUT",
                json_body={"note": "Reworded", "position": draft["position"]},
                hostname="gitlab.com",
            )

        assert "Edited draft:16" in capsys.readouterr().out

    def test_edit_inline_draft_without_line_range(self, mr_context: MrContext) -> None:
        position = {
            "base_sha": "base",
            "start_sha": "start",
            "head_sha": "head",
            "old_path": "src/a.py",
            "new_path": "src/a.py",
            "position_type": "text",
            "old_line": 10,
            "new_line": None,
            "line_range": None,
        }
        with (
            patch("glab_discussion.commands.edit.resolve_mr_context", return_value=mr_context),
            patch(
                "glab_discussion.commands.edit.glab_api", side_effect=[{"id": 17, "position": position}, None]
            ) as api,
        ):
            run(Namespace(note_ref=NoteRef("draft", 17), body="Reworded"))

        sent = api.call_args_list[1].kwargs["json_body"]["position"]
        assert "line_range" not in sent
        assert sent == {k: v for k, v in position.items() if k != "line_range"}
