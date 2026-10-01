from __future__ import annotations

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import NoReturn

from glab_discussion.api import GlabApiError, glab_api, glab_graphql
from glab_discussion.context import resolve_mr_context
from glab_discussion.models import DraftNote, MrContext, parse_draft_note

DELETE_WORKERS = 5
DELETE_RETRY_DELAYS = (1, 2, 4)  # seconds to wait before each retry
PREVIEW_LENGTH = 60
ACTIVITY_PAGE_SIZE = 50

# CLI spelling -> the /submit_review argument, and the reviewState GraphQL reports afterwards (None for approve,
# which is confirmed through approvedBy instead).
_VERDICTS: dict[str, tuple[str, str | None]] = {
    "reviewed": ("reviewed", "REVIEWED"),
    "requested-changes": ("requested_changes", "REQUESTED_CHANGES"),
    "approve": ("approve", None),
}

# System note actions a user's verdict leaves on the MR, in CLI spelling. `reviewed` notes exist since GitLab 17.10,
# `requested_changes` since 17.0.
_VERDICT_ACTIONS = {"approved": "approve", "requested_changes": "requested-changes", "reviewed": "reviewed"}

# Everything `drafts publish` needs to know about the MR and the current user, in one request. The activity notes
# are only needed to find the previous verdict, so the read-back after publishing leaves them out.
_STATE_QUERY = """
query($projectPath: ID!, $iid: String!, $withActivity: Boolean!, $activityPageSize: Int!) {
  currentUser { username }
  project(fullPath: $projectPath) {
    mergeRequest(iid: $iid) {
      allowsMultipleReviewers
      reviewers { nodes { username mergeRequestInteraction { reviewState } } }
      approvedBy { nodes { username } }
      mergeabilityChecks { identifier status }
      notes(filter: ONLY_ACTIVITY, last: $activityPageSize) @include(if: $withActivity) {
        pageInfo { hasPreviousPage startCursor }
        nodes { body createdAt author { username } systemNoteMetadata { action } }
      }
    }
  }
}
"""

_ACTIVITY_PAGE_QUERY = """
query($projectPath: ID!, $iid: String!, $before: String!, $activityPageSize: Int!) {
  project(fullPath: $projectPath) {
    mergeRequest(iid: $iid) {
      notes(filter: ONLY_ACTIVITY, last: $activityPageSize, before: $before) {
        pageInfo { hasPreviousPage startCursor }
        nodes { body createdAt author { username } systemNoteMetadata { action } }
      }
    }
  }
}
"""

_APPEND_REVIEWER_MUTATION = """
mutation($projectPath: ID!, $iid: String!, $usernames: [String!]!) {
  mergeRequestSetReviewers(
    input: {projectPath: $projectPath, iid: $iid, reviewerUsernames: $usernames, operationMode: APPEND}
  ) {
    errors
    mergeRequest { reviewers { nodes { username } } }
  }
}
"""

_DESTROY_REQUESTED_CHANGES_MUTATION = """
mutation($projectPath: ID!, $iid: String!) {
  mergeRequestDestroyRequestedChanges(input: {projectPath: $projectPath, iid: $iid}) {
    errors
  }
}
"""

_NOTHING_TO_REMOVE_ERRORS = {"User has not requested changes for this merge request", "Invalid license"}


@dataclass
class MrReviewState:
    username: str
    allows_multiple_reviewers: bool | None
    reviewers: dict[str, str | None]  # username -> reviewState, in GitLab's order
    approved: bool  # the current user is in approvedBy
    requested_changes_blocked: bool  # the REQUESTED_CHANGES mergeability check fails, for anyone's request
    activity: list[dict] = field(default_factory=list)  # oldest first
    activity_before: str | None = None  # cursor of an older page of activity, if there is one


def _plural(count: int) -> str:
    return f"{count} draft{'' if count == 1 else 's'}"


def _list_drafts(ctx: MrContext) -> list[DraftNote]:
    raw = glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/draft_notes",
        paginate=True,
        hostname=ctx.hostname,
    )
    return sorted((parse_draft_note(d) for d in raw or []), key=lambda d: d.id)


def _mr_variables(ctx: MrContext) -> dict:
    return {"projectPath": ctx.project_path, "iid": str(ctx.mr_iid), "activityPageSize": ACTIVITY_PAGE_SIZE}


def _parse_activity(notes: dict | None) -> tuple[list[dict], str | None]:
    notes = notes or {}
    page_info = notes.get("pageInfo") or {}
    before = page_info.get("startCursor") if page_info.get("hasPreviousPage") else None
    return list(notes.get("nodes") or []), before


def _fetch_state(ctx: MrContext, *, with_activity: bool) -> MrReviewState:
    data = glab_graphql(_STATE_QUERY, {**_mr_variables(ctx), "withActivity": with_activity}, hostname=ctx.hostname)
    username = (data.get("currentUser") or {}).get("username", "")
    mr = (data.get("project") or {}).get("mergeRequest") or {}
    reviewers = {
        node.get("username", ""): (node.get("mergeRequestInteraction") or {}).get("reviewState")
        for node in (mr.get("reviewers") or {}).get("nodes") or []
    }
    approvers = {node.get("username") for node in (mr.get("approvedBy") or {}).get("nodes") or []}
    checks = mr.get("mergeabilityChecks") or []
    activity, before = _parse_activity(mr.get("notes"))
    return MrReviewState(
        username=username,
        allows_multiple_reviewers=mr.get("allowsMultipleReviewers"),
        reviewers=reviewers,
        approved=username in approvers,
        requested_changes_blocked=any(
            c.get("identifier") == "REQUESTED_CHANGES" and c.get("status") == "FAILED" for c in checks
        ),
        activity=activity,
        activity_before=before,
    )


def _fetch_drafts_and_state(ctx: MrContext, *, with_activity: bool) -> tuple[list[DraftNote], MrReviewState]:
    """Fetch the drafts (REST) and the review state (GraphQL) in parallel: they do not depend on each other."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        drafts = pool.submit(_list_drafts, ctx)
        state = pool.submit(_fetch_state, ctx, with_activity=with_activity)
        return drafts.result(), state.result()


def _mentions(body: str, username: str) -> bool:
    """Whether `body` references @username as a whole username, not as the start of a longer one."""
    return re.search(rf"(?<![\w.-])@{re.escape(username)}(?![\w-]|\.[\w-])", body) is not None


def _verdict_of_note(note: dict, username: str) -> tuple[bool, str | None]:
    """Return (decided, verdict) for one activity note, read as the newest relevant event."""
    action = (note.get("systemNoteMetadata") or {}).get("action")
    author = (note.get("author") or {}).get("username")
    if action in _VERDICT_ACTIONS and author == username:
        return True, _VERDICT_ACTIONS[action]
    if action == "unapproved" and author == username:
        return True, None
    # "requested review from @user", also for a re-requested review, or "removed review request for @user".
    # Either way, the user owes the MR a new review.
    if action == "reviewer" and _mentions(note.get("body") or "", username):
        return True, None
    return False, None


def _previous_verdict(ctx: MrContext, state: MrReviewState) -> str | None:
    """Return the verdict the current user already gave the MR, in CLI spelling, or None if they owe a new one.

    The review state cannot tell: creating a draft sets it to REVIEW_STARTED, whatever the verdict was. The MR's
    system notes record every verdict and every review request, so the newest relevant one decides.
    """
    if state.approved:
        return "approve"
    activity, before = state.activity, state.activity_before
    while True:
        for note in reversed(activity):
            decided, verdict = _verdict_of_note(note, state.username)
            if decided:
                return verdict
        if not before:
            return None
        data = glab_graphql(_ACTIVITY_PAGE_QUERY, {**_mr_variables(ctx), "before": before}, hostname=ctx.hostname)
        notes = ((data.get("project") or {}).get("mergeRequest") or {}).get("notes")
        activity, before = _parse_activity(notes)


def _stop_before_publishing(message: str) -> NoReturn:
    print(f"Error: {message} Nothing was published.", file=sys.stderr)
    sys.exit(1)


def _ensure_reviewer(ctx: MrContext, state: MrReviewState) -> None:
    """Make the current user a reviewer of the MR, which /submit_review needs to set a review state.

    Exit with nothing published when GitLab does not add the user: it drops a reviewer it cannot add without an error.
    """
    username = state.username
    if username in state.reviewers:
        return

    data = glab_graphql(
        _APPEND_REVIEWER_MUTATION,
        {"projectPath": ctx.project_path, "iid": str(ctx.mr_iid), "usernames": [username]},
        hostname=ctx.hostname,
    )
    payload = data.get("mergeRequestSetReviewers") or {}
    added = [
        node.get("username") for node in ((payload.get("mergeRequest") or {}).get("reviewers") or {}).get("nodes") or []
    ]
    if username in added:
        print(f"Added you (@{username}) as a reviewer, so that the verdict can be set.")
        return

    message = f"GitLab did not add you (@{username}) as a reviewer, so the verdict cannot be set."
    others = [r for r in state.reviewers if r != username]
    if state.allows_multiple_reviewers is False and others:
        message += f" This MR allows only one reviewer, and @{others[0]} is the reviewer already."
    errors = payload.get("errors") or []
    if errors:
        message += " GitLab reports: " + "; ".join(errors) + "."
    _stop_before_publishing(message)


def _create_summary_draft(ctx: MrContext, body: str) -> None:
    """Add the summary as a general draft, so it is published as part of the review."""
    result = glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/draft_notes",
        method="POST",
        json_body={"note": body},
        hostname=ctx.hostname,
    )
    print(f"Added the summary as draft:{result['id']}.")


def run_publish(args: argparse.Namespace) -> None:
    ctx = resolve_mr_context(args)

    body = None
    if args.body is not None:
        body = sys.stdin.read() if args.body == "-" else args.body

    drafts, state = _fetch_drafts_and_state(ctx, with_activity=args.verdict is None)
    # Without --verdict the review would still get the default verdict, but a bare call with nothing pending
    # must not change the review state.
    if not drafts and not body and not args.verdict:
        print(
            "Error: nothing to publish. You have no drafts on this MR, and neither --body nor --verdict was given.",
            file=sys.stderr,
        )
        sys.exit(1)

    verdict = args.verdict
    if verdict is None:
        # A review always carries a verdict: being a reviewer with a review state is what lets the MR author
        # re-request a review. Default to reviewed only when it replaces no earlier verdict.
        previous = _previous_verdict(ctx, state)
        if previous is not None:
            _stop_before_publishing(
                f"You already gave this MR the verdict '{previous}', and this review would replace it."
                " Pass --verdict reviewed, --verdict requested-changes or --verdict approve"
                " to say which verdict this review gives."
            )
        print("No --verdict given, and you have no verdict on this MR yet, so the verdict defaults to reviewed.")
        verdict = "reviewed"

    _publish_with_verdict(ctx, verdict, body, len(drafts), state)


def _revoke_approval(ctx: MrContext) -> None:
    """Revoke the current user's approval. GitLab refuses to change the review state of a reviewer who approved."""
    try:
        glab_api(
            f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/unapprove",
            method="POST",
            hostname=ctx.hostname,
        )
    except GlabApiError as e:
        _stop_before_publishing(f"You approved this MR, and GitLab did not revoke the approval: {e}.")
    print("Revoked your approval, so that the new verdict can be set.")


def _remove_requested_changes(ctx: MrContext, state: MrReviewState) -> bool:
    """Remove the current user's earlier request for changes, which blocks the merge until it is removed.

    Setting another review state does not remove it on GitLab before 19.2 (EE). No API shows whose request it
    is, and the review state is no proof either: it can be reviewed while the request remains. The mutation's
    own answer is the check, so it runs whenever the new verdict is not requested-changes. Removing a request
    also resets the review state to unreviewed, so this runs before `/submit_review`.
    Return True when GitLab removed a request of the current user. Exit when it may still block the merge.
    """
    try:
        data = glab_graphql(
            _DESTROY_REQUESTED_CHANGES_MUTATION,
            {"projectPath": ctx.project_path, "iid": str(ctx.mr_iid)},
            hostname=ctx.hostname,
        )
    except GlabApiError as e:
        # GitLab CE, and EE before 17.8, have no such mutation. A request for changes can only block the merge
        # when the REQUESTED_CHANGES check fails, so go on when it does not.
        if not state.requested_changes_blocked:
            return False
        _stop_before_publishing(
            "GitLab reports this MR as blocked by requested changes, and this GitLab cannot remove a request"
            " for changes through the API (mergeRequestDestroyRequestedChanges needs GitLab EE 17.8 or newer),"
            f" so it cannot tell whether the request is yours. GitLab reports: {e}."
        )

    errors = (data.get("mergeRequestDestroyRequestedChanges") or {}).get("errors") or []
    if not errors:
        print("Removed your earlier request for changes, so that the new verdict can be set.")
        return True
    # The service answers with these fixed, untranslated messages when there is nothing of the user's to remove:
    # no request of theirs, or a license without the feature, where a request does not block the merge.
    if all(e in _NOTHING_TO_REMOVE_ERRORS for e in errors):
        return False
    _stop_before_publishing(f"GitLab did not remove your earlier request for changes: {'; '.join(errors)}.")


def _publish_with_verdict(
    ctx: MrContext, verdict: str, body: str | None, draft_count: int, state: MrReviewState
) -> None:
    command_state, expected_state = _VERDICTS[verdict]
    username = state.username
    _ensure_reviewer(ctx, state)

    # Remove the previous verdict first: GitLab before 19.2 does not replace one verdict with another.
    if verdict != "approve" and state.approved:
        _revoke_approval(ctx)
    if verdict != "requested-changes":
        _remove_requested_changes(ctx, state)

    if body:
        _create_summary_draft(ctx, body)
        draft_count += 1

    # Only GitLab 19.2+ applies a verdict sent to bulk_publish; older versions ignore it and still answer 204.
    # The quick action publishes the drafts and sets the verdict on every version since 16.7, but discards
    # the result of the state update, so both outcomes are read back below.
    result = glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/notes",
        method="POST",
        json_body={"body": f"/submit_review {command_state}"},
        hostname=ctx.hostname,
    )
    for message in (result or {}).get("summary") or []:
        print(f"GitLab: {message}")

    errors: list[str] = []

    remaining, after = _fetch_drafts_and_state(ctx, with_activity=False)
    if remaining:
        errors.append(f"{_plural(len(remaining))} still unpublished; 'read' shows them.")
    elif draft_count == 0:
        print("No drafts to publish.")
    else:
        print(f"Published {_plural(draft_count)} - {ctx.mr_url}")
    published = "The drafts were published, but the" if draft_count and not remaining else "The"
    not_applied = f"{published} verdict '{verdict}' was not applied:"

    if expected_state is None:
        if after.approved:
            print("Approved the MR.")
        else:
            errors.append(f"{not_applied} @{username} is not in the MR's approvals.")
    else:
        review_state = after.reviewers.get(username)
        if review_state != expected_state:
            errors.append(f"{not_applied} GitLab reports your review state as {review_state}.")
        elif after.approved:
            errors.append(f"{not_applied} your approval is still on the MR.")
        else:
            print(f"Set your reviewer state to {verdict}.")

    # The earlier step confirmed that no request for changes of the current user is left, so a request that
    # still blocks the merge is someone else's.
    if verdict != "requested-changes" and after.requested_changes_blocked:
        print("GitLab still reports the MR as blocked by requested changes, from another reviewer.")

    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


def _describe(draft: DraftNote) -> str:
    if draft.discussion_id:
        target = f"reply to {draft.discussion_id}"
        if draft.resolve_discussion:
            target += ", resolves thread"
    elif draft.position:
        line = draft.position.new_line if draft.position.new_line is not None else draft.position.old_line
        target = f"inline {draft.position.new_path or draft.position.old_path}:{line}"
    else:
        target = "general"

    preview = " ".join(draft.body.split())
    if len(preview) > PREVIEW_LENGTH:
        preview = preview[: PREVIEW_LENGTH - 3] + "..."
    return f"draft:{draft.id}  {target}  {preview}"


def _delete_one(ctx: MrContext, draft: DraftNote) -> GlabApiError | None:
    """Delete one draft, retrying every failure. Return the last error, or None once the draft is gone."""
    last_error: GlabApiError | None = None
    for attempt in range(len(DELETE_RETRY_DELAYS) + 1):
        if attempt > 0:
            time.sleep(DELETE_RETRY_DELAYS[attempt - 1])
        try:
            glab_api(
                f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/draft_notes/{draft.id}",
                method="DELETE",
                hostname=ctx.hostname,
            )
            return None
        except GlabApiError as e:
            # A draft that is already gone was deleted by an earlier attempt or by someone else.
            if e.http_status == 404:
                return None
            last_error = e
    return last_error


def run_delete(args: argparse.Namespace) -> None:
    ctx = resolve_mr_context(args)
    drafts = _list_drafts(ctx)

    if not drafts:
        print("You have no drafts on this MR.")
        return

    if not args.force:
        print(f"{len(drafts)} draft{'' if len(drafts) == 1 else 's'} would be deleted:")
        for draft in drafts:
            print(f"  {_describe(draft)}")
        print("Nothing was deleted. Run 'glab-discussion drafts delete --force' to delete them.")
        return

    with ThreadPoolExecutor(max_workers=DELETE_WORKERS) as pool:
        results = list(pool.map(lambda d: (d, _delete_one(ctx, d)), drafts))

    failures = [(draft, error) for draft, error in results if error is not None]
    print(f"Deleted {len(drafts) - len(failures)} of {len(drafts)} drafts.")
    if not failures:
        return

    print(f"Could not delete {len(failures)} drafts:", file=sys.stderr)
    for draft, error in failures:
        print(f"  draft:{draft.id}: {error}", file=sys.stderr)
    print(
        "Run 'glab-discussion drafts delete --force' again. It lists your drafts again and deletes only the ones left.",
        file=sys.stderr,
    )
    sys.exit(1)
