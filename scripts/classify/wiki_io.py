"""Atomic wiki page helpers for synthesis output."""

from __future__ import annotations

from pathlib import Path


GENERATED_START = "<!-- @generated:start -->"
GENERATED_END = "<!-- @generated:end -->"
USER_START = "<!-- @user:start -->"
USER_END = "<!-- @user:end -->"


def replace_generated_region(text: str, new_body: str) -> str:
    """Replace the generated sentinel region, preserving any user region bytes."""

    if _generated_marker_inside_fence(text):
        raise ValueError("malformed generated sentinels")

    start_count = text.count(GENERATED_START)
    end_count = text.count(GENERATED_END)

    if start_count == 0 and end_count == 0:
        base = text if text.endswith("\n") else f"{text}\n"
        body = new_body if new_body.endswith("\n") else f"{new_body}\n"
        return (
            f"{base}\n"
            f"{GENERATED_START}\n"
            f"{body}"
            f"{GENERATED_END}\n\n"
            f"{USER_START}\n"
            f"{USER_END}\n"
        )

    if start_count != 1 or end_count != 1:
        raise ValueError("malformed generated sentinels")

    start = text.find(GENERATED_START)
    end = text.find(GENERATED_END)
    if end < start:
        raise ValueError("malformed generated sentinels")

    body = new_body if new_body.endswith("\n") else f"{new_body}\n"
    before = text[: start + len(GENERATED_START)]
    after = text[end:]
    return f"{before}\n{body}{after}"


def append_log(vault: Path, entry: str) -> None:
    path = vault / "wiki" / "log.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    line = entry if entry.endswith("\n") else f"{entry}\n"
    _atomic_write(path, f"{existing}{line}")


def upsert_index_line(
    vault: Path,
    slug: str,
    summary_line: str,
    *,
    section: str | None = None,
) -> None:
    path = vault / "wiki" / "index.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    target = f"- [[{slug}]]"
    replacement = f"{target} — {summary_line}"

    if section is not None:
        _atomic_write(
            path,
            _upsert_index_line_in_section(
                existing=existing,
                target=target,
                replacement=replacement,
                section=section,
            ),
        )
        return

    lines = existing.splitlines()

    for idx, line in enumerate(lines):
        if line.startswith(target):
            lines[idx] = replacement
            break
    else:
        lines.append(replacement)

    _atomic_write(path, "\n".join(lines).rstrip() + "\n")


def _upsert_index_line_in_section(
    *,
    existing: str,
    target: str,
    replacement: str,
    section: str,
) -> str:
    lines = existing.splitlines(keepends=True)

    heading_idx = _find_section_heading(lines, section)
    if heading_idx is None:
        addition = f"{section}\n{replacement}\n"
        if not existing:
            lines = addition.splitlines(keepends=True)
        else:
            separator = "\n" if existing.endswith("\n") else "\n\n"
            lines.extend(f"{separator}{addition}".splitlines(keepends=True))
        heading_idx = _find_section_heading(lines, section)

    if heading_idx is None:
        raise ValueError(f"section was not created: {section}")

    section_end = _find_next_h2(lines, heading_idx + 1)
    lines = [
        line
        for idx, line in enumerate(lines)
        if not (
            line.startswith(target)
            and not (heading_idx < idx < section_end)
        )
    ]

    heading_idx = _find_section_heading(lines, section)
    if heading_idx is None:
        raise ValueError(f"section missing after migration: {section}")
    section_end = _find_next_h2(lines, heading_idx + 1)

    for idx in range(heading_idx + 1, section_end):
        if lines[idx].startswith(target):
            lines[idx] = f"{replacement}{_line_ending(lines[idx])}"
            break
    else:
        insert_at = section_end
        if insert_at > heading_idx + 1 and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        lines.insert(insert_at, f"{replacement}\n")

    return "".join(lines)


def _find_section_heading(lines: list[str], section: str) -> int | None:
    for idx, line in enumerate(lines):
        if line.rstrip("\r\n") == section:
            return idx
    return None


def _find_next_h2(lines: list[str], start: int) -> int:
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## "):
            return idx
    return len(lines)


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _generated_marker_inside_fence(text: str) -> bool:
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif in_fence and (GENERATED_START in line or GENERATED_END in line):
            return True
    return False
