from __future__ import annotations

from glab_discussion.commands.diff import annotate_diff

from .conftest import SAMPLE_DIFF


class TestAnnotateDiff:
    def test_basic_diff(self) -> None:
        result = annotate_diff(SAMPLE_DIFF)
        # Should have lines for: hunk header, context, context, removed, added, added, context
        assert len(result) > 0

    def test_hunk_header(self) -> None:
        result = annotate_diff(SAMPLE_DIFF)
        # First line should be the hunk header with empty line numbers
        hunk_line = result[0]
        assert "@@ -10,7 +10,8 @@" in hunk_line

    def test_context_lines(self) -> None:
        result = annotate_diff(SAMPLE_DIFF)
        # "     def bar(self):" is context at old:10, new:10
        context_line = result[1]
        assert "10" in context_line
        assert "def bar(self):" in context_line

    def test_removed_line(self) -> None:
        result = annotate_diff(SAMPLE_DIFF)
        # Find the removed line
        removed = [line for line in result if "y = old()" in line]
        assert len(removed) == 1
        # Removed lines should have old line number but no new line number
        assert "12" in removed[0]  # old_line = 12
        assert "-        y = old()" in removed[0]

    def test_added_lines(self) -> None:
        result = annotate_diff(SAMPLE_DIFF)
        # Find added lines - the sample diff has leading spaces so the "+" is indented
        added = [line for line in result if "y = new_method()" in line]
        assert len(added) == 1
        assert "12" in added[0]  # new_line = 12

        added2 = [line for line in result if "z = extra()" in line]
        assert len(added2) == 1
        assert "13" in added2[0]  # new_line = 13

    def test_line_numbers_increment(self) -> None:
        result = annotate_diff(SAMPLE_DIFF)
        # After the hunk header (@@ -10,7 +10,8 @@), lines should start at old:10, new:10
        # Line 1 (context): old=10, new=10 "     def bar(self):"
        # Line 2 (context): old=11, new=11 "         x = 1"
        # Line 3 (removed): old=12       "-        y = old()"
        # Line 4 (added):         new=12 "+        y = new_method()"
        # Line 5 (added):         new=13 "+        z = extra()"
        # Line 6 (context): old=13, new=14 "         return x"

        # Verify the return line has correct numbers
        return_line = [line for line in result if "return x" in line]
        assert len(return_line) == 1
        assert "13" in return_line[0]  # old line
        assert "14" in return_line[0]  # new line

    def test_empty_diff(self) -> None:
        result = annotate_diff("")
        assert result == []

    def test_diff_headers_skipped(self) -> None:
        diff_with_headers = "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,3 @@\n context\n-old\n+new\n"
        result = annotate_diff(diff_with_headers)
        # Should not include --- or +++ lines
        assert not any("--- a/file.py" in line for line in result)
        assert not any("+++ b/file.py" in line for line in result)

    def test_multiple_hunks(self) -> None:
        multi_hunk = "@@ -1,3 +1,3 @@\n a\n-b\n+c\n@@ -10,3 +10,3 @@\n x\n-y\n+z\n"
        result = annotate_diff(multi_hunk)
        # Should have 2 hunk headers
        hunk_headers = [line for line in result if "@@" in line]
        assert len(hunk_headers) == 2
