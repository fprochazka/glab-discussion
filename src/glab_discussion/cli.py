import argparse
import sys

from glab_discussion.ids import parse_note_ref

NOTE_REF_METAVAR = "note:ID|draft:ID"
NOTE_REF_HELP = "as 'read' prints it: note:123 for a published note, draft:123 for your pending draft"


def main(argv: list[str] | None = None) -> None:
    # Shared parent parser for MR context flags
    mr_parent = argparse.ArgumentParser(add_help=False)
    mr_parent.add_argument("--mr-url", help="Full URL of the merge request")
    mr_parent.add_argument("--hostname", help="GitLab hostname (e.g. gitlab.com)")
    mr_parent.add_argument("--project", help="GitLab project path (e.g. group/project)")
    mr_parent.add_argument("--mr-iid", type=int, help="Merge request IID")

    parser = argparse.ArgumentParser(
        prog="glab-discussion",
        description="CLI wrapper around GitLab Discussions REST API for managing MR discussions.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- read ---
    read_parser = subparsers.add_parser("read", parents=[mr_parent], help="Read and display MR discussions")
    dump_group = read_parser.add_mutually_exclusive_group()
    dump_group.add_argument("--dump", action="store_true", default=False, help="Dump discussions as structured data")
    dump_group.add_argument("--no-dump", action="store_true", default=False, help="Human-readable format")
    read_parser.add_argument("--full", action="store_true", default=False, help="Force full rewrite (only with --dump)")

    # --- write ---
    write_parser = subparsers.add_parser("write", parents=[mr_parent], help="Create a new discussion or reply")
    write_parser.add_argument("--body", required=True, help='Note body text (use "-" for stdin)')
    write_parser.add_argument("--reply-to", metavar="DISCUSSION_ID", help="Reply to an existing discussion")
    write_parser.add_argument("--file", help="File path for a diff note")
    write_parser.add_argument("--new-line", type=int, help="New-side line number for diff note")
    write_parser.add_argument("--old-line", type=int, help="Old-side line number for diff note")
    write_parser.add_argument("--commit", metavar="SHA", help="Commit SHA for diff note")
    draft_group = write_parser.add_mutually_exclusive_group()
    draft_group.add_argument(
        "--draft",
        action="store_true",
        default=False,
        help="Write a pending draft that only you see until 'drafts publish'"
        " (default: the GLAB_DISCUSSION_WRITE_AS_DRAFT environment variable)",
    )
    draft_group.add_argument(
        "--no-draft",
        action="store_true",
        default=False,
        help="Publish the comment immediately, even if GLAB_DISCUSSION_WRITE_AS_DRAFT is true",
    )
    write_parser.add_argument(
        "--resolve",
        action="store_true",
        default=False,
        help="Resolve the thread when the draft is published (only with --reply-to and a draft)",
    )

    # --- diff ---
    diff_parser = subparsers.add_parser("diff", parents=[mr_parent], help="Show MR diff information")
    diff_parser.add_argument("--file", help="Filter to a single file path")
    diff_parser.add_argument("--version", type=int, help="Specific diff version ID")

    # --- resolve ---
    resolve_parser = subparsers.add_parser("resolve", parents=[mr_parent], help="Resolve or unresolve a discussion")
    resolve_parser.add_argument("discussion_id", help="Discussion ID to resolve")
    resolve_parser.add_argument("--unresolve", action="store_true", default=False, help="Unresolve instead of resolve")

    # --- delete ---
    delete_parser = subparsers.add_parser("delete", parents=[mr_parent], help="Delete a note or a draft")
    delete_parser.add_argument(
        "note_ref", type=parse_note_ref, metavar=NOTE_REF_METAVAR, help=f"ID to delete, {NOTE_REF_HELP}"
    )

    # --- edit ---
    edit_parser = subparsers.add_parser("edit", parents=[mr_parent], help="Edit a note or a draft")
    edit_parser.add_argument(
        "note_ref", type=parse_note_ref, metavar=NOTE_REF_METAVAR, help=f"ID to edit, {NOTE_REF_HELP}"
    )
    edit_parser.add_argument("--body", required=True, help='New note body text (use "-" for stdin)')

    # --- drafts ---
    drafts_parser = subparsers.add_parser("drafts", help="Publish or delete your pending drafts")
    drafts_subparsers = drafts_parser.add_subparsers(dest="drafts_command", required=True)

    publish_parser = drafts_subparsers.add_parser(
        "publish",
        parents=[mr_parent],
        help="Publish all your drafts as one review",
        description="Publish all your drafts on the MR as one review, with one notification.",
    )
    publish_parser.add_argument(
        "--body", help='Summary comment, added as a draft and published with the review (use "-" for stdin)'
    )
    publish_parser.add_argument(
        "--verdict",
        choices=["reviewed", "requested-changes", "approve"],
        help="The verdict of the review. Adds you as a reviewer if you are not one. Needs GitLab 16.7 or newer."
        " Default: reviewed, if you have not given the MR a verdict yet; otherwise --verdict is required.",
    )

    drafts_delete_parser = drafts_subparsers.add_parser(
        "delete",
        parents=[mr_parent],
        help="Delete all your drafts",
        description="List all your drafts on the MR. With --force, delete them.",
    )
    drafts_delete_parser.add_argument(
        "--force", action="store_true", default=False, help="Delete the drafts instead of listing them"
    )

    args = parser.parse_args(argv)

    if args.command == "read":
        from glab_discussion.commands.read import run

        run(args)
    elif args.command == "write":
        from glab_discussion.commands.write import run

        run(args)
    elif args.command == "diff":
        from glab_discussion.commands.diff import run

        run(args)
    elif args.command == "resolve":
        from glab_discussion.commands.resolve import run

        run(args)
    elif args.command == "delete":
        from glab_discussion.commands.delete import run

        run(args)
    elif args.command == "edit":
        from glab_discussion.commands.edit import run

        run(args)
    elif args.command == "drafts" and args.drafts_command == "publish":
        from glab_discussion.commands.drafts import run_publish

        run_publish(args)
    elif args.command == "drafts" and args.drafts_command == "delete":
        from glab_discussion.commands.drafts import run_delete

        run_delete(args)
    else:
        parser.print_help()
        sys.exit(1)
