from __future__ import annotations

import pathlib

import pytest

from paper_rec.config import ConfigError
from paper_rec.customize import _base_paper_id, _read_seed_config
from paper_rec.pdf import PdfEnricher
from paper_rec.sources.arxiv import ArxivSource


def test_arxiv_url_parser_accepts_abs_and_pdf_urls() -> None:
    assert ArxivSource.paper_id_from_url("https://arxiv.org/abs/2401.12345v2") == "2401.12345v2"
    assert ArxivSource.paper_id_from_url("https://arxiv.org/pdf/2401.12345.pdf") == "2401.12345"
    assert _base_paper_id("2401.12345v3") == "2401.12345"


def test_arxiv_api_urls_are_canonical_https_urls() -> None:
    source = ArxivSource()
    payload = b'''<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2401.12345v1</id>
        <published>2026-08-10T00:00:00Z</published>
        <title>Example Paper</title>
        <summary>Example abstract.</summary>
        <arxiv:comment xmlns:arxiv="http://arxiv.org/schemas/atom">18 pages. Project page: https://example.github.io/project/</arxiv:comment>
        <author><name>Example Author</name></author>
      </entry>
    </feed>'''
    assert source._parse(payload)[0].url == "https://arxiv.org/abs/2401.12345v1"
    assert source._parse(payload)[0].project_url == "https://example.github.io/project/"


def test_arxiv_project_url_can_come_from_abstract_link() -> None:
    source = ArxivSource()
    payload = b'''<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>https://arxiv.org/abs/2608.09762v1</id>
        <published>2026-08-10T00:00:00Z</published>
        <title>Example Robotics Paper</title>
        <summary>Videos and more details are available at our project website: &lt;a href="https://example.github.io/"&gt;this https URL&lt;/a&gt;.</summary>
        <author><name>Example Author</name></author>
      </entry>
    </feed>'''
    assert source._parse(payload)[0].project_url == "https://example.github.io/"


def test_pdf_metadata_extractors_find_institution_and_code_link() -> None:
    text = "University of Example\nhttps://github.com/example/project\n"
    assert PdfEnricher._extract_institutions(text) == ["University of Example"]
    links, status = PdfEnricher._extract_code_links(text, "")
    assert links == ["https://github.com/example/project"]
    assert status == "open_source"


def test_pdf_institution_extractor_joins_wrapped_affiliation_lines() -> None:
    text = "Department of Robotics,\nUniversity of Example,\nExample City, 12345\n"
    assert PdfEnricher._extract_institutions(text) == [
        "Department of Robotics, University of Example, Example City, 12345"
    ]


def test_seed_config_rejects_more_than_five_links(tmp_path: pathlib.Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "max_papers_per_interest: 6\ninterests: []\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="1 to 5"):
        _read_seed_config(tmp_path)


def test_local_seed_config_inherits_public_base(tmp_path: pathlib.Path) -> None:
    (tmp_path / "config.base.yaml").write_text(
        "mode: preserve\nmax_papers_per_interest: 5\ninterests:\n"
        "  - id: base\n    label: Base\n    file: base.example.txt\n",
        encoding="utf-8",
    )
    (tmp_path / "config.local.yaml").write_text(
        "inherit: config.base.yaml\nmode: rewrite\ninterests:\n"
        "  - id: local\n    label: Local\n    file: local.local.txt\n",
        encoding="utf-8",
    )
    (tmp_path / "local.local.txt").write_text(
        "https://arxiv.org/abs/2401.12345\n", encoding="utf-8"
    )

    raw, path = _read_seed_config(tmp_path)

    assert path.name == "config.local.yaml"
    assert raw["mode"] == "rewrite"
    assert raw["max_papers_per_interest"] == 5
    assert raw["interests"][0]["id"] == "local"
