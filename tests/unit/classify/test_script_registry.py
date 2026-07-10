"""Unit tests for scripts.classify.script_registry.

The registry is the security boundary for the control panel: the panel can
ONLY run scripts that appear here, addressed by `key` — never an arbitrary
command string. So the registry's integrity (unique keys, real script
paths, required metadata) is load-bearing.
"""

from __future__ import annotations

import pytest

from scripts.classify import script_registry as reg


class TestRegistryShape:
    def test_every_entry_has_required_keys(self):
        required = {"key", "name", "use_case", "tier", "interpreter", "cwd", "argv"}
        for entry in reg.SCRIPTS:
            # 'link' tier entries are display-only and may omit run fields.
            if entry["tier"] == "link":
                assert {"key", "name", "use_case", "tier"} <= entry.keys()
                continue
            missing = required - entry.keys()
            assert not missing, f"{entry.get('key')} missing keys: {missing}"

    def test_keys_are_unique(self):
        keys = [e["key"] for e in reg.SCRIPTS]
        assert len(keys) == len(set(keys)), "duplicate registry keys"

    def test_tiers_are_known_values(self):
        allowed = {"daily", "occasional", "done", "link"}
        for e in reg.SCRIPTS:
            assert e["tier"] in allowed, f"{e['key']} has bad tier {e['tier']}"

    def test_runnable_entries_point_at_existing_scripts(self):
        # argv[0] resolved against cwd must be a real file on disc.
        from pathlib import Path
        for e in reg.SCRIPTS:
            if e["tier"] == "link":
                continue
            script = Path(e["cwd"]) / e["argv"][0]
            assert script.exists(), f"{e['key']}: script not found at {script}"

    def test_runnable_entries_have_existing_interpreter(self):
        from pathlib import Path
        for e in reg.SCRIPTS:
            if e["tier"] == "link":
                continue
            assert Path(e["interpreter"]).exists(), (
                f"{e['key']}: interpreter not found at {e['interpreter']}"
            )


class TestValidateRegistry:
    def test_passes_on_real_registry(self):
        # Should not raise.
        reg.validate_registry(reg.SCRIPTS)

    def test_raises_on_duplicate_keys(self):
        bad = [
            {"key": "x", "name": "X", "use_case": "u", "tier": "link"},
            {"key": "x", "name": "Y", "use_case": "u", "tier": "link"},
        ]
        with pytest.raises(ValueError, match="duplicate"):
            reg.validate_registry(bad)

    def test_raises_on_missing_key_field(self):
        bad = [{"name": "X", "use_case": "u", "tier": "link"}]
        with pytest.raises(ValueError):
            reg.validate_registry(bad)

    def test_raises_on_unknown_tier(self):
        bad = [{"key": "x", "name": "X", "use_case": "u", "tier": "bogus"}]
        with pytest.raises(ValueError, match="tier"):
            reg.validate_registry(bad)

    def test_raises_when_runnable_script_missing(self, tmp_path):
        # In-repo missing script must raise (external ones are tolerated — see
        # TestExternalScriptTolerance). Use the repo root as cwd.
        bad = [{
            "key": "x", "name": "X", "use_case": "u", "tier": "daily",
            "interpreter": "/usr/bin/python3",
            "cwd": str(reg._REPO_ROOT),
            "argv": ["scripts/classify/does_not_exist.py"],
        }]
        with pytest.raises(ValueError, match="not found|missing"):
            reg.validate_registry(bad)


class TestServerEntry:
    def test_review_server_is_a_runnable_server(self):
        from pathlib import Path
        e = reg.get("review-server")
        assert e.get("kind") == "server"
        assert e.get("url")
        for f in ("interpreter", "cwd", "argv"):
            assert f in e, f"server entry missing {f}"
        assert (Path(e["cwd"]) / e["argv"][0]).exists()

    def test_validate_rejects_server_missing_url(self, tmp_path):
        bad = [{
            "key": "s", "name": "S", "use_case": "u", "tier": "link",
            "kind": "server", "interpreter": "/usr/bin/python3",
            "cwd": str(tmp_path), "argv": ["x.py"],
        }]
        with pytest.raises(ValueError, match="url|missing"):
            reg.validate_registry(bad)


class TestByTier:
    def test_groups_entries_by_tier(self):
        grouped = reg.by_tier()
        assert set(grouped.keys()) <= {"daily", "occasional", "done", "link"}
        flat = [e for entries in grouped.values() for e in entries]
        assert len(flat) == len(reg.SCRIPTS)

    def test_tier_order_daily_first_done_last(self):
        grouped = reg.by_tier()
        order = list(grouped.keys())
        # daily must come before occasional, done, link
        if "daily" in order and "done" in order:
            assert order.index("daily") < order.index("done")

    def test_lookup_by_key_returns_entry(self):
        # There must be a way to resolve a key to its entry for POST /run.
        entry = reg.get("audit-manifest")
        assert entry["key"] == "audit-manifest"

    def test_lookup_unknown_key_raises(self):
        with pytest.raises(KeyError):
            reg.get("no-such-key")


class TestExternalScriptTolerance:
    """Scripts outside the repo (e.g. the granolaSync sibling) are environment-

    dependent — the registry can't guarantee they exist, so their absence must
    NOT crash the import-time validation. In-repo scripts are still required.
    """

    def _entry(self, cwd: str, script: str) -> dict:
        return {
            "key": "probe", "name": "Probe", "use_case": "test", "tier": "daily",
            "interpreter": "python", "cwd": cwd, "argv": [script],
        }

    def test_missing_external_script_does_not_raise(self):
        entry = self._entry("/definitely/not/a/repo/path", "ghost.py")
        reg.validate_registry([entry])  # must not raise

    def test_missing_in_repo_script_still_raises(self):
        entry = self._entry(str(reg._REPO_ROOT), "scripts/classify/does_not_exist.py")
        with pytest.raises(ValueError, match="script not found"):
            reg.validate_registry([entry])
