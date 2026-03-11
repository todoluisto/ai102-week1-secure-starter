"""Classification categories for job opportunity scoring.

Defines the 5-bucket system used by the scorer to classify
job opportunities against a candidate's resume profile.
"""

from dataclasses import dataclass


@dataclass
class Category:
    id: int
    name: str
    criteria: list[str]
    suggested_action: str


CATEGORIES = [
    Category(
        id=1,
        name="Strong Fit — Apply Now",
        criteria=[
            "80%+ skills match with candidate profile",
            "Seniority level aligns with candidate experience",
            "Tech stack overlap is high (core languages, frameworks, platforms)",
            "Location/remote policy is compatible",
            "Domain or industry is relevant to candidate background",
        ],
        suggested_action="Draft tailored application this week",
    ),
    Category(
        id=2,
        name="Stretch Role — Worth a Shot",
        criteria=[
            "60-79% skills match",
            "Role is 1 level above current seniority or adjacent title",
            "Core tech stack overlaps but has growth areas",
            "Company or domain is appealing",
            "Growth opportunity outweighs the gap",
        ],
        suggested_action="Apply with a narrative that bridges the gap",
    ),
    Category(
        id=3,
        name="Interesting — Not Now",
        criteria=[
            "Compelling company, relevant domain, or strong team",
            "Mismatched on timing, seniority, location, or compensation signals",
            "Tech stack is adjacent but not core to candidate",
            "Worth revisiting if circumstances change",
        ],
        suggested_action="Save to watchlist with a note on why it's interesting, revisit in 30 days",
    ),
    Category(
        id=4,
        name="Needs More Research",
        criteria=[
            "Job description is vague or generic",
            "Unfamiliar company with limited public information",
            "Unclear tech stack, responsibilities, or team structure",
            "Role scope is ambiguous — could be great or terrible",
        ],
        suggested_action="Dig deeper before committing time — research company, find team on LinkedIn",
    ),
    Category(
        id=5,
        name="Not Relevant",
        criteria=[
            "Wrong tech stack entirely (no meaningful overlap)",
            "Wrong domain with no transferable value",
            "Spam recruiter blast or mass template",
            "Seniority mismatch of 2+ levels in either direction",
            "Clearly off target for candidate's career trajectory",
        ],
        suggested_action="Archive immediately — no action needed",
    ),
]


def format_categories_for_prompt() -> str:
    """Format all categories as text for inclusion in the classification prompt."""
    lines = []
    for cat in CATEGORIES:
        lines.append(f"### {cat.id}. {cat.name}")
        lines.append("Criteria:")
        for c in cat.criteria:
            lines.append(f"- {c}")
        lines.append(f"Default action: {cat.suggested_action}")
        lines.append("")
    return "\n".join(lines)
