"""Audit and optionally create missing canonical MOC stub pages."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Allow direct script invocation (`python scripts/classify/moc_audit.py`).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify import moc_map
from scripts.classify.classify_vault import _iter_md_files
from scripts.classify.frontmatter import read_frontmatter
from scripts.classify.wiki_io import _atomic_write


@dataclass(frozen=True)
class MissingMoc:
    name: str
    incoming_count: int
    status: str
    stub_body: str


@dataclass(frozen=True)
class LintIssue:
    path: Path
    message: str


@dataclass(frozen=True)
class VaultAudit:
    vault: Path
    missing_mocs: dict[str, MissingMoc]
    lint_issues: tuple[LintIssue, ...]


def audit_vault(*, vault: Path, apply: bool) -> VaultAudit:
    """Return missing-MOC and canonical-MOC frontmatter findings for one vault."""
    canonical_names = _canonical_moc_names()
    incoming_counts = {name: 0 for name in canonical_names}
    existing_names = {
        name for name in canonical_names if (vault / f"{name}.md").exists()
    }

    for path in _iter_audited_md_files(vault):
        target = _normalise_up_target(read_frontmatter(path).get("up"))
        if target in canonical_names and target not in existing_names:
            incoming_counts[target] += 1

    missing_mocs: dict[str, MissingMoc] = {}
    for name in canonical_names:
        if name in existing_names:
            continue
        incoming_count = incoming_counts[name]
        status = _missing_status(incoming_count=incoming_count, apply=apply)
        stub_body = build_stub_body(vault=vault, name=name)
        missing_mocs[name] = MissingMoc(
            name=name,
            incoming_count=incoming_count,
            status=status,
            stub_body=stub_body,
        )
        if apply and incoming_count >= 1:
            path = vault / f"{name}.md"
            if not path.exists():
                _atomic_write(path, stub_body)

    return VaultAudit(
        vault=vault,
        missing_mocs=missing_mocs,
        lint_issues=tuple(_lint_existing_mocs(vault=vault, names=canonical_names)),
    )


def build_stub_body(*, vault: Path, name: str) -> str:
    """Return the Inbox-archetype stub for a canonical MOC page."""
    description = _description_for(name)
    return (
        "---\n"
        "type: moc\n"
        f"org: {vault.name}\n"
        f"context: {_context_for(vault)}\n"
        "up: '[[Personal]]'\n"
        "tags: [moc]\n"
        "---\n\n"
        f"# {name}\n\n"
        f"{description}\n\n"
        "## Inbox\n\n"
        "```dataview\n"
        "LIST WHERE up = this.file.link SORT file.name ASC\n"
        "```\n\n"
        "## Organised\n\n"
        "<!-- curated content goes here -->\n"
    )


def render_reports(audits: Iterable[VaultAudit]) -> str:
    """Render deterministic dry-run/apply output for one or more vault audits."""
    parts: list[str] = []
    for audit in sorted(audits, key=lambda item: item.vault.name):
        parts.extend(_render_vault_report(audit))
    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", action="append", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    audits = [audit_vault(vault=vault, apply=args.apply) for vault in args.vault]
    print(render_reports(audits), end="")
    return 0


def _render_vault_report(audit: VaultAudit) -> list[str]:
    lines = [f"Vault: {audit.vault.name}", "", "Missing MOCs"]
    if not audit.missing_mocs:
        lines.append("- none")
    else:
        for name in sorted(audit.missing_mocs):
            missing = audit.missing_mocs[name]
            if missing.incoming_count == 0:
                lines.append(f"- {name} — skipped (no references)")
                continue
            lines.extend(
                [
                    (
                        f"- {name} — {missing.incoming_count} incoming references"
                        f" — {missing.status}"
                    ),
                    "",
                    "```markdown",
                    missing.stub_body.rstrip(),
                    "```",
                ]
            )

    lines.extend(["", "Frontmatter lint"])
    if not audit.lint_issues:
        lines.append("- none")
    else:
        for issue in sorted(
            audit.lint_issues,
            key=lambda item: item.path.relative_to(audit.vault).as_posix(),
        ):
            rel = issue.path.relative_to(audit.vault).as_posix()
            lines.append(f"- {rel}: {issue.message}")
    lines.append("")
    return lines


def _iter_audited_md_files(vault: Path) -> Iterable[Path]:
    for path in _iter_md_files(vault, None):
        rel_parts = path.relative_to(vault).parts
        if rel_parts and rel_parts[0] == "_resources":
            continue
        yield path


def _canonical_moc_names() -> tuple[str, ...]:
    return tuple(
        sorted({_normalise_up_target(value) for value in moc_map.UP_MAP.values()})
    )


def _missing_status(*, incoming_count: int, apply: bool) -> str:
    if incoming_count == 0:
        return "skipped (no references)"
    if apply:
        return "created"
    return "would create"


def _lint_existing_mocs(*, vault: Path, names: tuple[str, ...]) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for name in names:
        path = vault / f"{name}.md"
        if not path.exists():
            continue
        target = _normalise_up_target(read_frontmatter(path).get("up"))
        if not target:
            continue
        display = f"[[{target}]]"
        if target == name:
            issues.append(
                LintIssue(path=path, message=f"up points to itself ({display})")
            )
            continue
        if not (vault / f"{target}.md").exists():
            issues.append(
                LintIssue(path=path, message=f"up points to missing page {display}")
            )
    return issues


def _normalise_up_target(value: Any) -> str:
    if isinstance(value, list) and len(value) == 1:
        return _normalise_up_target(value[0])
    if not isinstance(value, str):
        return ""
    target = value.strip().strip("'\"")
    if target.startswith("[[") and target.endswith("]]"):
        target = target[2:-2]
    target = target.split("|", 1)[0].strip()
    if target.endswith(".md"):
        target = target[:-3]
    return target


def _description_for(name: str) -> str:
    descriptions = getattr(moc_map, "MOC_DESCRIPTIONS", {})
    if isinstance(descriptions, dict):
        value = descriptions.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Hub note — target of `up: [[{name}]]` links."


def _context_for(vault: Path) -> str:
    if vault.name == "Business":
        return "work"
    return "personal"


if __name__ == "__main__":
    raise SystemExit(main())
