"""Scripted checks on a draft (stage 4 of the document crew). Plain code, no
model: free, deterministic, and run before Kural's review. They only report;
nothing here edits the draft.

Heuristics, not proof: a finding is something for Kural to look at.
"""

import re

MISSING = re.compile(r"\[MISSING:[^\]]*\]")
EMPTY_LINK = re.compile(r"\[[^\]]*\]\(\s*\)")
BARE_URL = re.compile(r"(?<![(\[<])https?://[^\s)>\]]+")
MD_LINK_WITH_URL = re.compile(r"\]\(\s*https?://")
CLAIM_WORDS = re.compile(r"\d\s?%|\baccording to\b|\b(study|survey|report|research) (shows?|found|finds|says)\b", re.IGNORECASE)
MIN_REPEAT_WORDS = 8


def _outside_code(markdown: str) -> list[str]:
    """Lines that are not inside a ``` fence."""
    lines, inside = [], False
    for line in markdown.splitlines():
        if line.strip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            lines.append(line)
    return lines


def run_checks(markdown: str) -> list[str]:
    findings = []
    text = markdown or ""
    if not text.strip():
        return ["the draft is empty"]

    if sum(1 for line in text.splitlines() if line.strip().startswith("```")) % 2:
        findings.append("unclosed code fence (odd number of ``` lines)")

    lines = _outside_code(text)

    previous = 0
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.*)", line)
        if match:
            level = len(match.group(1))
            if previous and level > previous + 1:
                findings.append(f"heading level jumps from H{previous} to H{level}: {match.group(2).strip()!r}")
            previous = level

    prose = "\n".join(lines)
    findings += [f"link with no URL: {m}" for m in EMPTY_LINK.findall(prose)]
    findings += [f"bare URL with no link text: {m}" for m in BARE_URL.findall(prose)]

    seen, repeated = set(), []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", prose):
        words = re.sub(r"[^a-z0-9 ]", "", sentence.lower()).split()
        if len(words) < MIN_REPEAT_WORDS:
            continue
        key = " ".join(words)
        if key in seen and key not in repeated:
            repeated.append(key)
            findings.append(f"repeated sentence: {sentence.strip()[:80]!r}")
        seen.add(key)

    for paragraph in re.split(r"\n\s*\n", prose):
        paragraph = paragraph.strip()
        if paragraph.startswith("#") or not paragraph:
            continue
        if CLAIM_WORDS.search(paragraph) and not MD_LINK_WITH_URL.search(paragraph):
            findings.append(f"possible unsourced claim (no link in the paragraph): {paragraph[:80]!r}")

    findings += [f"unresolved marker: {m}" for m in MISSING.findall(text)]
    return findings
