from __future__ import annotations

import threading
from argparse import Namespace
from unittest.mock import call, patch

import pytest

from glab_discussion.api import GlabApiError
from glab_discussion.commands.drafts import _mentions, run_delete, run_publish
from glab_discussion.models import MrContext

DRAFTS_ENDPOINT = "projects/42/merge_requests/7/draft_notes"


def _draft(draft_id: int, note: str = "Body", **extra) -> dict:
    data = {
        "id": draft_id,
        "author_id": 1,
        "resolve_discussion": False,
        "discussion_id": None,
        "note": note,
        "position": {"base_sha": None, "new_path": None, "old_path": None},
    }
    data.update(extra)
    return data


def _publish_args(**overrides) -> Namespace:
    values = {"body": None, "verdict": None}
    values.update(overrides)
    return Namespace(**values)


@pytest.fixture
def context(mr_context: MrContext):
    with (
        patch("glab_discussion.commands.drafts.resolve_mr_context", return_value=mr_context),
        patch("glab_discussion.commands.drafts.time.sleep") as sleep,
    ):
        yield sleep


NOT_REQUESTED = "User has not requested changes for this merge request"


def _activity(action: str, author: str = "me", body: str = "") -> dict:
    return {"action": action, "author": author, "body": body}


def _flow(calls: list[str]) -> list[str]:
    """Collapse the two state requests that run in parallel, in either order, into one label."""
    flow: list[str] = []
    i = 0
    while i < len(calls):
        if frozenset(calls[i : i + 2]) == {"GET draft_notes", "GRAPHQL state"}:
            flow.append("FETCH" if not flow else "READBACK")
            i += 2
        else:
            flow.append(calls[i])
            i += 1
    return flow


class FakePublishGitLab:
    """Answers the REST and GraphQL calls of `drafts publish`, and records them in order as short labels.

    The verdict model follows GitLab 18.10 EE: creating a draft sets the reviewer's state to REVIEW_STARTED,
    a request for changes stays until it is removed explicitly, the review state of a reviewer who approved
    does not change, and every verdict and review request leaves a system note.
    """

    def __init__(
        self,
        drafts: list[dict],
        *,
        reviewers: list[str] | None = None,
        state: str = "UNREVIEWED",
        approved: bool = False,
        requested: bool = False,
        activity: list[dict] | None = None,
    ) -> None:
        self.drafts = drafts
        self.reviewers = {
            r: (state if r == "me" else "UNREVIEWED") for r in (reviewers if reviewers is not None else ["me"])
        }
        self.approved = approved
        self.requested = requested
        self.activity = list(activity or [])
        self.other_requested = False
        self.allows_multiple_reviewers = True
        self.can_add_reviewer = True
        self.publishes = True
        self.applies_verdict = True
        self.destroy_mutation_exists = True
        self.destroy_errors: list[str] | None = None
        self.unapprove_fails = False
        self.barrier: threading.Barrier | None = None
        self.calls: list[str] = []
        self.with_activity: list[bool] = []
        self.created_notes: list[dict] = []
        self._lock = threading.Lock()

    @property
    def state(self) -> str | None:
        return self.reviewers.get("me")

    def _record(self, label: str) -> None:
        with self._lock:
            self.calls.append(label)

    def _set_state(self, state: str) -> None:
        if "me" in self.reviewers:
            self.reviewers["me"] = state

    def _wait_for_the_other_request(self) -> None:
        if self.barrier is not None:
            self.barrier.wait()

    def rest(self, endpoint: str, **kwargs):
        method = kwargs.get("method", "GET")
        path = endpoint.removeprefix("projects/42/merge_requests/7/")
        self._record(f"{method} {path}")
        if path == "draft_notes" and method == "GET":
            self._wait_for_the_other_request()
            return list(self.drafts)
        if path == "draft_notes" and method == "POST":
            self.created_notes.append(kwargs["json_body"])
            self.drafts.append(_draft(900, kwargs["json_body"]["note"]))
            self._set_state("REVIEW_STARTED")
            return {"id": 900}
        if path == "notes" and method == "POST":
            self.created_notes.append(kwargs["json_body"])
            self._submit_review(kwargs["json_body"]["body"].removeprefix("/submit_review "))
            return {"commands_changes": {}, "summary": ["Submitted the current review."]}
        if path == "unapprove":
            if self.unapprove_fails:
                raise GlabApiError("glab api failed: 404 Not found", stderr="glab: 404 Not found (HTTP 404)\n")
            self.approved = False
            self._set_state("UNAPPROVED")
            self.activity.append(_activity("unapproved"))
            return {}
        raise AssertionError(f"unexpected call {method} {endpoint}")

    def _submit_review(self, state: str) -> None:
        if self.publishes:
            self.drafts = []
        if not self.applies_verdict:
            return
        if state == "approve":
            self.approved = True
            self._set_state("APPROVED")
            self.activity.append(_activity("approved"))
        elif self.approved and state != "requested_changes":
            return  # "Reviewer has approved"
        elif state == "requested_changes":
            self.requested = True
            self.approved = False
            self._set_state("REQUESTED_CHANGES")
            self.activity.append(_activity("requested_changes"))
        else:
            self._set_state("REVIEWED")
            self.activity.append(_activity("reviewed"))

    def _activity_page(self, end: int, size: int) -> dict:
        start = max(0, end - size)
        nodes = [
            {
                "body": a["body"],
                "createdAt": f"2026-01-01T00:00:{i:02d}Z",
                "author": {"username": a["author"]},
                "systemNoteMetadata": {"action": a["action"]},
            }
            for i, a in enumerate(self.activity[start:end], start)
        ]
        return {"pageInfo": {"hasPreviousPage": start > 0, "startCursor": str(start)}, "nodes": nodes}

    def graphql(self, query: str, variables: dict, *, hostname: str | None = None) -> dict:
        assert hostname == "gitlab.com"
        assert variables["projectPath"] == "group/project"
        assert variables["iid"] == "7"
        if "mergeRequestSetReviewers" in query:
            self._record("GRAPHQL set-reviewers")
            assert variables["usernames"] == ["me"]
            assert "operationMode: APPEND" in query
            if self.can_add_reviewer:
                self.reviewers["me"] = "UNREVIEWED"
                self.activity.append(_activity("reviewer", body="requested review from @me"))
            nodes = [{"username": r} for r in self.reviewers]
            errors = [] if self.can_add_reviewer else ["Reviewers not able to be set"]
            return {"mergeRequestSetReviewers": {"errors": errors, "mergeRequest": {"reviewers": {"nodes": nodes}}}}
        if "mergeRequestDestroyRequestedChanges" in query:
            self._record("GRAPHQL destroy-requested-changes")
            if not self.destroy_mutation_exists:
                raise GlabApiError(
                    "glab api failed: Field 'mergeRequestDestroyRequestedChanges' doesn't exist on type 'Mutation'"
                )
            if self.destroy_errors is not None:
                return {"mergeRequestDestroyRequestedChanges": {"errors": self.destroy_errors}}
            if not self.requested:
                return {"mergeRequestDestroyRequestedChanges": {"errors": [NOT_REQUESTED]}}
            self.requested = False
            self._set_state("UNREVIEWED")
            return {"mergeRequestDestroyRequestedChanges": {"errors": []}}
        if "$before" in query:
            self._record("GRAPHQL activity-page")
            page = self._activity_page(int(variables["before"]), variables["activityPageSize"])
            return {"project": {"mergeRequest": {"notes": page}}}

        self._record("GRAPHQL state")
        self.with_activity.append(variables["withActivity"])
        self._wait_for_the_other_request()
        failed = self.requested or self.other_requested
        merge_request = {
            "allowsMultipleReviewers": self.allows_multiple_reviewers,
            "reviewers": {
                "nodes": [
                    {"username": r, "mergeRequestInteraction": {"reviewState": s}} for r, s in self.reviewers.items()
                ]
            },
            "approvedBy": {"nodes": [{"username": "me"}] if self.approved else []},
            "mergeabilityChecks": [{"identifier": "REQUESTED_CHANGES", "status": "FAILED" if failed else "SUCCESS"}],
        }
        if variables["withActivity"]:
            merge_request["notes"] = self._activity_page(len(self.activity), variables["activityPageSize"])
        return {"currentUser": {"username": "me"}, "project": {"mergeRequest": merge_request}}


@pytest.fixture
def publish_gitlab(mr_context: MrContext):
    holder: dict[str, FakePublishGitLab] = {}

    def install(fake: FakePublishGitLab) -> FakePublishGitLab:
        holder["fake"] = fake
        return fake

    with (
        patch("glab_discussion.commands.drafts.resolve_mr_context", return_value=mr_context),
        patch("glab_discussion.commands.drafts.glab_api", side_effect=lambda *a, **k: holder["fake"].rest(*a, **k)),
        patch(
            "glab_discussion.commands.drafts.glab_graphql", side_effect=lambda *a, **k: holder["fake"].graphql(*a, **k)
        ),
    ):
        yield install


class TestPublishFetch:
    def test_nothing_to_publish(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([]))
        with pytest.raises(SystemExit) as exc_info:
            run_publish(_publish_args())

        assert exc_info.value.code == 1
        assert _flow(fake.calls) == ["FETCH"]
        assert "nothing to publish" in capsys.readouterr().err

    def test_drafts_and_state_are_fetched_concurrently(self, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)]))
        # Each of the two requests waits until the other one has started; run one after the other, they time out.
        fake.barrier = threading.Barrier(2, timeout=5)
        run_publish(_publish_args(verdict="approve"))

        assert _flow(fake.calls) == ["FETCH", "GRAPHQL destroy-requested-changes", "POST notes", "READBACK"]

    def test_body_from_stdin(self, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([]))
        with patch("glab_discussion.commands.drafts.sys.stdin") as stdin:
            stdin.read.return_value = "From stdin"
            run_publish(_publish_args(body="-"))

        assert fake.created_notes[0] == {"note": "From stdin"}


class TestPublishDefaultVerdict:
    @pytest.mark.parametrize(
        ("reviewers", "state", "activity"),
        [
            pytest.param([], "UNREVIEWED", [], id="not-a-reviewer"),
            pytest.param(
                ["me"], "UNREVIEWED", [_activity("reviewer", "alice", "requested review from @me")], id="unreviewed"
            ),
            pytest.param(["me"], "REVIEW_STARTED", [], id="review-started"),
        ],
    )
    def test_defaults_to_reviewed(self, capsys, publish_gitlab, reviewers, state, activity) -> None:
        fake = publish_gitlab(
            FakePublishGitLab([_draft(1), _draft(2)], reviewers=reviewers, state=state, activity=activity)
        )
        run_publish(_publish_args())

        assert fake.created_notes == [{"body": "/submit_review reviewed"}]
        assert fake.state == "REVIEWED"
        assert fake.with_activity == [True, False]
        out = capsys.readouterr().out
        assert "so the verdict defaults to reviewed" in out
        assert "Published 2 drafts" in out
        assert "Set your reviewer state to reviewed." in out

    def test_body_becomes_a_draft(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)]))
        run_publish(_publish_args(body="Looks good overall"))

        assert fake.created_notes == [{"note": "Looks good overall"}, {"body": "/submit_review reviewed"}]
        assert "Published 2 drafts" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "activity",
        [
            pytest.param(
                [_activity("requested_changes"), _activity("reviewer", "alice", "requested review from @me")],
                id="re-requested-after-verdict",
            ),
            pytest.param(
                [
                    _activity("reviewed"),
                    _activity("reviewer", "alice", "removed review request for @me"),
                    _activity("reviewer", "alice", "requested review from @bob and @me"),
                ],
                id="removed-and-re-added",
            ),
            pytest.param(
                [_activity("reviewed"), _activity("reviewer", "alice", "removed review request for @me")],
                id="removed",
            ),
            pytest.param([_activity("approved"), _activity("unapproved")], id="approved-then-unapproved"),
            pytest.param(
                [_activity("requested_changes", "alice"), _activity("approved", "bob"), _activity("reviewed", "carol")],
                id="other-users-verdicts",
            ),
        ],
    )
    def test_no_verdict_of_the_user(self, capsys, publish_gitlab, activity) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], state="REVIEW_STARTED", activity=activity))
        run_publish(_publish_args())

        assert fake.created_notes == [{"body": "/submit_review reviewed"}]
        assert "so the verdict defaults to reviewed" in capsys.readouterr().out

    @pytest.mark.parametrize(
        ("activity", "approved", "named"),
        [
            pytest.param([_activity("reviewed")], False, "reviewed", id="reviewed"),
            pytest.param([_activity("requested_changes")], False, "requested-changes", id="requested-changes"),
            pytest.param([_activity("approved")], True, "approve", id="approved"),
            pytest.param([], True, "approve", id="approved-by-only"),
            pytest.param(
                [_activity("approved"), _activity("approved", "bob"), _activity("unapproved", "bob")],
                True,
                "approve",
                id="another-user-unapproved",
            ),
            pytest.param(
                [_activity("reviewer", "alice", "requested review from @me"), _activity("requested_changes")],
                False,
                "requested-changes",
                id="verdict-after-request",
            ),
            pytest.param(
                [_activity("requested_changes"), _activity("reviewer", "alice", "requested review from @me2")],
                False,
                "requested-changes",
                id="request-for-similar-username",
            ),
        ],
    )
    def test_previous_verdict_stops(self, capsys, publish_gitlab, activity, approved: bool, named: str) -> None:
        fake = publish_gitlab(
            FakePublishGitLab([_draft(1)], state="REVIEW_STARTED", approved=approved, activity=activity)
        )

        with pytest.raises(SystemExit) as exc_info:
            run_publish(_publish_args(body="Summary"))

        assert exc_info.value.code == 1
        assert _flow(fake.calls) == ["FETCH"]
        assert fake.created_notes == []
        err = capsys.readouterr().err
        assert f"You already gave this MR the verdict '{named}'" in err
        assert "Pass --verdict reviewed, --verdict requested-changes or --verdict approve" in err
        assert "Nothing was published." in err

    def test_request_for_changes_survives_a_new_draft(self, capsys, publish_gitlab) -> None:
        # Live round 4: after requesting changes, creating a draft sets the review state to REVIEW_STARTED.
        fake = publish_gitlab(
            FakePublishGitLab(
                [_draft(1)], state="REQUESTED_CHANGES", requested=True, activity=[_activity("requested_changes")]
            )
        )
        fake.rest("projects/42/merge_requests/7/draft_notes", method="POST", json_body={"note": "One more"})
        assert fake.state == "REVIEW_STARTED"
        fake.calls.clear()
        fake.created_notes.clear()

        with pytest.raises(SystemExit) as exc_info:
            run_publish(_publish_args())

        assert exc_info.value.code == 1
        assert fake.requested is True
        assert fake.created_notes == []
        assert "the verdict 'requested-changes'" in capsys.readouterr().err

    def test_pages_back_when_undecided(self, capsys, publish_gitlab) -> None:
        unrelated = [_activity("label", "alice", "added ~bug label") for _ in range(120)]
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], activity=[_activity("requested_changes"), *unrelated]))

        with pytest.raises(SystemExit):
            run_publish(_publish_args())

        assert _flow(fake.calls) == ["FETCH", "GRAPHQL activity-page", "GRAPHQL activity-page"]
        assert "the verdict 'requested-changes'" in capsys.readouterr().err

    def test_no_paging_when_decided_on_the_first_page(self, publish_gitlab) -> None:
        unrelated = [_activity("label", "alice", "added ~bug label") for _ in range(120)]
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], activity=[*unrelated, _activity("unapproved")]))
        run_publish(_publish_args())

        assert "GRAPHQL activity-page" not in fake.calls


class TestPublishVerdict:
    def test_reviewed(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)]))
        run_publish(_publish_args(verdict="reviewed"))

        assert _flow(fake.calls) == ["FETCH", "GRAPHQL destroy-requested-changes", "POST notes", "READBACK"]
        assert fake.created_notes == [{"body": "/submit_review reviewed"}]
        out = capsys.readouterr().out
        assert "GitLab: Submitted the current review." in out
        assert "Published 1 draft - " in out
        assert "Set your reviewer state to reviewed." in out
        assert "Removed your earlier request" not in out

    def test_explicit_verdict_skips_activity(self, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], activity=[_activity("requested_changes")]))
        fake.requested = True
        run_publish(_publish_args(verdict="reviewed"))

        assert fake.with_activity == [False, False]
        assert "GRAPHQL activity-page" not in fake.calls
        assert fake.state == "REVIEWED"

    def test_requested_changes(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)]))
        run_publish(_publish_args(verdict="requested-changes"))

        assert _flow(fake.calls) == ["FETCH", "POST notes", "READBACK"]
        assert fake.created_notes == [{"body": "/submit_review requested_changes"}]
        assert "Set your reviewer state to requested-changes." in capsys.readouterr().out

    def test_approve(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)]))
        run_publish(_publish_args(verdict="approve"))

        assert _flow(fake.calls) == ["FETCH", "GRAPHQL destroy-requested-changes", "POST notes", "READBACK"]
        assert fake.created_notes == [{"body": "/submit_review approve"}]
        assert "Approved the MR." in capsys.readouterr().out

    def test_approved_to_reviewed_revokes_approval(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], state="APPROVED", approved=True))
        run_publish(_publish_args(verdict="reviewed"))

        assert fake.calls.index("POST unapprove") < fake.calls.index("POST notes")
        assert fake.state == "REVIEWED"
        out = capsys.readouterr().out
        assert "Revoked your approval" in out
        assert "Set your reviewer state to reviewed." in out

    def test_approved_to_requested_changes_revokes_approval(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], state="APPROVED", approved=True))
        run_publish(_publish_args(verdict="requested-changes"))

        assert "POST unapprove" in fake.calls
        assert "GRAPHQL destroy-requested-changes" not in fake.calls
        assert fake.state == "REQUESTED_CHANGES"
        assert "Set your reviewer state to requested-changes." in capsys.readouterr().out

    def test_requested_to_reviewed_removes_request(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], state="REQUESTED_CHANGES", requested=True))
        run_publish(_publish_args(verdict="reviewed", body="Fixed now"))

        destroy = fake.calls.index("GRAPHQL destroy-requested-changes")
        assert destroy < fake.calls.index("POST draft_notes") < fake.calls.index("POST notes")
        assert fake.requested is False
        assert fake.state == "REVIEWED"
        out = capsys.readouterr().out
        assert "Removed your earlier request for changes" in out
        assert "Published 2 drafts" in out
        assert "blocked by requested changes" not in out

    def test_reviewed_with_leftover_request_removes_it(self, capsys, publish_gitlab) -> None:
        # The state GitLab before 19.2 leaves behind after requested-changes followed by reviewed.
        fake = publish_gitlab(FakePublishGitLab([], state="REVIEWED", requested=True))
        run_publish(_publish_args(verdict="reviewed"))

        assert fake.requested is False
        out = capsys.readouterr().out
        assert "Removed your earlier request for changes" in out
        assert "No drafts to publish." in out
        assert "Published" not in out

    def test_requested_to_approve_removes_request(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], state="REQUESTED_CHANGES", requested=True))
        run_publish(_publish_args(verdict="approve"))

        assert fake.calls.index("GRAPHQL destroy-requested-changes") < fake.calls.index("POST notes")
        assert fake.requested is False
        assert fake.approved is True
        assert "Approved the MR." in capsys.readouterr().out

    @pytest.mark.parametrize(
        ("verdict", "state", "approved", "requested"),
        [
            ("reviewed", "REVIEWED", False, False),
            ("requested-changes", "REQUESTED_CHANGES", False, True),
            ("approve", "APPROVED", True, False),
        ],
    )
    def test_same_verdict_again_removes_nothing(
        self, capsys, publish_gitlab, verdict: str, state: str, approved: bool, requested: bool
    ) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], state=state, approved=approved, requested=requested))
        run_publish(_publish_args(verdict=verdict))

        assert "POST unapprove" not in fake.calls
        assert fake.state == state
        assert fake.approved is approved
        assert fake.requested is requested
        out = capsys.readouterr().out
        assert "Revoked" not in out
        assert "Removed" not in out

    def test_adds_reviewer_first(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], reviewers=["someone"]))
        run_publish(_publish_args(verdict="reviewed"))

        assert _flow(fake.calls)[:2] == ["FETCH", "GRAPHQL set-reviewers"]
        assert "Added you (@me) as a reviewer" in capsys.readouterr().out

    def test_with_body_and_no_drafts(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([], reviewers=[]))
        run_publish(_publish_args(verdict="requested-changes", body="Summary"))

        assert _flow(fake.calls) == ["FETCH", "GRAPHQL set-reviewers", "POST draft_notes", "POST notes", "READBACK"]
        assert fake.created_notes == [{"note": "Summary"}, {"body": "/submit_review requested_changes"}]
        assert "Published 1 draft - " in capsys.readouterr().out


class TestPublishFailures:
    def test_not_added_as_reviewer_stops_before_publishing(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], reviewers=["alice"]))
        fake.can_add_reviewer = False
        fake.allows_multiple_reviewers = False

        with pytest.raises(SystemExit) as exc_info:
            run_publish(_publish_args(verdict="reviewed", body="Summary"))

        assert exc_info.value.code == 1
        assert _flow(fake.calls) == ["FETCH", "GRAPHQL set-reviewers"]
        assert fake.created_notes == []
        err = capsys.readouterr().err
        assert "GitLab did not add you (@me) as a reviewer" in err
        assert "Nothing was published." in err
        assert "allows only one reviewer, and @alice is the reviewer already" in err

    def test_not_added_without_single_reviewer_limit(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], reviewers=["alice"]))
        fake.can_add_reviewer = False

        with pytest.raises(SystemExit):
            run_publish(_publish_args(verdict="reviewed"))

        err = capsys.readouterr().err
        assert "only one reviewer" not in err
        assert "GitLab reports: Reviewers not able to be set" in err

    def test_unapprove_failure_stops_before_publishing(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], state="APPROVED", approved=True))
        fake.unapprove_fails = True

        with pytest.raises(SystemExit) as exc_info:
            run_publish(_publish_args(verdict="reviewed", body="Summary"))

        assert exc_info.value.code == 1
        assert fake.created_notes == []
        err = capsys.readouterr().err
        assert "You approved this MR, and GitLab did not revoke the approval" in err
        assert "Nothing was published." in err

    def test_destroy_errors_stop_before_publishing(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], state="REQUESTED_CHANGES", requested=True))
        fake.destroy_errors = ["Invalid permissions"]

        with pytest.raises(SystemExit) as exc_info:
            run_publish(_publish_args(verdict="reviewed"))

        assert exc_info.value.code == 1
        assert fake.created_notes == []
        err = capsys.readouterr().err
        assert "GitLab did not remove your earlier request for changes: Invalid permissions." in err
        assert "Nothing was published." in err

    def test_missing_destroy_mutation_without_block_goes_on(self, capsys, publish_gitlab) -> None:
        # GitLab CE: no mutation, and no request for changes can block the merge.
        fake = publish_gitlab(FakePublishGitLab([_draft(1)]))
        fake.destroy_mutation_exists = False
        run_publish(_publish_args(verdict="reviewed"))

        assert fake.state == "REVIEWED"
        assert "Set your reviewer state to reviewed." in capsys.readouterr().out

    def test_missing_destroy_mutation_with_block_stops(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)], state="REVIEWED", requested=True))
        fake.destroy_mutation_exists = False

        with pytest.raises(SystemExit) as exc_info:
            run_publish(_publish_args(verdict="reviewed"))

        assert exc_info.value.code == 1
        assert fake.created_notes == []
        err = capsys.readouterr().err
        assert "needs GitLab EE 17.8 or newer" in err
        assert "Nothing was published." in err

    def test_other_reviewers_request_is_reported(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)]))
        fake.other_requested = True
        run_publish(_publish_args(verdict="approve"))

        out = capsys.readouterr().out
        assert "Approved the MR." in out
        assert "blocked by requested changes, from another reviewer" in out

    def test_review_state_mismatch(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)]))
        fake.applies_verdict = False

        with pytest.raises(SystemExit) as exc_info:
            run_publish(_publish_args(verdict="requested-changes"))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Published 1 draft" in captured.out
        assert "Set your reviewer state" not in captured.out
        assert (
            "Error: The drafts were published, but the verdict 'requested-changes' was not applied:"
            " GitLab reports your review state as UNREVIEWED." in captured.err
        )

    def test_approval_mismatch(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1)]))
        fake.applies_verdict = False

        with pytest.raises(SystemExit) as exc_info:
            run_publish(_publish_args(verdict="approve"))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Approved the MR." not in captured.out
        assert "The drafts were published, but the verdict 'approve' was not applied" in captured.err

    def test_mismatch_without_drafts(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([]))
        fake.applies_verdict = False

        with pytest.raises(SystemExit):
            run_publish(_publish_args(verdict="reviewed"))

        captured = capsys.readouterr()
        assert "No drafts to publish." in captured.out
        assert "Error: The verdict 'reviewed' was not applied:" in captured.err

    def test_drafts_left_unpublished(self, capsys, publish_gitlab) -> None:
        fake = publish_gitlab(FakePublishGitLab([_draft(1), _draft(2)]))
        fake.publishes = False

        with pytest.raises(SystemExit) as exc_info:
            run_publish(_publish_args(verdict="reviewed"))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Published" not in captured.out
        assert "Set your reviewer state to reviewed." in captured.out
        assert "Error: 2 drafts still unpublished; 'read' shows them." in captured.err


class TestMentions:
    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ("requested review from @me", True),
            ("requested review from @me and @bob", True),
            ("requested review from @bob, @me and @carol", True),
            ("removed review request for @me.", True),
            ("requested review from @me2", False),
            ("requested review from @me-too", False),
            ("requested review from @me.too", False),
            ("requested review from @someme", False),
            ("requested review from user@me", False),
        ],
    )
    def test_whole_username(self, body: str, expected: bool) -> None:
        assert _mentions(body, "me") is expected


class TestDelete:
    def test_no_drafts(self, capsys, context) -> None:
        with patch("glab_discussion.commands.drafts.glab_api", return_value=[]):
            run_delete(Namespace(force=False))
        assert "You have no drafts on this MR." in capsys.readouterr().out

    def test_without_force_lists_and_deletes_nothing(self, capsys, context) -> None:
        drafts = [
            _draft(3, "Reply text", discussion_id="a" * 40, resolve_discussion=True),
            _draft(1, "A general comment " * 10),
            _draft(
                2,
                "Inline",
                position={
                    "base_sha": "b",
                    "head_sha": "h",
                    "start_sha": "s",
                    "old_path": "src/a.py",
                    "new_path": "src/a.py",
                    "new_line": 42,
                },
            ),
        ]
        with patch("glab_discussion.commands.drafts.glab_api", return_value=drafts) as api:
            run_delete(Namespace(force=False))

        api.assert_called_once()
        out = capsys.readouterr().out
        assert "3 drafts would be deleted:" in out
        lines = out.splitlines()
        assert lines[1].startswith("  draft:1  general  A general comment")
        assert lines[1].endswith("...")
        assert lines[2] == "  draft:2  inline src/a.py:42  Inline"
        assert lines[3] == f"  draft:3  reply to {'a' * 40}, resolves thread  Reply text"
        assert "Nothing was deleted. Run 'glab-discussion drafts delete --force' to delete them." in out

    def test_force_deletes_all(self, capsys, context) -> None:
        deleted: list[str] = []
        lock = threading.Lock()

        def respond(endpoint: str, **kwargs):
            if kwargs.get("method") == "DELETE":
                with lock:
                    deleted.append(endpoint)
                return None
            return [_draft(i) for i in range(1, 8)]

        with patch("glab_discussion.commands.drafts.glab_api", side_effect=respond):
            run_delete(Namespace(force=True))

        assert sorted(deleted) == sorted(f"{DRAFTS_ENDPOINT}/{i}" for i in range(1, 8))
        assert "Deleted 7 of 7 drafts." in capsys.readouterr().out
        context.assert_not_called()

    def test_force_retries_and_treats_404_as_deleted(self, capsys, context) -> None:
        attempts: dict[str, int] = {}
        lock = threading.Lock()

        def respond(endpoint: str, **kwargs):
            if kwargs.get("method") != "DELETE":
                return [_draft(1), _draft(2)]
            with lock:
                attempts[endpoint] = attempts.get(endpoint, 0) + 1
                count = attempts[endpoint]
            if endpoint.endswith("/1") and count == 1:
                raise GlabApiError("glab api failed: glab: HTTP 502", stderr="glab: HTTP 502\n")
            if endpoint.endswith("/2"):
                raise GlabApiError(
                    "glab api failed: 404 Draft Note Not Found", stderr="glab: 404 Draft Note Not Found (HTTP 404)\n"
                )
            return None

        with patch("glab_discussion.commands.drafts.glab_api", side_effect=respond):
            run_delete(Namespace(force=True))

        assert attempts == {f"{DRAFTS_ENDPOINT}/1": 2, f"{DRAFTS_ENDPOINT}/2": 1}
        assert context.call_args_list == [call(1)]
        assert "Deleted 2 of 2 drafts." in capsys.readouterr().out

    def test_force_reports_failures_after_three_retries(self, capsys, context) -> None:
        def respond(endpoint: str, **kwargs):
            if kwargs.get("method") != "DELETE":
                return [_draft(1), _draft(2)]
            if endpoint.endswith("/2"):
                raise GlabApiError("glab api failed: glab: HTTP 500", stderr="glab: HTTP 500\n")
            return None

        with (
            patch("glab_discussion.commands.drafts.glab_api", side_effect=respond),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_delete(Namespace(force=True))

        assert exc_info.value.code == 1
        assert context.call_args_list == [call(1), call(2), call(4)]
        captured = capsys.readouterr()
        assert "Deleted 1 of 2 drafts." in captured.out
        assert "draft:2: glab api failed: glab: HTTP 500" in captured.err
        assert "Run 'glab-discussion drafts delete --force' again." in captured.err


class TestHttpStatus:
    @pytest.mark.parametrize(
        ("stderr", "status"),
        [
            ("glab: 404 Draft Note Not Found (HTTP 404)\n", 404),
            ("glab: HTTP 502\n", 502),
            ("error connecting to gitlab.com\n", None),
        ],
    )
    def test_reads_status_from_glab_stderr(self, stderr: str, status: int | None) -> None:
        assert GlabApiError("failed", stderr=stderr).http_status == status
