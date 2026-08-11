from __future__ import annotations

import pathlib

import pytest

from paper_rec.config import ConfigError, load_app_config, load_profile, validate_profile_channels


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_example_configuration_is_valid() -> None:
    app = load_app_config(ROOT / "config/app.yaml", ROOT)
    profile = load_profile(ROOT / "profiles/research.yaml")

    validate_profile_channels(profile, app)

    assert profile.id == "research"
    assert profile.arxiv.categories[0] == "cs.CV"
    assert app.channels["feishu_primary"].webhook_env == "FEISHU_WEBHOOK_URL"


def test_profile_rejects_unknown_ranker(tmp_path: pathlib.Path) -> None:
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        """
id: demo
title: Demo
language: zh-CN
interests:
  - id: vision
    label: Vision
    description: Vision papers
    include: [vision]
sources:
  arxiv:
    categories: [cs.CV]
selection:
  ranker: unknown
"""
    )

    with pytest.raises(ConfigError, match="ranker"):
        load_profile(profile_path)
