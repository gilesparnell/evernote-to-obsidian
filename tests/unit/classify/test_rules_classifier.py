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


class TestTitleTypeShortcuts:
    """Title-pattern rules that fire on the note's filename pattern.

    Without these, AWS-folder notes whose body has no org/type keywords
    fall to the LM cascade at ~7 sec/call. With them, notes like
    '1-1 With Rob.md' auto-classify in milliseconds.
    """

    def test_one_on_one_dash_separator_is_meeting(self) -> None:
        result = classify("1-1 With Rob Kennedy", "", folder_hint="")
        assert result["type"] == "meeting"

    def test_one_on_one_colon_separator_is_meeting(self) -> None:
        result = classify("1:1 Stefan", "", folder_hint="")
        assert result["type"] == "meeting"

    def test_one_on_one_underscore_separator_is_meeting(self) -> None:
        # Real example from the vault: '1-1_ Mike Roz.md'
        result = classify("1-1_ Mike Roz", "", folder_hint="")
        assert result["type"] == "meeting"

    def test_one_on_one_with_no_separator_is_meeting(self) -> None:
        # Some titles render as '1 1 Pete' after Evernote export
        result = classify("1 1 Pete Stanski", "", folder_hint="")
        assert result["type"] == "meeting"

    def test_standup_title_is_meeting(self) -> None:
        result = classify("Standup notes 2024-Q2", "", folder_hint="")
        assert result["type"] == "meeting"

    def test_weekly_sync_title_is_meeting(self) -> None:
        result = classify("Weekly sync - APAC team", "", folder_hint="")
        assert result["type"] == "meeting"

    def test_daily_standup_title_is_meeting(self) -> None:
        result = classify("Daily standup notes", "", folder_hint="")
        assert result["type"] == "meeting"

    def test_olr_title_is_management(self) -> None:
        result = classify("OLR feedback - Q3", "", folder_hint="")
        assert result["type"] == "management"

    def test_pip_title_is_management(self) -> None:
        result = classify("PIP discussion notes", "", folder_hint="")
        assert result["type"] == "management"

    def test_performance_review_title_is_management(self) -> None:
        result = classify("Performance Review - 2024", "", folder_hint="")
        assert result["type"] == "management"

    def test_calibration_title_is_management(self) -> None:
        # Real example: '2024 NSS Q1 Calibration.md'
        result = classify("2024 NSS Q1 Calibration", "", folder_hint="")
        assert result["type"] == "management"

    def test_h1_goals_title_is_management(self) -> None:
        result = classify("H1 Goals 2024", "", folder_hint="")
        assert result["type"] == "management"

    def test_goal_tracker_title_is_management(self) -> None:
        # Real example: '2016 APAC Goal Tracker - 30 May v2.md'
        result = classify("2016 APAC Goal Tracker", "", folder_hint="")
        assert result["type"] == "management"

    def test_interview_title_is_interview(self) -> None:
        result = classify("Interview with X candidate", "", folder_hint="")
        assert result["type"] == "interview"

    def test_phone_screen_title_is_interview(self) -> None:
        result = classify("Phone screen - Senior SA role", "", folder_hint="")
        assert result["type"] == "interview"

    def test_reinvent_title_is_reference(self) -> None:
        result = classify("re:Invent 2023 - container sessions", "", folder_hint="")
        assert result["type"] == "reference"

    def test_summit_title_is_reference(self) -> None:
        # Real example: '2016 Summit_ containers.md'
        result = classify("2016 Summit_ containers", "", folder_hint="")
        assert result["type"] == "reference"

    def test_random_title_does_not_match_any_rule(self) -> None:
        """Falls through to keyword scoring (current behaviour)."""
        result = classify("Some random project notes", "", folder_hint="")
        # type still gets assigned (defaults to note/personal) but the
        # confidence should NOT be boosted by a title rule.
        assert result["type"] in ("note", "personal")
        assert result["confidence"] < 0.80

    def test_case_insensitive_match(self) -> None:
        result = classify("1-1 WITH SOMEONE", "", folder_hint="")
        assert result["type"] == "meeting"


class TestTitleRulePlusFolderHintAutoClassifies:
    """The combined unlock: AWS-folder 1-1 notes hit confidence >= 0.80
    via folder-hint org boost + title-rule type signal, avoiding the LM.
    """

    def test_one_on_one_in_aws_folder_auto_classifies(self) -> None:
        result = classify("1-1 With Rob Kennedy", "", folder_hint="AWS")
        assert result["type"] == "meeting"
        assert result["org"] == "Amazon"
        assert result["confidence"] >= 0.80, (
            f"Expected confidence >= 0.80, got {result['confidence']:.2f}. "
            "The rules cascade should catch this without an LM call."
        )

    def test_olr_in_aws_folder_auto_classifies(self) -> None:
        result = classify("OLR for direct report", "", folder_hint="AWS")
        assert result["type"] == "management"
        assert result["org"] == "Amazon"
        assert result["confidence"] >= 0.80

    def test_summit_in_aws_folder_auto_classifies(self) -> None:
        result = classify("2016 Summit_ containers", "", folder_hint="AWS")
        assert result["type"] == "reference"
        assert result["org"] == "Amazon"
        assert result["confidence"] >= 0.80

    def test_one_on_one_in_tsystems_folder_routes_to_t_systems(self) -> None:
        result = classify("1-1 With Klaus", "", folder_hint="T-Systems")
        assert result["type"] == "meeting"
        assert result["org"] == "T-Systems"
        assert result["confidence"] >= 0.80

    def test_one_on_one_in_tsc_folder_routes_to_tsc(self) -> None:
        result = classify("1-1 With Adrian", "", folder_hint="TSC")
        assert result["type"] == "meeting"
        assert result["org"] == "TSC"
        assert result["confidence"] >= 0.80

    def test_title_rule_wins_over_competing_keywords(self) -> None:
        """1-1 title beats body keywords pointing to other types — the title
        signal is a stronger intent indicator than scattered body keywords.
        """
        result = classify(
            "1-1 With Engineering Lead",
            "Discussed deployment, pull request, code review for the schema",
            folder_hint="AWS",
        )
        # Body alone would score: technical=3 (deployment, pull request, schema)
        # But title rule overrides → meeting
        assert result["type"] == "meeting"
        assert result["confidence"] >= 0.80


class TestMinKeywordScoreGate:
    """A single generic keyword match shouldn't auto-classify.

    Without this gate, a note titled '39 Mountain Drive Alarm' lands in
    [[Interview Prep]] because its body happens to contain one interview
    keyword (e.g. 'demonstrate' or 'strength'). False positives like this
    pollute the MOCs; better to send the note to the LM where it can
    decide based on actual context.
    """

    def test_single_keyword_match_drops_confidence_below_threshold(self) -> None:
        # A non-interview note with exactly one generic interview keyword
        # ('demonstrate') should NOT auto-classify as interview.
        result = classify(
            "API Gateway Demo",
            "We'll demonstrate the new flow at the team meeting",
            folder_hint="AWS",
        )
        # Either type is something other than interview, OR confidence < 0.80.
        if result["type"] == "interview":
            assert result["confidence"] < 0.80, (
                f"Single keyword 'demonstrate' shouldn't auto-classify as "
                f"interview. Got confidence {result['confidence']:.2f}."
            )

    def test_two_or_more_keyword_matches_can_auto_classify(self) -> None:
        # Multiple genuine interview keywords → strong signal, auto-classify.
        # Title is deliberately neutral so we exercise the keyword-scoring
        # path, not the title-rule shortcut. AWS folder gives org confidence.
        result = classify(
            "Discussion notes",
            "STAR story: tell me about a time. Competency-based behavioural question.",
            folder_hint="AWS",
        )
        assert result["type"] == "interview"
        assert result["confidence"] >= 0.80

    def test_title_rule_bypasses_min_score_gate(self) -> None:
        # Title rules are inherently strong signals; they bypass the
        # min-keyword-score requirement.
        result = classify(
            "1-1 Stefan",
            "We'll demonstrate the new flow",
            folder_hint="AWS",
        )
        assert result["type"] == "meeting"
        assert result["confidence"] >= 0.80

    def test_single_career_keyword_drops_below_threshold(self) -> None:
        # 'credentials' is a career keyword but appears constantly in AWS
        # technical notes (security credentials, AWS credentials, etc.).
        result = classify(
            "AWS Service Credentials and Settings",
            "Configure your AWS credentials in the CLI",
            folder_hint="AWS",
        )
        # Either it's NOT typed career, or confidence is below threshold.
        if result["type"] == "career":
            assert result["confidence"] < 0.80


class TestTitleRulesUnderscoreBoundary:
    """Evernote export uses underscores in titles where the original had
    a colon or space (e.g. 'Interview: Foo' → 'Interview_ Foo'). Our title
    regexes must match across the underscore, not stop at it.
    """

    def test_interview_with_underscore_separator_matches(self) -> None:
        # Real example: '80 Interview_ candidate name.md' (most common pattern)
        result = classify("Interview_ Senior SA", "", folder_hint="AWS")
        assert result["type"] == "interview"
        assert result["confidence"] >= 0.80

    def test_phone_screen_with_underscore_matches(self) -> None:
        result = classify("Phone screen_ Jane Doe", "", folder_hint="AWS")
        assert result["type"] == "interview"
        assert result["confidence"] >= 0.80


class TestAdditionalTitleRules:
    """Patterns discovered from analysis of 6,048 unclassified AWS titles."""

    def test_roadmap_title_is_reference(self) -> None:
        result = classify("Roadmap H2 2024", "", folder_hint="AWS")
        assert result["type"] == "reference"
        assert result["confidence"] >= 0.80

    def test_roadmap_underscore_title_is_reference(self) -> None:
        result = classify("Roadmap_ EC2 networking", "", folder_hint="AWS")
        assert result["type"] == "reference"

    def test_screenshot_title_is_reference(self) -> None:
        # 160 of these in the unclassified set — auto-captured screenshots
        # from Evernote, typically a reference snapshot.
        result = classify("Screenshot 2018-04-15 at 14.23.png", "", folder_hint="AWS")
        assert result["type"] == "reference"

    def test_sprint_title_is_meeting(self) -> None:
        result = classify("Sprint planning notes", "", folder_hint="AWS")
        assert result["type"] == "meeting"

    def test_sprint_underscore_title_is_meeting(self) -> None:
        result = classify("Sprint_ team review", "", folder_hint="AWS")
        assert result["type"] == "meeting"

    def test_sko_title_is_reference(self) -> None:
        # Sales Kick-Off — annual reference event
        result = classify("SKO 2023 notes", "", folder_hint="AWS")
        assert result["type"] == "reference"

    def test_yearly_title_is_management(self) -> None:
        result = classify("Yearly review prep", "", folder_hint="AWS")
        assert result["type"] == "management"
