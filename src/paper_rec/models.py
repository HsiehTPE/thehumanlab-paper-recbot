from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Paper:
    id: str
    title: str
    abstract: str
    authors: tuple[str, ...]
    published: str
    url: str
    pdf_url: str
    categories: tuple[str, ...] = ()
    source: str = "arxiv"
    project_url: str = ""
    institutions: tuple[str, ...] = ()
    code_links: tuple[str, ...] = ()
    code_status: str = "not_found"


@dataclass(frozen=True)
class RankedPaper:
    paper: Paper
    section: str
    score: int
    reason: str
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Digest:
    profile_id: str
    title: str
    content: str
    papers: tuple[RankedPaper, ...]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    fetched_count: int
    candidate_count: int
    selected_count: int
    output_path: str
    deliveries: dict[str, str] = field(default_factory=dict)
