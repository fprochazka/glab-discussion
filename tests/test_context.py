from __future__ import annotations

from unittest.mock import patch

import pytest

from glab_discussion.context import _parse_mr_url


class TestParseMrUrl:
    @patch("glab_discussion.context.glab_api")
    def test_valid_url(self, mock_glab_api) -> None:
        mock_glab_api.return_value = {"id": 123}
        ctx = _parse_mr_url("https://gitlab.com/group/project/-/merge_requests/42")
        assert ctx.hostname == "gitlab.com"
        assert ctx.project_path == "group/project"
        assert ctx.mr_iid == 42
        assert ctx.project_id == 123
        assert ctx.mr_url == "https://gitlab.com/group/project/-/merge_requests/42"
        mock_glab_api.assert_called_once_with("projects/group%2Fproject", hostname="gitlab.com")

    @patch("glab_discussion.context.glab_api")
    def test_valid_url_nested_group(self, mock_glab_api) -> None:
        mock_glab_api.return_value = {"id": 456}
        ctx = _parse_mr_url("https://gitlab.example.com/org/team/repo/-/merge_requests/99")
        assert ctx.hostname == "gitlab.example.com"
        assert ctx.project_path == "org/team/repo"
        assert ctx.mr_iid == 99
        assert ctx.project_id == 456
        mock_glab_api.assert_called_once_with("projects/org%2Fteam%2Frepo", hostname="gitlab.example.com")

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid GitLab MR URL"):
            _parse_mr_url("https://github.com/user/repo/pull/1")

    def test_invalid_url_no_mr_number(self) -> None:
        with pytest.raises(ValueError, match="Invalid GitLab MR URL"):
            _parse_mr_url("https://gitlab.com/group/project/-/merge_requests/")

    @patch("glab_discussion.context.glab_api")
    def test_http_url(self, mock_glab_api) -> None:
        mock_glab_api.return_value = {"id": 789}
        ctx = _parse_mr_url("http://gitlab.local/team/app/-/merge_requests/5")
        assert ctx.hostname == "gitlab.local"
        assert ctx.project_path == "team/app"
        assert ctx.mr_iid == 5
