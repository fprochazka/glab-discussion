from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MrContext:
    hostname: str  # e.g. "gitlab.com"
    project_id: int  # numeric project ID
    project_path: str  # e.g. "group/project"
    mr_iid: int  # MR internal ID
    mr_url: str  # web URL of the MR


@dataclass
class Position:
    """Position data for DiffNote."""

    base_sha: str
    head_sha: str
    start_sha: str
    old_path: str
    new_path: str
    position_type: str = "text"
    old_line: int | None = None
    new_line: int | None = None


@dataclass
class Note:
    id: int
    author_username: str
    author_id: int
    is_bot: bool
    body: str
    created_at: str
    updated_at: str
    system: bool
    resolvable: bool
    resolved: bool
    note_type: str | None  # None, "DiffNote", "DiscussionNote"
    position: Position | None = None


@dataclass
class Discussion:
    id: str
    individual_note: bool
    notes: list[Note] = field(default_factory=list)

    @property
    def is_diff_note(self) -> bool:
        return bool(self.notes and self.notes[0].note_type == "DiffNote")

    @property
    def is_system(self) -> bool:
        return bool(self.notes and all(n.system for n in self.notes))

    @property
    def resolved(self) -> bool:
        return all(n.resolved for n in self.notes if n.resolvable)

    @property
    def first_note(self) -> Note:
        return self.notes[0]

    @property
    def max_timestamp(self) -> str:
        """MAX(created_at, updated_at) across all notes."""
        timestamps: list[str] = []
        for n in self.notes:
            timestamps.append(n.created_at)
            timestamps.append(n.updated_at)
        return max(timestamps)


@dataclass
class UserInfo:
    id: int
    username: str
    name: str
    is_bot: bool


def parse_position(data: dict) -> Position:
    """Parse a position dict from the GitLab API into a Position dataclass."""
    return Position(
        base_sha=data["base_sha"],
        head_sha=data["head_sha"],
        start_sha=data["start_sha"],
        old_path=data["old_path"],
        new_path=data["new_path"],
        position_type=data.get("position_type", "text"),
        old_line=data.get("old_line"),
        new_line=data.get("new_line"),
    )


def parse_note(data: dict, *, is_bot: bool = False) -> Note:
    """Parse a note dict from the GitLab API into a Note dataclass."""
    author = data.get("author", {})
    position = None
    if data.get("position"):
        position = parse_position(data["position"])

    return Note(
        id=data["id"],
        author_username=author.get("username", "unknown"),
        author_id=author.get("id", 0),
        is_bot=is_bot,
        body=data.get("body", ""),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        system=data.get("system", False),
        resolvable=data.get("resolvable", False),
        resolved=data.get("resolved", False),
        note_type=data.get("type"),
        position=position,
    )


def parse_discussion(data: dict) -> Discussion:
    """Parse a discussion dict from the GitLab API into a Discussion dataclass."""
    notes = [parse_note(n) for n in data.get("notes", [])]
    return Discussion(
        id=data["id"],
        individual_note=data.get("individual_note", False),
        notes=notes,
    )
