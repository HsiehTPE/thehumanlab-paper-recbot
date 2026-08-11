from __future__ import annotations

from paper_rec.config import Profile
from paper_rec.models import Digest, RankedPaper


_CHINESE_NUMBERS = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十")


def _section_heading(index: int, label: str) -> str:
    number = _CHINESE_NUMBERS[index - 1] if index <= len(_CHINESE_NUMBERS) else str(index)
    return f"第{number}部分：{label}"


def _paper_tags(ranked: RankedPaper) -> str:
    if ranked.matched_terms:
        return ", ".join(ranked.matched_terms)
    return "未提取到明确标签"


def _attention(ranked: RankedPaper) -> str:
    if ranked.reason.startswith("Matched:"):
        terms = ranked.reason.removeprefix("Matched:").strip()
        return f"论文与当前方向的关键词匹配度较高，主要涉及：{terms}。"
    return ranked.reason or "论文与当前研究方向相关，建议结合原文进一步判断。"


def _field(label: str, value: str) -> list[str]:
    return [f"【{label}】", value]


def _institutions(values: tuple[str, ...]) -> str:
    if not values:
        return "未获取到作者机构信息"
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(value.split()).strip(" ,;:")
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return "\n".join(f"{index}. {value}" for index, value in enumerate(unique, 1))


def _trend(profile: Profile, papers: list[RankedPaper]) -> str:
    if not papers:
        return "今日没有足够的候选论文形成明显趋势。"
    labels = [interest.label for interest in profile.interests if any(item.section == interest.id for item in papers)]
    return f"今日论文主要集中在：{'、'.join(labels)}。建议优先关注评分较高且与多个关键词匹配的工作。"


def render_markdown(profile: Profile, papers: list[RankedPaper]) -> Digest:
    by_section = {interest.id: [] for interest in profile.interests}
    for paper in papers:
        by_section[paper.section].append(paper)

    lines = ["今日论文速递", ""]
    for index, interest in enumerate(profile.interests, 1):
        lines.extend([_section_heading(index, interest.label), ""])
        selected = by_section[interest.id][: interest.limit]
        if not selected:
            lines.extend(["今天没有特别值得关注的新论文。", ""])
            continue
        for index, ranked in enumerate(selected, 1):
            paper = ranked.paper
            lines.extend(
                [
                    f"{index}. {paper.title}",
                    "",
                    *_field("Paper", paper.url),
                    *(_field("Project", paper.project_url) if paper.project_url else []),
                    *_field("Authors", ", ".join(paper.authors)),
                    *_field("Institutions", _institutions(paper.institutions)),
                    *(_field("Code", ", ".join(paper.code_links)) if paper.code_links else []),
                    *_field("Published", paper.published[:10]),
                    *_field("Tags", _paper_tags(ranked)),
                    "",
                    *_field("摘要", paper.abstract),
                    *_field("值得关注", _attention(ranked)),
                    "",
                ]
            )
    lines.extend([f"今日趋势: {_trend(profile, papers)}", ""])
    content = "\n".join(lines).rstrip() + "\n"
    return Digest(profile.id, profile.title, content, tuple(papers))
