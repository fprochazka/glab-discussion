from __future__ import annotations

from argparse import Namespace
from unittest.mock import call, patch

import pytest

from glab_discussion.commands.write import build_position, run
from glab_discussion.models import MrContext

VERSIONS = [
    {"id": 3, "base_commit_sha": "base3", "head_commit_sha": "head3", "start_commit_sha": "start3"},
    {"id": 2, "base_commit_sha": "base2", "head_commit_sha": "head2", "start_commit_sha": "start2"},
]


def _args(**overrides) -> Namespace:
    values = {
        "body": "Comment text",
        "reply_to": None,
        "file": None,
        "new_line": None,
        "old_line": None,
        "commit": None,
        "draft": False,
        "no_draft": False,
        "resolve": False,
    }
    values.update(overrides)
    return Namespace(**values)


@pytest.fixture
def no_draft_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GLAB_DISCUSSION_WRITE_AS_DRAFT", raising=False)


@pytest.fixture
def mock_api(mr_context: MrContext):
    def respond(endpoint: str, **kwargs):
        if endpoint.endswith("/versions"):
            return VERSIONS
        if endpoint.endswith("/draft_notes"):
            return {"id": 501}
        if endpoint.endswith("/notes"):
            return {"id": 9001}
        return {"id": "d" * 40, "notes": [{"id": 9002}]}

    with (
        patch("glab_discussion.commands.write.resolve_mr_context", return_value=mr_context),
        patch("glab_discussion.commands.write.glab_api", side_effect=respond) as api,
    ):
        yield api


class TestBuildPosition:
    def test_new_line(self) -> None:
        assert build_position(VERSIONS[0], "src/a.py", 42, None) == {
            "position_type": "text",
            "base_sha": "base3",
            "head_sha": "head3",
            "start_sha": "start3",
            "old_path": "src/a.py",
            "new_path": "src/a.py",
            "new_line": 42,
        }

    def test_both_lines(self) -> None:
        position = build_position(VERSIONS[1], "src/a.py", 42, 40)
        assert position["new_line"] == 42
        assert position["old_line"] == 40
        assert position["head_sha"] == "head2"


@pytest.mark.usefixtures("no_draft_env")
class TestWriteNormal:
    def test_general(self, capsys, mock_api) -> None:
        run(_args())

        mock_api.assert_called_once_with(
            "projects/42/merge_requests/7/discussions",
            method="POST",
            raw_fields={"body": "Comment text"},
            hostname="gitlab.com",
        )
        assert f"Created discussion {'d' * 40} (note:9002)" in capsys.readouterr().out

    def test_reply(self, capsys, mock_api) -> None:
        run(_args(reply_to="abc"))

        mock_api.assert_called_once_with(
            "projects/42/merge_requests/7/discussions/abc/notes",
            method="POST",
            raw_fields={"body": "Comment text"},
            hostname="gitlab.com",
        )
        assert "Replied to discussion abc (note:9001)" in capsys.readouterr().out

    def test_diff_note(self, capsys, mock_api) -> None:
        run(_args(file="src/a.py", new_line=42))

        assert mock_api.call_args_list[-1] == call(
            "projects/42/merge_requests/7/discussions",
            method="POST",
            json_body={"body": "Comment text", "position": build_position(VERSIONS[0], "src/a.py", 42, None)},
            hostname="gitlab.com",
        )
        assert "note:9002" in capsys.readouterr().out

    def test_resolve_needs_draft(self, capsys, mock_api) -> None:
        with pytest.raises(SystemExit) as exc_info:
            run(_args(reply_to="abc", resolve=True))
        assert exc_info.value.code == 1
        assert "--resolve works only on a draft reply" in capsys.readouterr().err
        mock_api.assert_not_called()


@pytest.mark.usefixtures("no_draft_env")
class TestWriteDraft:
    def test_general(self, capsys, mock_api) -> None:
        run(_args(draft=True))

        mock_api.assert_called_once_with(
            "projects/42/merge_requests/7/draft_notes",
            method="POST",
            json_body={"note": "Comment text"},
            hostname="gitlab.com",
        )
        assert "Created draft:501 (new thread)" in capsys.readouterr().out

    def test_reply(self, capsys, mock_api) -> None:
        run(_args(draft=True, reply_to="abc"))

        mock_api.assert_called_once_with(
            "projects/42/merge_requests/7/draft_notes",
            method="POST",
            json_body={"note": "Comment text", "in_reply_to_discussion_id": "abc"},
            hostname="gitlab.com",
        )
        assert "Created draft:501 (reply to discussion abc)" in capsys.readouterr().out

    def test_reply_resolve(self, capsys, mock_api) -> None:
        run(_args(draft=True, reply_to="abc", resolve=True))

        mock_api.assert_called_once_with(
            "projects/42/merge_requests/7/draft_notes",
            method="POST",
            json_body={"note": "Comment text", "in_reply_to_discussion_id": "abc", "resolve_discussion": True},
            hostname="gitlab.com",
        )
        assert "resolves the thread" in capsys.readouterr().out

    def test_inline_on_commit(self, capsys, mock_api) -> None:
        run(_args(draft=True, file="src/a.py", old_line=10, commit="head2"))

        assert mock_api.call_args_list == [
            call("projects/42/merge_requests/7/versions", hostname="gitlab.com"),
            call(
                "projects/42/merge_requests/7/draft_notes",
                method="POST",
                json_body={"note": "Comment text", "position": build_position(VERSIONS[1], "src/a.py", None, 10)},
                hostname="gitlab.com",
            ),
        ]
        assert "Created draft:501 (diff note on src/a.py:10)" in capsys.readouterr().out

    def test_resolve_needs_reply(self, capsys, mock_api) -> None:
        with pytest.raises(SystemExit):
            run(_args(draft=True, resolve=True))
        assert "--resolve works only on a draft reply" in capsys.readouterr().err
        mock_api.assert_not_called()


class TestDraftEnvVar:
    @pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE", " Yes "])
    def test_true_values_write_a_draft(self, monkeypatch, mock_api, value: str) -> None:
        monkeypatch.setenv("GLAB_DISCUSSION_WRITE_AS_DRAFT", value)
        run(_args())
        assert mock_api.call_args.args[0] == "projects/42/merge_requests/7/draft_notes"

    def test_env_draft_says_why(self, capsys, monkeypatch, mock_api) -> None:
        monkeypatch.setenv("GLAB_DISCUSSION_WRITE_AS_DRAFT", "true")
        run(_args())
        assert capsys.readouterr().out.splitlines()[1] == (
            "Written as a draft because GLAB_DISCUSSION_WRITE_AS_DRAFT is set. Pass --no-draft to post it right away."
        )

    def test_explicit_draft_does_not_mention_env(self, capsys, monkeypatch, mock_api) -> None:
        monkeypatch.setenv("GLAB_DISCUSSION_WRITE_AS_DRAFT", "true")
        run(_args(draft=True))
        out = capsys.readouterr().out
        assert "Created draft:501" in out
        assert "GLAB_DISCUSSION_WRITE_AS_DRAFT" not in out

    @pytest.mark.parametrize("value", ["false", "0", "no", ""])
    def test_false_values_publish(self, monkeypatch, mock_api, value: str) -> None:
        monkeypatch.setenv("GLAB_DISCUSSION_WRITE_AS_DRAFT", value)
        run(_args())
        assert mock_api.call_args.args[0] == "projects/42/merge_requests/7/discussions"

    def test_unset_publishes(self, monkeypatch, mock_api) -> None:
        monkeypatch.delenv("GLAB_DISCUSSION_WRITE_AS_DRAFT", raising=False)
        run(_args())
        assert mock_api.call_args.args[0] == "projects/42/merge_requests/7/discussions"

    def test_no_draft_overrides_env(self, monkeypatch, mock_api) -> None:
        monkeypatch.setenv("GLAB_DISCUSSION_WRITE_AS_DRAFT", "true")
        run(_args(no_draft=True))
        assert mock_api.call_args.args[0] == "projects/42/merge_requests/7/discussions"

    def test_draft_flag_ignores_unknown_env(self, monkeypatch, mock_api) -> None:
        monkeypatch.setenv("GLAB_DISCUSSION_WRITE_AS_DRAFT", "maybe")
        run(_args(draft=True))
        assert mock_api.call_args.args[0] == "projects/42/merge_requests/7/draft_notes"

    def test_unknown_value_is_an_error(self, capsys, monkeypatch, mock_api) -> None:
        monkeypatch.setenv("GLAB_DISCUSSION_WRITE_AS_DRAFT", "maybe")
        with pytest.raises(SystemExit) as exc_info:
            run(_args())
        assert exc_info.value.code == 1
        assert "GLAB_DISCUSSION_WRITE_AS_DRAFT is set to 'maybe'" in capsys.readouterr().err
        mock_api.assert_not_called()
