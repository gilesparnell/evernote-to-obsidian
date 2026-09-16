"""One-off backfill: re-open already-exported Granola notes for classification.

granolaSync writes complete-looking R2 frontmatter (`type: meeting`,
`context: work`) on every note it exports. Those are hardcoded guesses — right
for a calendar meeting, wrong for the solo recordings that make up most of the
corpus. Because all four required fields were present, ``is_classified()``
treated them as settled and the LM classifier never revisited them, freezing
notes like "Bed Linen for the Family" as work meetings.

The exporter now stamps ``classified_by: export`` so new notes stay open. This
script does the same for the notes already on disk, which carry no provenance
at all. Stamping them makes the next nightly run pick them up.

Notes the classifier has already claimed (``classified_by: classifier``) are
left alone, so re-running never undoes real work.

    python -m scripts.classify.mark_granola_provisional --vault ~/…/Personal --dry-run
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from scripts.classify import frontmatter as _fm

# Operator-curated tree on a different schema — never touch it. Mirrors
# classify_vault._SKIP_TOP_LEVEL_EXACT.
_SKIP_TOP_LEVEL: frozenset[str] = frozenset({"wiki"})

# Both vaults are iCloud-synced; an unpaced burst of writes is what this
# throttle exists to prevent. Matches classify_vault.ICLOUD_SLEEP_SECONDS.
ICLOUD_SLEEP_SECONDS = 0.05


def _is_skipped(path: Path, vault: Path) -> bool:
    try:
        first = path.relative_to(vault).parts[0]
    except (ValueError, IndexError):
        return False
    return first in _SKIP_TOP_LEVEL


def mark_granola_provisional(vault: Path, *, dry_run: bool = False) -> list[Path]:
    """Stamp `classified_by: export` on unmarked Granola exports.

    A note qualifies when it carries a ``granola_id`` (so it came from the
    exporter) and has no ``classified_by`` yet. Returns the paths changed —
    or that would change, under ``dry_run``.
    """
    changed: list[Path] = []
    for path in sorted(vault.rglob("*.md")):
        if _is_skipped(path, vault):
            continue
        try:
            fm = _fm.read_frontmatter(path)
        except OSError:
            continue
        if not fm.get("granola_id") or fm.get("classified_by"):
            continue
        changed.append(path)
        if not dry_run:
            _fm.write_frontmatter(
                path, {"classified_by": _fm.PROVISIONAL_PROVENANCE}
            )
            time.sleep(ICLOUD_SLEEP_SECONDS)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    changed = mark_granola_provisional(args.vault, dry_run=args.dry_run)
    verb = "would re-open" if args.dry_run else "re-opened"
    print(f"{verb} {len(changed)} Granola note(s) in {args.vault}")
    for path in changed:
        print(f"  {path.relative_to(args.vault)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
