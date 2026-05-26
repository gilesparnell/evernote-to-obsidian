"""Unit tests for scripts.classify.moc_map.

UP_MAP and up_for_type live in their own module so consumers that only
need the wikilink lookup (the review server, migrate tools, future
utilities) don't transitively pull in the LM SDK from classify_vault's
dependency chain. The tests here lock in the export contract.
"""

from scripts.classify.moc_map import UP_MAP, up_for_type


class TestUpMap:
    def test_meeting_maps_to_meetings_moc(self) -> None:
        assert UP_MAP["meeting"] == "[[Meetings]]"

    def test_technical_maps_to_technical_moc(self) -> None:
        assert UP_MAP["technical"] == "[[Technical]]"

    def test_interview_maps_to_interview_prep(self) -> None:
        assert UP_MAP["interview"] == "[[Interview Prep]]"

    def test_management_maps_to_leadership(self) -> None:
        assert UP_MAP["management"] == "[[Leadership]]"

    def test_application_maps_to_job_hunt(self) -> None:
        assert UP_MAP["application"] == "[[Job Hunt]]"

    def test_clipping_maps_to_clippings_moc(self) -> None:
        # Plan 2026-05-26-001 — body-shape rules emit type='clipping' for
        # single-image / single-URL / embed-only Evernote import artefacts.
        # New MOC keeps them separate from operator-authored references.
        assert UP_MAP["clipping"] == "[[Clippings]]"


class TestUpForType:
    def test_known_type_returns_mapped_moc(self) -> None:
        assert up_for_type("meeting") == "[[Meetings]]"
        assert up_for_type("technical") == "[[Technical]]"

    def test_unknown_type_falls_back_to_personal(self) -> None:
        assert up_for_type("nonexistent_type_xyz") == "[[Personal]]"

    def test_empty_string_falls_back_to_personal(self) -> None:
        assert up_for_type("") == "[[Personal]]"
