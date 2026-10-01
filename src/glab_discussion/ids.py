from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Literal

_REF_RE = re.compile(r"^(note|draft):(\d+)$")


@dataclass(frozen=True)
class NoteRef:
    """A published note or a pending draft, as `read` prints it.

    Draft IDs and note IDs come from separate sequences and can collide on one MR,
    so a bare number cannot say which one the caller means.
    """

    kind: Literal["note", "draft"]
    id: int

    @property
    def is_draft(self) -> bool:
        return self.kind == "draft"

    def __str__(self) -> str:
        return f"{self.kind}:{self.id}"


def parse_note_ref(value: str) -> NoteRef:
    """Parse `note:123` or `draft:123`. Used as an argparse `type`."""
    match = _REF_RE.match(value.strip())
    if match:
        kind: Literal["note", "draft"] = "note" if match.group(1) == "note" else "draft"
        return NoteRef(kind=kind, id=int(match.group(2)))

    if value.strip().isdigit():
        number = value.strip()
        raise argparse.ArgumentTypeError(
            f"Ambiguous ID '{number}': pass 'note:{number}' for a published note"
            f" or 'draft:{number}' for your pending draft. 'read' prints IDs in this form."
        )

    raise argparse.ArgumentTypeError(
        f"Unrecognized ID '{value}': pass 'note:<id>' for a published note"
        " or 'draft:<id>' for your pending draft. 'read' prints IDs in this form."
    )
