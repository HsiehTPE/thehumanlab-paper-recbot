from __future__ import annotations

from paper_rec.config import ArxivConfig, DeliveryConfig, InterestConfig, Profile, SelectionConfig
from paper_rec.models import Paper
from paper_rec.recall import recall


def make_profile() -> Profile:
    return Profile(
        id="demo",
        title="Demo",
        language="zh-CN",
        interests=(
            InterestConfig(
                id="medical",
                label="Medical",
                description="Medical imaging",
                include=("medical imaging", "MRI"),
                exclude=("genomics",),
            ),
        ),
        arxiv=ArxivConfig(categories=("cs.CV",)),
        selection=SelectionConfig(),
        delivery=DeliveryConfig(),
    )


def paper(paper_id: str, title: str, abstract: str) -> Paper:
    return Paper(paper_id, title, abstract, ("Author",), "2026-08-05", "https://example.test", "")


def test_recall_matches_terms_and_honors_exclusions() -> None:
    papers = [
        paper("1", "MRI reconstruction", "A medical imaging method."),
        paper("2", "MRI genomics", "Medical imaging combined with genomics."),
        paper("3", "Language modeling", "No imaging contribution."),
    ]

    candidates = recall(papers, make_profile())

    assert [candidate.paper.id for candidate in candidates] == ["1"]
    assert candidates[0].section == "medical"
    assert candidates[0].score >= 55


def test_recall_treats_hyphen_and_space_as_equivalent() -> None:
    candidates = recall(
        [paper("1", "Whole body control", "A humanoid robot controller.")],
        Profile(
            id="demo",
            title="Demo",
            language="en",
            interests=(
                InterestConfig(
                    id="robotics",
                    label="Robotics",
                    description="Robotics",
                    include=("whole-body control",),
                ),
            ),
            arxiv=ArxivConfig(categories=("cs.RO",)),
            selection=SelectionConfig(),
            delivery=DeliveryConfig(),
        ),
    )

    assert [candidate.paper.id for candidate in candidates] == ["1"]
