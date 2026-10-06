from __future__ import annotations

from subprocess import CompletedProcess
from unittest.mock import patch

from glab_discussion.api import glab_api, glab_graphql, glab_mr_view_json


class TestGlabGraphql:
    def test_sends_query_and_variables_as_json_body(self) -> None:
        with patch("glab_discussion.api.glab_api", return_value={"data": {"currentUser": {"username": "me"}}}) as api:
            data = glab_graphql("query { currentUser { username } }", {"a": 1}, hostname="gitlab.example.com")

        api.assert_called_once_with(
            "graphql",
            json_body={"query": "query { currentUser { username } }", "variables": {"a": 1}},
            hostname="gitlab.example.com",
        )
        assert data == {"currentUser": {"username": "me"}}

    def test_missing_data_is_empty(self) -> None:
        with patch("glab_discussion.api.glab_api", return_value=None):
            assert glab_graphql("query { x }", {}) == {}


class TestSubprocessEncoding:
    """glab prints UTF-8 JSON; decoding it with the locale codec (cp1252 on Windows) blows up on emoji
    and on names like Janeček, and the reader thread then hands back stdout=None."""

    def test_glab_api_decodes_glab_output_as_utf8(self) -> None:
        completed = CompletedProcess(args=[], returncode=0, stdout='{"name": "Janeček 🔎"}', stderr="")
        with patch("glab_discussion.api.subprocess.run", return_value=completed) as run:
            assert glab_api("projects/1") == {"name": "Janeček 🔎"}

        assert run.call_args.kwargs["encoding"] == "utf-8"

    def test_glab_mr_view_json_decodes_glab_output_as_utf8(self) -> None:
        completed = CompletedProcess(args=[], returncode=0, stdout='{"iid": 7}', stderr="")
        with patch("glab_discussion.api.subprocess.run", return_value=completed) as run:
            assert glab_mr_view_json() == {"iid": 7}

        assert run.call_args.kwargs["encoding"] == "utf-8"
