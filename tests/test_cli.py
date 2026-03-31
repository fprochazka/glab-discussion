from __future__ import annotations

import pytest

from glab_discussion.cli import main


class TestCli:
    def test_no_args_shows_error(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2  # argparse error exit code

    def test_read_help(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["read", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "--mr-url" in captured.out
        assert "--dump" in captured.out

    def test_write_help(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["write", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "--body" in captured.out
        assert "--reply-to" in captured.out

    def test_diff_help(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["diff", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "--file" in captured.out
        assert "--version" in captured.out

    def test_resolve_help(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["resolve", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "discussion_id" in captured.out
        assert "--unresolve" in captured.out

    def test_delete_help(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["delete", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "note_id" in captured.out

    def test_edit_help(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["edit", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "note_id" in captured.out
        assert "--body" in captured.out

    def test_delete_requires_note_id(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["delete"])
        assert exc_info.value.code == 2

    def test_edit_requires_body(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["edit", "123"])
        assert exc_info.value.code == 2

    def test_invalid_command(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["nonexistent"])
        assert exc_info.value.code == 2
