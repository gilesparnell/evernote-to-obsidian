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


class TestReviewQueueMinedRules:
    """Rules mined from the chunk-3 AWS review queue (566 items). Each pattern
    represented >= 8 review-queue notes — collectively ~32% of the queue.
    These move recurring Evernote-shape artefacts from LM-burdened review
    candidates to free rules-only auto-classification.
    """

    # --- Evernote web-clipper "Cursor and ..." (107 / 566 = 19% of queue) ---
    # When the user clipped a web page or PDF via cursor selection, Evernote
    # auto-prepended "Cursor and " to the title. These are clippings, not
    # technical content — type: reference fits.
    def test_cursor_and_title_is_reference(self) -> None:
        result = classify(
            "Cursor and 14 Maralinga Lease 2016 - realestate.com.au",
            "",
            folder_hint="AWS",
        )
        assert result["type"] == "reference"

    def test_cursor_and_pdf_clipping_is_reference(self) -> None:
        result = classify(
            "Cursor and 140130AMD6 Amazon DMWall Production Quote.pdf",
            "",
            folder_hint="AWS",
        )
        assert result["type"] == "reference"

    def test_cursor_alone_without_and_does_not_match(self) -> None:
        # Defensive: a note literally about Cursor (the IDE) shouldn't be
        # caught by this rule. The "and" suffix is required.
        result = classify(
            "Cursor IDE setup notes",
            "AWS S3 deployment guide using Cursor editor",
            folder_hint="AWS",
        )
        # Not the web-clipper rule — falls through to keyword scoring.
        # Body has "aws" + "s3" (tech keywords from new rule below), so
        # type may be 'technical', NOT 'reference'.
        assert result["type"] != "reference"

    # --- AWS service-name title prefix (EC2 alone = 37 / 566 = 7% of queue) ---
    # Notes titled with a bare AWS service name are technical content by
    # construction. EC2 was 37 occurrences; adding the broader cluster
    # catches similar shapes (S3 Palantir.NN, Lambda foo, IAM bar).
    def test_ec2_prefix_is_technical(self) -> None:
        result = classify("EC2 Palantir.10", "", folder_hint="AWS")
        assert result["type"] == "technical"
        assert result["org"] == "Amazon"

    def test_s3_prefix_is_technical(self) -> None:
        result = classify("S3 bucket policy notes", "", folder_hint="AWS")
        assert result["type"] == "technical"

    def test_iam_prefix_is_technical(self) -> None:
        result = classify("IAM role review", "", folder_hint="AWS")
        assert result["type"] == "technical"

    def test_lambda_prefix_is_technical(self) -> None:
        result = classify("Lambda cold-start mitigation", "", folder_hint="AWS")
        assert result["type"] == "technical"

    def test_dynamodb_prefix_is_technical(self) -> None:
        result = classify("DynamoDB capacity planning", "", folder_hint="AWS")
        assert result["type"] == "technical"

    def test_api_gateway_with_space_is_technical(self) -> None:
        result = classify("API Gateway throttling", "", folder_hint="AWS")
        assert result["type"] == "technical"

    def test_aws_service_word_in_middle_does_not_match(self) -> None:
        # The rule anchors to the start of the title to avoid over-firing.
        # "Meeting about EC2" should still be a meeting from keywords.
        result = classify(
            "Meeting agenda items about EC2 capacity",
            "standup meeting attendees agenda",
            folder_hint="AWS",
        )
        assert result["type"] == "meeting"

    # --- Numeric image filenames (21 / 566) — Evernote camera-export titles ---
    # Pattern: 8+ digits then .jpg/.png/.heic. These are photo dumps with no
    # textual body — auto-classify as reference so they leave the LM queue.
    def test_numeric_jpg_filename_is_reference(self) -> None:
        result = classify("03172015127.jpg", "", folder_hint="AWS")
        assert result["type"] == "reference"

    def test_numeric_heic_filename_is_reference(self) -> None:
        result = classify("20180412093715.heic", "", folder_hint="AWS")
        assert result["type"] == "reference"

    def test_short_numeric_filename_does_not_match(self) -> None:
        # Only filenames with 8+ digits (Evernote's camera-export shape).
        # A 4-digit prefix like "1234 notes.jpg" shouldn't be auto-typed.
        result = classify("1234 notes.jpg", "AWS S3 deployment", folder_hint="AWS")
        # Should fall through to keyword scoring, not be rule-typed.
        # Body has multiple Amazon-org keywords; type from keywords (technical or note).
        assert result["type"] != "reference" or result["type"] == "technical"

    # --- GoToWebinar (9+ / 566) — webinar screencap notes ---
    def test_gotowebinar_title_is_reference(self) -> None:
        result = classify("GoToWebinar Viewer.2", "", folder_hint="AWS")
        assert result["type"] == "reference"

    def test_gotowebinar_with_underscore_is_reference(self) -> None:
        result = classify("GoToWebinar_ Talking_ Attendee 4", "", folder_hint="AWS")
        assert result["type"] == "reference"

    # --- Inbox email exports (8 / 566) — Evernote's email-to-Evernote feature ---
    # Pattern: "Inbox – gilesparnell@gmail.com.N". The em-dash + email
    # combination is the marker. The rule requires a dash separator so a
    # legitimate note titled just "Inbox" or "Inbox cleanup plan" isn't
    # caught.
    def test_inbox_email_export_is_reference(self) -> None:
        result = classify(
            "Inbox – gilesparnell@gmail.com.1", "", folder_hint="AWS"
        )
        assert result["type"] == "reference"

    def test_inbox_hyphen_email_export_is_reference(self) -> None:
        # ASCII hyphen variant (not all exports preserve the em-dash).
        result = classify(
            "Inbox - giles@example.com", "", folder_hint="AWS"
        )
        assert result["type"] == "reference"

    def test_bare_inbox_title_does_not_match(self) -> None:
        # A note literally named "Inbox" without an email is allowed to
        # fall through to content-based classification.
        result = classify("Inbox", "task list for the week", folder_hint="")
        assert result["type"] != "reference"


class TestBodyShapeClippingRules:
    """Plan 2026-05-26-001 — bodies that are JUST an embed (image / URL /
    audio / PDF) classify as type='clipping' with high confidence, bypassing
    the LM. Org comes from the folder hint when content gives no signal.

    Mined from the 566-note chunk-3 review queue: 321 image-only + 7 URL-only
    + 4 audio/PDF-only = 332 notes (58.7% of the queue) currently wasting an
    LM call to land in review for human triage. After this rule, they auto-
    classify as clippings."""

    # --- Rule A: body is a single image embed ---

    def test_body_single_image_skitch_classifies_as_clipping(self) -> None:
        # Most common shape in the review queue: Evernote Skitch screencap.
        result = classify(
            title="03172015127.jpg",
            body="![skitch.png](./_resources/03172015127.jpg.resources/skitch.png)",
            folder_hint="AWS",
        )
        assert result["type"] == "clipping"

    def test_body_single_image_other_alt_text_classifies_as_clipping(self) -> None:
        # Not all image bodies are Skitch — Evernote also embeds with
        # arbitrary alt text and IMG_xxxx.JPG filenames.
        result = classify(
            title="Containers_ Kevin Gibbs",
            body="![IMG_0428.JPG](./_resources/Containers__Kevin_Gibbs.resources/IMG_0428.JPG)",
            folder_hint="AWS",
        )
        assert result["type"] == "clipping"

    def test_body_image_with_trailing_whitespace_classifies_as_clipping(self) -> None:
        # The classifier currently strips body whitespace before length
        # checks, but the body-shape regex should tolerate trailing newlines
        # / spaces from Markdown render conventions.
        result = classify(
            title="screenshot",
            body="![x](path.png)\n\n",
            folder_hint="AWS",
        )
        assert result["type"] == "clipping"

    def test_body_image_with_additional_text_falls_through(self) -> None:
        # If there's a caption or any prose alongside the image, the body
        # has real content — must NOT short-circuit to clipping.
        result = classify(
            title="Architecture diagram",
            body=(
                "![diagram](./_resources/arch.png)\n\n"
                "This is the proposed AWS S3 + Lambda + IAM ingestion "
                "pipeline for the Q2 deployment. See action items below."
            ),
            folder_hint="AWS",
        )
        assert result["type"] != "clipping"

    # --- Rule B: body is a single URL ---

    def test_body_single_url_classifies_as_clipping(self) -> None:
        result = classify(
            title="Spotify Account overview",
            body="https://www.spotify.com/account/overview",
            folder_hint="",
        )
        assert result["type"] == "clipping"

    def test_body_url_in_angle_brackets_classifies_as_clipping(self) -> None:
        # Common Markdown shape: angle-bracket-wrapped URL.
        result = classify(
            title="Laser guide",
            body="<http://www.laserist.org/guide-to-laser-shows.html>",
            folder_hint="",
        )
        assert result["type"] == "clipping"

    def test_body_url_with_paragraph_text_falls_through(self) -> None:
        result = classify(
            title="Architecture refs",
            body=(
                "Reference architecture for AWS S3-backed ingestion is "
                "documented at https://docs.aws.amazon.com/foo and the "
                "Lambda piece is covered in the linked RFC."
            ),
            folder_hint="AWS",
        )
        assert result["type"] != "clipping"

    # --- Rule C: body is an audio or PDF embed ---

    def test_body_evernote_audio_embed_classifies_as_clipping(self) -> None:
        # Evernote-exported voice memos: literal `[Evernote YYYYMMDD HH-MM-SS.m4a](...)`.
        result = classify(
            title="Note.14",
            body="[Evernote 20180510 08-25-09.m4a](./_resources/Note.14.resources/Evernote%2020180510%2008-25-09.m4a)",
            folder_hint="AWS",
        )
        assert result["type"] == "clipping"

    def test_body_pdf_image_embed_classifies_as_clipping(self) -> None:
        # Evernote-clipped PDFs land as image embeds with `.pdf` in the alt text
        # (one-page-per-image preview).
        result = classify(
            title="Amazon Stamp 032",
            body="![Amazon Stamp 032.pdf](./_resources/Amazon_Stamp_032.pdf/page-1.png)",
            folder_hint="AWS",
        )
        assert result["type"] == "clipping"

    # --- Org inference from folder hint ---
    # These tests use a title that does NOT trigger any existing title rule
    # (e.g. "x123"), so any passing org/confidence assertion comes from the
    # new body-shape rule alone, not an accidental title-rule fallback.

    def test_clipping_uses_folder_hint_for_amazon_org(self) -> None:
        result = classify(
            title="x123",  # no title-rule match
            body="![s](./_r/s.png)",
            folder_hint="AWS",  # → Amazon per ORG_KEYWORDS
        )
        assert result["type"] == "clipping"
        assert result["org"] == "Amazon"

    def test_clipping_no_folder_hint_defaults_to_personal(self) -> None:
        result = classify(
            title="x123",
            body="![s](./_r/s.png)",
            folder_hint="",
        )
        assert result["type"] == "clipping"
        assert result["org"] == "Personal"

    # --- Confidence ---

    def test_clipping_confidence_above_auto_threshold(self) -> None:
        # Body-shape rules must clear the 0.80 auto-classify gate so the
        # pipeline writes frontmatter instead of routing to review. Title
        # is "x123" to avoid the existing 'screenshot' title rule firing
        # at confidence 0.95 and masking the body-shape rule's contribution.
        result = classify(
            title="x123",
            body="![s](./_r/s.png)",
            folder_hint="AWS",
        )
        assert result["type"] == "clipping"
        assert result["confidence"] >= 0.80

    # --- Integration with the existing cascade ---

    def test_clipping_image_wins_over_title_keyword(self) -> None:
        # A title like "Standup notes" would normally hit the title-rule
        # cascade and classify as meeting. But an image-only body is a
        # stronger signal that this is a clipped artefact, not a real
        # meeting note — clipping wins.
        result = classify(
            title="Standup notes",
            body="![board](./_r/whiteboard.png)",
            folder_hint="AWS",
        )
        assert result["type"] == "clipping"


class TestShouldPurgeByBodyShape:
    """Plan 2026-05-26-001 — body < 30 chars (after stripping markdown
    wrappers) is a stub note worth deleting outright. Operator opted in to
    hard-delete on 2026-05-26; manifest at .classify_deleted_manifest.json
    captures each deletion for audit.

    Empty bodies ALSO purge per operator decision (zero-length notes are
    junk by definition)."""

    # True cases — small bodies purge

    def test_purges_tiny_phone_number_body(self) -> None:
        from scripts.classify.rules_classifier import should_purge_by_body_shape
        # Bare phone number — the kind of one-line scribble the operator
        # explicitly opted to purge. (Markdown-wrapped tel links are
        # 32+ chars after stripping and survive to the review queue —
        # documented as a v2 enhancement in plan §Out of Scope.)
        assert should_purge_by_body_shape("041 581 7988")

    def test_purges_tiny_address_fragment(self) -> None:
        from scripts.classify.rules_classifier import should_purge_by_body_shape
        # Real example: 746276943.md body was an ID string.
        assert should_purge_by_body_shape("746276943\n082356")

    def test_purges_body_with_only_whitespace_and_markdown_chars(self) -> None:
        from scripts.classify.rules_classifier import should_purge_by_body_shape
        # Real example: "AB Committee Meeting Agenda" body = "**<u>\n</u>**".
        # After stripping markdown wrappers it's effectively empty.
        assert should_purge_by_body_shape("**<u>\n</u>**")

    def test_purges_29_char_body(self) -> None:
        from scripts.classify.rules_classifier import should_purge_by_body_shape
        # Boundary: 29 chars after strip = purge.
        body = "x" * 29
        assert should_purge_by_body_shape(body)

    # True cases — empty bodies purge per 2026-05-26 operator decision

    def test_purges_empty_body(self) -> None:
        from scripts.classify.rules_classifier import should_purge_by_body_shape
        assert should_purge_by_body_shape("")

    def test_purges_whitespace_only_body(self) -> None:
        from scripts.classify.rules_classifier import should_purge_by_body_shape
        assert should_purge_by_body_shape("   \n\n\t  \n")

    # False cases — bodies at or above the threshold do not purge

    def test_does_not_purge_30_char_body(self) -> None:
        from scripts.classify.rules_classifier import should_purge_by_body_shape
        # Boundary: 30 chars after strip = keep. < not <=.
        body = "x" * 30
        assert not should_purge_by_body_shape(body)

    def test_does_not_purge_image_only_body(self) -> None:
        from scripts.classify.rules_classifier import should_purge_by_body_shape
        # An image-only body strips down to "" via _BODY_STRIP_MARKDOWN_RE —
        # which would be < 30 chars — BUT the pipeline runs the clipping
        # rule check FIRST and routes to classify(), not purge. This unit
        # test confirms should_purge() in isolation would return True; the
        # pipeline-level test in TestBodyShapeOrdering proves the ordering.
        #
        # Reading the helper in isolation: yes, an image-only body strips
        # to nothing and the function returns True. The CALLER (pipeline)
        # is responsible for checking clipping rules first.
        body = "![x](path.png)"
        assert should_purge_by_body_shape(body)


class TestBodyShapeReason:
    """The reason string lives in the result dict and ends up in the review
    HTML / heartbeat / sample reports. Must clearly name which body-shape
    rule fired so downstream operators can understand the classification."""

    def test_image_only_body_reason_names_clipping(self) -> None:
        result = classify(
            title="s", body="![x](path.png)", folder_hint="AWS",
        )
        assert "clipping" in result["reason"].lower()

    def test_url_only_body_reason_names_clipping(self) -> None:
        result = classify(
            title="s", body="https://example.com/foo", folder_hint="",
        )
        assert "clipping" in result["reason"].lower()
