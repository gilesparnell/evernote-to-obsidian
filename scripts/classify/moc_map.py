"""Maps of Content (MOC) lookup — pure data, no other imports.

Lives in its own module so consumers that only need the wikilink lookup
(the review server, future migration tools) don't transitively pull in
``lm_classifier`` → ``openai`` → ``httpx`` — a multi-second import chain
that has nothing to do with rendering an HTML page or moving a file.

The R2 frontmatter ``type`` field is canonical; this module's job is to
turn that into the ``up:`` wikilink for the right MOC.
"""

from __future__ import annotations


UP_MAP: dict[str, str] = {
    "meeting": "[[Meetings]]",
    "technical": "[[Technical]]",
    "reference": "[[Reference]]",
    "person": "[[People]]",
    "company": "[[Companies]]",
    "recipe": "[[Personal]]",
    "journal": "[[Personal]]",
    "personal": "[[Personal]]",
    "note": "[[Personal]]",
    "project": "[[Projects]]",
    "interview": "[[Interview Prep]]",
    "management": "[[Leadership]]",
    "application": "[[Job Hunt]]",
    "career": "[[Career]]",
    "pattern": "[[Patterns]]",
}


def up_for_type(type_value: str) -> str:
    """Return the wikilink for a note's MOC, given its R2 ``type`` value.

    Unknown / missing types fall back to ``[[Personal]]`` so the note is
    surfaced *somewhere* rather than orphaned.
    """
    return UP_MAP.get(type_value, "[[Personal]]")
