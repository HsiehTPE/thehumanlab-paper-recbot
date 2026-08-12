from __future__ import annotations

import re

from paper_rec.config import InterestConfig, Profile
from paper_rec.models import Paper, RankedPaper


def contains_term(text: str, term: str) -> bool:
    normalized_text = re.sub(r"[-_]+", " ", text.lower())
    normalized_term = re.sub(r"[-_]+", " ", term.lower())
    pattern = re.escape(normalized_term).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", normalized_text) is not None


def score_interest(paper: Paper, interest: InterestConfig) -> tuple[int, tuple[str, ...]]:
    text = f"{paper.title}\n{paper.abstract}"
    if any(contains_term(text, term) for term in interest.exclude):
        return 0, ()
    matched = tuple(term for term in interest.include if contains_term(text, term))
    if not matched:
        return 0, ()
    title_hits = sum(1 for term in matched if contains_term(paper.title, term))
    score = min(100, 42 + len(matched) * 10 + title_hits * 12 + interest.weight * 3)
    return score, matched


def recall(papers: list[Paper], profile: Profile) -> list[RankedPaper]:
    candidates = []
    for paper in papers:
        best = None
        for interest in profile.interests:
            score, matched = score_interest(paper, interest)
            candidate = RankedPaper(
                paper=paper,
                section=interest.id,
                score=score,
                reason=f"Matched: {', '.join(matched)}" if matched else "",
                matched_terms=matched,
            )
            if score and (best is None or candidate.score > best.score):
                best = candidate
        if best is not None:
            candidates.append(best)
    candidates.sort(key=lambda item: (item.score, item.paper.published), reverse=True)
    return candidates[: profile.selection.recall_limit]
