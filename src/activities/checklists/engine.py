"""
Checklist engine — parses specializations/ markdown files and maps
asset tags to relevant checklists for a hunt session.
"""

import re
from pathlib import Path

SPECIALIZATIONS_DIR = Path(__file__).parent.parent.parent.parent / "specializations"

# Maps asset tags to checklist slugs from specializations/
TAG_TO_CHECKLISTS: dict[str, list[str]] = {
    "api":      ["idor-api"],
    "admin":    ["idor-api"],
    "upload":   ["idor-api"],
    "billing":  ["idor-api"],
    "internal": ["idor-api"],
    "auth":     ["oauth-auth"],
    "legacy":   ["idor-api"],
    "devtools": ["oauth-auth"],
    "cms":      ["idor-api"],
    "ai":       ["ai-llm"],
    "llm":      ["ai-llm"],
}

CHECKLIST_NAMES = {
    "idor-api":    "IDOR + API Security",
    "oauth-auth":  "OAuth + Authentication",
    "ai-llm":      "AI / LLM Security",
}


def checklists_for_tags(tags: list[str]) -> list[str]:
    """
    Returns deduplicated list of checklist slugs relevant for a given set of tags.
    Falls back to idor-api if no tags match — it's the broadest checklist.
    """
    slugs: list[str] = []
    for tag in tags:
        for slug in TAG_TO_CHECKLISTS.get(tag, []):
            if slug not in slugs:
                slugs.append(slug)
    return slugs if slugs else ["idor-api"]


def parse_checklist(slug: str) -> dict:
    """
    Parses a specializations/<slug>/checklist.md file into structured data.

    Returns:
        {
            "slug": "idor-api",
            "name": "IDOR + API Security",
            "sections": [
                {
                    "title": "Setup",
                    "items": ["Two test accounts created", ...]
                },
                ...
            ],
            "flat_items": ["Two test accounts created", ...]  # for indexing progress
        }
    """
    path = SPECIALIZATIONS_DIR / slug / "checklist.md"
    if not path.exists():
        return {"slug": slug, "name": slug, "sections": [], "flat_items": []}

    sections = []
    current_section = None
    flat_items = []

    for line in path.read_text().splitlines():
        # Section header
        if line.startswith("## "):
            if current_section:
                sections.append(current_section)
            current_section = {"title": line[3:].strip(), "items": [], "start_index": len(flat_items)}
            continue

        # Checklist item — matches "- [ ] text" or "- [x] text"
        match = re.match(r"^- \[[ xX]\] (.+)$", line)
        if match and current_section is not None:
            item_text = match.group(1).strip()
            current_section["items"].append(item_text)
            flat_items.append(item_text)

    if current_section:
        sections.append(current_section)

    return {
        "slug": slug,
        "name": CHECKLIST_NAMES.get(slug, slug),
        "sections": sections,
        "flat_items": flat_items,
    }


def load_checklists_for_session(slugs: list[str], progress: dict) -> list[dict]:
    """
    Loads and annotates checklists with current session progress.

    progress format: {"idor-api": [0, 2, 5], "oauth-auth": [1]}
    (list of flat item indices that are checked)

    Returns list of checklists with each item annotated with checked=True/False
    and its flat index for form submission.
    """
    result = []
    for slug in slugs:
        parsed = parse_checklist(slug)
        checked_indices = set(progress.get(slug, []))

        annotated_sections = []
        flat_index = 0
        for section in parsed["sections"]:
            annotated_items = []
            for item in section["items"]:
                annotated_items.append({
                    "text": item,
                    "index": flat_index,
                    "checked": flat_index in checked_indices,
                })
                flat_index += 1
            annotated_sections.append({
                "title": section["title"],
                "items": annotated_items,
            })

        total = len(parsed["flat_items"])
        done = len(checked_indices)
        pct = int((done / total) * 100) if total else 0

        result.append({
            "slug": slug,
            "name": parsed["name"],
            "sections": annotated_sections,
            "total": total,
            "done": done,
            "pct": pct,
        })

    return result
