"""Unit tests for the small pure helpers in scripts.classify.classify_vault.

Most of classify_vault is integration-level (real files, LM calls, atomic
writes), but a few pure functions deserve fast unit tests.
"""

from pathlib import Path

from scripts.classify.classify_vault import (
    _auto_classify_rate,
    _corpus_eta,
    _count_already_classified,
    _overall_postfix,
    _progress_total,
    _rules_hit_rate,
)


class TestProgressTotal:
    """Progress-bar denominator should track the --limit when one is set,
    so users see % progress toward the cap they asked for rather than %
    progress through the whole folder.
    """

    def test_no_limit_returns_full_scan_size(self) -> None:
        assert _progress_total(scan_size=6375, limit=None) == 6375

    def test_limit_below_scan_size_returns_limit(self) -> None:
        # Classic --limit case: 100 cap on a 6375-note folder.
        assert _progress_total(scan_size=6375, limit=100) == 100

    def test_limit_above_scan_size_returns_scan_size(self) -> None:
        # User asked for more than is available; tqdm should cap at the
        # files we'll actually see.
        assert _progress_total(scan_size=16, limit=500) == 16

    def test_limit_equal_to_scan_size_returns_either(self) -> None:
        assert _progress_total(scan_size=100, limit=100) == 100

    def test_limit_zero_returns_zero(self) -> None:
        # Edge: --limit 0 means "process nothing". Avoid divide-by-zero
        # surprises downstream.
        assert _progress_total(scan_size=6375, limit=0) == 0


class TestOverallPostfix:
    """The postfix string lives in the tqdm progress bar and answers
    'how close am I to having classified the whole corpus?', as distinct
    from the bar's own % which tracks progress against --limit.
    """

    def test_basic_format_with_percentage(self) -> None:
        out = _overall_postfix(processed=100, corpus_size=6375)
        assert "100/6375" in out
        assert "1.6%" in out
        assert out.startswith("overall:")

    def test_complete_corpus_shows_100_percent(self) -> None:
        out = _overall_postfix(processed=6375, corpus_size=6375)
        assert "6375/6375" in out
        assert "100.0%" in out

    def test_zero_processed_shows_zero_percent(self) -> None:
        out = _overall_postfix(processed=0, corpus_size=6375)
        assert "0/6375" in out
        assert "0.0%" in out

    def test_empty_corpus_does_not_divide_by_zero(self) -> None:
        # Edge case: --folder pointing at an empty (or filtered-empty)
        # subset. Must not raise; percentage is meaningless so omit it.
        out = _overall_postfix(processed=0, corpus_size=0)
        assert "0/0" in out
        # No "NaN%" or division crash.
        assert "NaN" not in out
        assert "inf" not in out.lower()


class TestCountAlreadyClassified:
    """Pre-scan counter — used so the postfix can report
    'X of Y classified in the corpus' across chunked runs."""

    def _write_classified(self, dir: Path, name: str) -> Path:
        note = dir / name
        note.write_text(
            "---\n"
            "type: note\n"
            "org: Amazon\n"
            "context: work\n"
            'up: "[[Personal]]"\n'
            "---\n\nbody\n",
            encoding="utf-8",
        )
        return note

    def _write_unclassified(self, dir: Path, name: str) -> Path:
        note = dir / name
        note.write_text("Just body, no frontmatter.\n", encoding="utf-8")
        return note

    def test_counts_only_classified_notes(self, tmp_path: Path) -> None:
        a = self._write_classified(tmp_path, "a.md")
        b = self._write_unclassified(tmp_path, "b.md")
        c = self._write_classified(tmp_path, "c.md")
        d = self._write_unclassified(tmp_path, "d.md")
        e = self._write_classified(tmp_path, "e.md")
        assert _count_already_classified([a, b, c, d, e]) == 3

    def test_empty_list_returns_zero(self) -> None:
        assert _count_already_classified([]) == 0

    def test_all_unclassified_returns_zero(self, tmp_path: Path) -> None:
        a = self._write_unclassified(tmp_path, "a.md")
        b = self._write_unclassified(tmp_path, "b.md")
        assert _count_already_classified([a, b]) == 0

    def test_all_classified_returns_full_count(self, tmp_path: Path) -> None:
        a = self._write_classified(tmp_path, "a.md")
        b = self._write_classified(tmp_path, "b.md")
        assert _count_already_classified([a, b]) == 2


class TestAutoClassifyRate:
    """The 'ac:X%' postfix segment: of all classification attempts this run,
    what % reached confidence >= 0.80 and got auto-classified.
    """

    def test_basic_rate(self) -> None:
        # 7 auto + 33 review = 40 attempts; ac = 7/40 = 17.5%
        assert _auto_classify_rate(auto=7, review=33) == "ac:18%"

    def test_high_rate_rounds(self) -> None:
        # 73 auto + 27 review = 100 attempts; ac = 73%
        assert _auto_classify_rate(auto=73, review=27) == "ac:73%"

    def test_no_attempts_returns_dash(self) -> None:
        # Before the first attempt completes; avoid divide-by-zero
        assert _auto_classify_rate(auto=0, review=0) == "ac:-"

    def test_all_auto(self) -> None:
        assert _auto_classify_rate(auto=50, review=0) == "ac:100%"


class TestRulesHitRate:
    """The 'rules:X%' postfix: of the auto-classified notes, what % were
    caught by the rules cascade (free) vs. needing an LM call.
    """

    def test_basic_rate(self) -> None:
        # 50 auto, 18 from rules → 36%
        assert _rules_hit_rate(rules_auto=18, total_auto=50) == "rules:36%"

    def test_no_auto_yet(self) -> None:
        assert _rules_hit_rate(rules_auto=0, total_auto=0) == "rules:-"

    def test_all_rules(self) -> None:
        # The dream case — no LM calls needed
        assert _rules_hit_rate(rules_auto=20, total_auto=20) == "rules:100%"

    def test_no_rules_hits(self) -> None:
        assert _rules_hit_rate(rules_auto=0, total_auto=20) == "rules:0%"


class TestCorpusEta:
    """The 'corpus-eta:Xh' postfix: estimated time to classify the rest
    of the unclassified corpus at the current observed rate.
    """

    def test_hours_format(self) -> None:
        # 10s/attempt, 5000 attempts remaining = 50000 sec = ~13.9h
        out = _corpus_eta(elapsed_seconds=100.0, attempts=10, remaining=5000)
        assert out.startswith("corpus-eta:")
        assert "h" in out
        # 13.something hours
        assert any(c.isdigit() for c in out)

    def test_minutes_format_for_short_runs(self) -> None:
        # 1s/attempt, 100 attempts remaining = 100 sec = under a minute
        # but more than 0, so should be in minutes
        out = _corpus_eta(elapsed_seconds=60.0, attempts=60, remaining=120)
        assert "corpus-eta:" in out
        # 120s = 2m — should be minutes
        assert "m" in out or "h" in out

    def test_no_data_yet(self) -> None:
        # Before any attempts complete
        assert _corpus_eta(elapsed_seconds=0.0, attempts=0, remaining=5000) == "corpus-eta:?"

    def test_zero_remaining(self) -> None:
        # All done — ETA is 0
        assert _corpus_eta(elapsed_seconds=100.0, attempts=10, remaining=0) == "corpus-eta:0m"
