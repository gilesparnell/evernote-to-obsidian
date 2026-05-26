"""Unit tests for scripts.classify.audit_manifest.

After every classifier chunk, the operator audits .classify_deleted_manifest.json
to confirm nothing important got hard-deleted. This module formats the manifest
into a human-readable report so the operator doesn't have to write ad-hoc heredoc
python every time.

Defaults to showing only the most recent run's deletions — that's what the
post-chunk operator checklist always wants. --all-runs to override.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.classify.audit_manifest import (
    audit,
    entries_for_run,
    format_entry,
    latest_run_id,
    load_manifest,
)


# ---------------------------------------------------------------------------
# Fixtures


def _write_manifest(vault: Path, entries: list[dict]) -> Path:
    p = vault / ".classify_deleted_manifest.json"
    p.write_text(json.dumps({"deleted": entries}, indent=2), encoding="utf-8")
    return p


def _entry(
    path: str = "Evernote/notes/AWS/foo.md",
    chars: int = 10,
    preview: str = "some body",
    run_id: str = "2026-05-26T19:37:02+10:00",
    deleted_at: str = "2026-05-26T19:37:15+10:00",
) -> dict:
    return {
        "path": path,
        "stripped_body_chars": chars,
        "body_preview": preview,
        "deleted_at_aest": deleted_at,
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# load_manifest


class TestLoadManifest:
    def test_returns_dict_when_manifest_exists(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, [_entry()])
        d = load_manifest(tmp_path)
        assert d is not None
        assert d["deleted"][0]["path"].endswith("foo.md")

    def test_returns_none_when_manifest_missing(self, tmp_path: Path) -> None:
        # Fresh vault that has never had a classifier run with purges.
        assert load_manifest(tmp_path) is None

    def test_raises_clear_error_on_corrupt_json(self, tmp_path: Path) -> None:
        (tmp_path / ".classify_deleted_manifest.json").write_text(
            "not valid json {{{", encoding="utf-8",
        )
        with pytest.raises(json.JSONDecodeError):
            load_manifest(tmp_path)


# ---------------------------------------------------------------------------
# latest_run_id


class TestLatestRunId:
    def test_returns_max_iso_timestamp(self) -> None:
        deleted = [
            _entry(run_id="2026-05-26T19:37:02+10:00"),
            _entry(run_id="2026-05-26T23:46:10+10:00"),
            _entry(run_id="2026-05-25T08:00:00+10:00"),
        ]
        assert latest_run_id(deleted) == "2026-05-26T23:46:10+10:00"

    def test_returns_none_for_empty_deleted_list(self) -> None:
        assert latest_run_id([]) is None

    def test_handles_single_entry(self) -> None:
        deleted = [_entry(run_id="2026-05-26T19:37:02+10:00")]
        assert latest_run_id(deleted) == "2026-05-26T19:37:02+10:00"


# ---------------------------------------------------------------------------
# entries_for_run


class TestEntriesForRun:
    def test_returns_only_matching_run_id(self) -> None:
        a = _entry(path="a.md", run_id="run-1")
        b = _entry(path="b.md", run_id="run-2")
        c = _entry(path="c.md", run_id="run-1")
        out = entries_for_run([a, b, c], "run-1")
        assert out == [a, c]

    def test_returns_empty_for_unknown_run_id(self) -> None:
        out = entries_for_run([_entry(run_id="run-1")], "run-missing")
        assert out == []

    def test_preserves_order(self) -> None:
        # Manifest grows append-only — preserving order keeps the report
        # in deletion order for that run.
        entries = [
            _entry(path=f"f{i}.md", run_id="run-1")
            for i in range(5)
        ]
        out = entries_for_run(entries, "run-1")
        assert [e["path"] for e in out] == [f"f{i}.md" for i in range(5)]


# ---------------------------------------------------------------------------
# format_entry


class TestFormatEntry:
    def test_includes_index_chars_filename_and_preview(self) -> None:
        out = format_entry(1, _entry(
            path="Evernote/notes/AWS/Note.13.md",
            chars=11,
            preview="Bread rolls",
        ))
        assert "1." in out
        assert "11 chars" in out
        assert "Note.13.md" in out
        assert "Bread rolls" in out

    def test_uses_basename_not_full_path(self) -> None:
        out = format_entry(1, _entry(path="a/deeply/nested/file.md"))
        assert "file.md" in out
        assert "deeply/nested" not in out

    def test_truncates_filename_at_55_chars(self) -> None:
        long_name = "x" * 80 + ".md"
        out = format_entry(1, _entry(path=long_name))
        # Truncated, never wrapped
        lines = out.split("\n")
        assert all(len(line) <= 200 for line in lines)
        # The filename portion is bounded
        assert "x" * 60 not in out

    def test_pads_index_for_alignment(self) -> None:
        # Two-digit and three-digit indices should align with right-padding.
        a = format_entry(1, _entry())
        b = format_entry(135, _entry())
        # Both indices should occupy the same column width
        assert a.index("[") == b.index("[")


# ---------------------------------------------------------------------------
# audit (top-level)


class TestAudit:
    def test_handles_missing_manifest_gracefully(self, tmp_path: Path) -> None:
        # Fresh vault, no manifest yet. Don't crash — say so clearly.
        out = audit(tmp_path, last_run_only=True, limit=None)
        assert "no manifest" in out.lower() or "no deletions" in out.lower()

    def test_last_run_only_filters_to_most_recent(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, [
            _entry(path="old.md", run_id="2026-05-26T19:37:02+10:00"),
            _entry(path="new1.md", run_id="2026-05-26T23:46:10+10:00"),
            _entry(path="new2.md", run_id="2026-05-26T23:46:10+10:00"),
        ])
        out = audit(tmp_path, last_run_only=True, limit=None)
        assert "new1.md" in out
        assert "new2.md" in out
        assert "old.md" not in out

    def test_all_runs_shows_total_and_per_run_breakdown(
        self, tmp_path: Path,
    ) -> None:
        _write_manifest(tmp_path, [
            _entry(path="a.md", run_id="2026-05-26T19:37:02+10:00"),
            _entry(path="b.md", run_id="2026-05-26T23:46:10+10:00"),
            _entry(path="c.md", run_id="2026-05-26T23:46:10+10:00"),
        ])
        out = audit(tmp_path, last_run_only=False, limit=None)
        assert "3" in out  # total
        assert "a.md" in out
        assert "b.md" in out
        assert "c.md" in out

    def test_limit_caps_output_count(self, tmp_path: Path) -> None:
        # Useful when the manifest grows large — operator wants a sample.
        _write_manifest(tmp_path, [
            _entry(path=f"f{i}.md", run_id="2026-05-26T19:37:02+10:00")
            for i in range(20)
        ])
        out = audit(tmp_path, last_run_only=True, limit=5)
        # Counts: first 5 filenames present, the rest not
        assert "f0.md" in out
        assert "f4.md" in out
        assert "f10.md" not in out

    def test_includes_total_count_in_summary_line(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, [
            _entry(path=f"f{i}.md", run_id="2026-05-26T23:46:10+10:00")
            for i in range(135)
        ])
        out = audit(tmp_path, last_run_only=True, limit=None)
        assert "135" in out

    def test_empty_deletions_returns_helpful_message(
        self, tmp_path: Path,
    ) -> None:
        _write_manifest(tmp_path, [])  # legal but empty
        out = audit(tmp_path, last_run_only=True, limit=None)
        assert "no deletions" in out.lower() or "0 purged" in out.lower()
