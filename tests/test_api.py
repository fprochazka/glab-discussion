from __future__ import annotations

from unittest.mock import patch

from glab_discussion.api import glab_graphql


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
