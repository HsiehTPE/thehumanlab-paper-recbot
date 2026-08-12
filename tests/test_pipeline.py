from __future__ import annotations

import sqlite3

from paper_rec.config import AppConfig, ArxivConfig, DeliveryConfig, InterestConfig, Profile, SelectionConfig
from paper_rec.models import Paper
from paper_rec.pipeline import Pipeline


class FakeSource:
    def fetch(self, config, interests=()):
        return [
            Paper(
                id="2608.00001v1",
                title="Medical Imaging Foundation Model",
                abstract="A foundation model for medical imaging and MRI analysis.",
                authors=("Ada Researcher",),
                published="2026-08-05T00:00:00+00:00",
                url="https://arxiv.org/abs/2608.00001v1",
                pdf_url="https://arxiv.org/pdf/2608.00001v1",
                categories=("cs.CV",),
            )
        ]


def test_pipeline_runs_without_network_or_delivery(tmp_path) -> None:
    app = AppConfig(tmp_path / "state", tmp_path / "output", {})
    profile = Profile(
        id="demo",
        title="Demo Digest",
        language="zh-CN",
        interests=(
            InterestConfig(
                id="medical",
                label="Medical",
                description="Medical imaging",
                include=("medical imaging", "MRI"),
                limit=3,
            ),
        ),
        arxiv=ArxivConfig(categories=("cs.CV",)),
        selection=SelectionConfig(ranker="heuristic", minimum_score=55, max_items=3),
        delivery=DeliveryConfig(),
    )

    result = Pipeline(app, source=FakeSource()).run(profile, skip_send=True)

    assert result.fetched_count == 1
    assert result.selected_count == 1
    assert (tmp_path / "output/demo/latest.md").exists()
    content = (tmp_path / "output/demo/latest.md").read_text(encoding="utf-8")
    assert "Medical Imaging Foundation Model" in content
    assert "今日论文速递" in content
    assert "作者追踪" not in content
    assert "【摘要】" in content
    assert "【值得关注】" in content
    connection = sqlite3.connect(tmp_path / "state/paper-rec.sqlite3")
    assert connection.execute("SELECT status FROM runs").fetchone()[0] == "succeeded"
