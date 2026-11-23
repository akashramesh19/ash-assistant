from crew.checks import run_checks

GOOD = """# Title

Intro paragraph with a clear point about the subject matter at hand today.

## Section

A claim of 40% growth is [reported here](https://example.com/report).
"""


def test_clean_draft_has_no_findings():
    assert run_checks(GOOD) == []


def test_empty_draft():
    assert run_checks("  \n") == ["the draft is empty"]


def test_heading_level_jump():
    assert any("H1 to H3" in f for f in run_checks("# A\n\n### C\n\ntext"))


def test_first_heading_may_be_any_level():
    assert run_checks("## Start\n\ntext here\n\n### Next\n") == []


def test_empty_link_and_bare_url():
    found = run_checks("See [here]() and https://example.com/x for more.")
    assert any("link with no URL" in f for f in found)
    assert any("bare URL" in f for f in found)


def test_url_inside_a_markdown_link_is_not_bare():
    assert not any("bare URL" in f for f in run_checks("See [docs](https://example.com/x) now."))


def test_repeated_sentence():
    text = "This sentence is long enough to be flagged as a repeat.\n\nOther text.\n\nThis sentence is long enough to be flagged as a repeat."
    assert any("repeated sentence" in f for f in run_checks(text))


def test_short_repeats_are_ignored():
    assert run_checks("Yes.\n\nYes.\n\nYes.") == []


def test_unsourced_claim_flagged_but_sourced_one_is_not():
    assert any("unsourced claim" in f for f in run_checks("Sales rose 40% last year."))
    assert not any("unsourced" in f for f in run_checks("Sales rose 40% ([source](https://example.com))."))


def test_missing_markers_are_reported():
    assert any("[MISSING: the date]" in f for f in run_checks("Launch is on [MISSING: the date]."))


def test_unclosed_code_fence_and_content_inside_fences_is_ignored():
    assert any("unclosed code fence" in f for f in run_checks("```\ncode\n"))
    assert run_checks("# A\n\n```\n### not a heading\nhttps://bare.example\n```\n") == []
