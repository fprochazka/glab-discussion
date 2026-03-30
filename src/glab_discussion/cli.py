import argparse
import sys


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

    # --- diff ---
    diff_parser = subparsers.add_parser("diff", parents=[mr_parent], help="Show MR diff information")
    diff_parser.add_argument("--file", help="Filter to a single file path")
    diff_parser.add_argument("--version", type=int, help="Specific diff version ID")

    # --- resolve ---
    resolve_parser = subparsers.add_parser("resolve", parents=[mr_parent], help="Resolve or unresolve a discussion")
    resolve_parser.add_argument("discussion_id", help="Discussion ID to resolve")
    resolve_parser.add_argument("--unresolve", action="store_true", default=False, help="Unresolve instead of resolve")

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
    else:
        parser.print_help()
        sys.exit(1)
