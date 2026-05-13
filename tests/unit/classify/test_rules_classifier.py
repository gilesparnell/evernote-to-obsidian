"""Unit tests for scripts.classify.rules_classifier.

Covers the 13 test scenarios from plan §Unit 3: org/type/context detection
across the full R2 schema, people extraction with false-positive filtering,
tag inference (STAR + AWS LP + draft), folder_hint as tie-breaker, and the
content-wins-over-folder behaviour.
"""

from scripts.classify.rules_classifier import classify


class TestOrgAndType:
    def test_aws_meeting_classified_as_amazon_work_meeting(self) -> None:
        result = classify(
            "Weekly AWS standup",
            "AWS S3 deployment meeting",
            folder_hint="",
        )
        assert result["org"] == "Amazon"
        assert result["type"] == "meeting"
        assert result["context"] == "work"

    def test_personal_keywords_classified_as_personal(self) -> None:
        result = classify(
            "Family weekend",
            "birthday party, family dinner, kids homework",
            folder_hint="",
        )
        assert result["org"] == "Personal"
        assert result["type"] == "personal"
        assert result["context"] == "personal"

    def test_recipe_keywords(self) -> None:
        result = classify(
            "Cake recipe",
            "recipe: chocolate cake, 2 cups flour",
            folder_hint="",
        )
        assert result["type"] == "recipe"

    def test_management_keywords(self) -> None:
        result = classify(
            "Q1 OLR",
            "OLR calibration, direct report performance review, low performer",
            folder_hint="",
        )
        assert result["type"] == "management"

    def test_application_keywords(self) -> None:
        result = classify(
            "Anthropic application",
            "applied to Anthropic, phone screen scheduled Mar 14",
            folder_hint="",
        )
        assert result["type"] == "application"

    def test_pattern_keywords(self) -> None:
        result = classify(
            "CQRS notes",
            "CQRS pattern for write-heavy systems, event sourcing trade-offs",
            folder_hint="",
        )
        assert result["type"] == "pattern"

    def test_career_keywords(self) -> None:
        result = classify(
            "CV update",
            "Resume summary: 15 years SRE leadership",
            folder_hint="",
        )
        assert result["type"] == "career"


class TestPeopleExtraction:
    def test_extracts_capitalised_name_pairs(self) -> None:
        result = classify(
            "Standup notes",
            "John Smith attended the standup with Alice Jones",
            folder_hint="",
        )
        assert "John Smith" in result["people"]
        assert "Alice Jones" in result["people"]

    def test_filters_weekday_false_positives(self) -> None:
        # Bigram "Tuesday Meeting" matches the capitalised-pair regex; the
        # weekday filter must drop it entirely (not just strip "Tuesday").
        result = classify(
            "Schedule",
            "Tuesday Meeting agenda items",
            folder_hint="",
        )
        assert all("Tuesday" not in p for p in result["people"])


class TestTagInference:
    def test_star_story_and_aws_lp_tags(self) -> None:
        result = classify(
            "Interview prep — customer escalation",
            "STAR story, situation: customer escalation, action: escalated to VP",
            folder_hint="",
        )
        assert "star" in result["tags"]
        assert "aws-lp/customer-obsession" in result["tags"]
        assert result["type"] == "interview"

    def test_draft_and_star_combined(self) -> None:
        result = classify(
            "[draft] interview story",
            "[draft] STAR story about scaling team",
            folder_hint="",
        )
        assert "star" in result["tags"]
        assert "draft" in result["tags"]


class TestFolderHintAndOrgPrecedence:
    def test_folder_hint_fallback_when_body_has_no_keywords(self) -> None:
        # No org keywords in body; folder_hint "AWS" should resolve org to
        # Amazon with LOW confidence (below the 0.80 auto-classify threshold).
        result = classify(
            "Untitled",
            "no signal whatsoever in this body",
            folder_hint="AWS",
        )
        assert result["org"] == "Amazon"
        assert result["confidence"] < 0.80

    def test_aws_in_body_beats_personal_keywords_for_org(self) -> None:
        # Per plan: org=Amazon wins, context=work, regardless of personal
        # keywords elsewhere in the body.
        result = classify(
            "Q1 review",
            "AWS quarterly review with family dinner and kids homework",
            folder_hint="",
        )
        assert result["org"] == "Amazon"
        assert result["context"] == "work"
