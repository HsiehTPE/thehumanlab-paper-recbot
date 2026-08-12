from paper_rec.config import ArxivConfig, InterestConfig
from paper_rec.sources.arxiv import ArxivSource


def test_arxiv_query_uses_categories_and_include_terms() -> None:
    source = ArxivSource()
    config = ArxivConfig(categories=("cs.CV", "cs.RO"))
    interests = (
        InterestConfig(
            id="robotics",
            label="Robotics",
            description="Robotics",
            include=("humanoid robot", "whole-body control", "humanoid robot"),
        ),
    )

    captured = {}

    def fake_request(url: str) -> bytes:
        captured["url"] = url
        return b'<feed xmlns="http://www.w3.org/2005/Atom" />'

    source._request = fake_request
    source.fetch(config, interests)

    assert "cat%3Acs.CV" in captured["url"]
    assert "all%3A%22humanoid+robot%22" in captured["url"]
    assert "all%3A%22whole-body+control%22" in captured["url"]
    assert captured["url"].count("humanoid+robot") == 1
