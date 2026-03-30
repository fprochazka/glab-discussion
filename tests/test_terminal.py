from __future__ import annotations

from unittest.mock import patch

from glab_discussion.terminal import is_interactive_terminal


class TestIsInteractiveTerminal:
    @patch.dict("os.environ", {"CLAUDECODE": "1"}, clear=False)
    def test_returns_false_when_claudecode_set(self) -> None:
        assert is_interactive_terminal() is False

    @patch.dict("os.environ", {"AIDER": "1"}, clear=False)
    def test_returns_false_when_aider_set(self) -> None:
        assert is_interactive_terminal() is False

    @patch.dict("os.environ", {"CURSOR": "1"}, clear=False)
    def test_returns_false_when_cursor_set(self) -> None:
        assert is_interactive_terminal() is False

    @patch.dict("os.environ", {"GITHUB_COPILOT": "1"}, clear=False)
    def test_returns_false_when_github_copilot_set(self) -> None:
        assert is_interactive_terminal() is False

    @patch.dict("os.environ", {}, clear=True)
    @patch("sys.stdin")
    @patch("sys.stdout")
    def test_returns_false_when_stdin_not_tty(self, mock_stdout, mock_stdin) -> None:
        mock_stdin.isatty.return_value = False
        mock_stdout.isatty.return_value = True
        assert is_interactive_terminal() is False

    @patch.dict("os.environ", {}, clear=True)
    @patch("sys.stdin")
    @patch("sys.stdout")
    def test_returns_false_when_stdout_not_tty(self, mock_stdout, mock_stdin) -> None:
        mock_stdin.isatty.return_value = True
        mock_stdout.isatty.return_value = False
        assert is_interactive_terminal() is False

    @patch.dict("os.environ", {}, clear=True)
    @patch("sys.stdin")
    @patch("sys.stdout")
    def test_returns_true_when_interactive(self, mock_stdout, mock_stdin) -> None:
        mock_stdin.isatty.return_value = True
        mock_stdout.isatty.return_value = True
        assert is_interactive_terminal() is True
