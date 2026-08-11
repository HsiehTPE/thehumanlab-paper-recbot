from __future__ import annotations

from paper_rec.config import Profile
from paper_rec.models import RankedPaper


class HeuristicRanker:
    def rank(self, candidates: list[RankedPaper], profile: Profile) -> list[RankedPaper]:
        return candidates

