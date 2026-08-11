from __future__ import annotations

import io
import html
import re
import urllib.request
from dataclasses import replace

from paper_rec.models import Paper, RankedPaper


_INSTITUTION_HINTS = (
    "university",
    "institute",
    "institution",
    "laboratory",
    "lab",
    "college",
    "school",
    "department",
    "faculty",
    "hospital",
    "medical center",
    "research center",
    "research centre",
    "academy",
    "polytechnic",
)
_CODE_HOSTS = ("github.com", "gitlab.com", "huggingface.co", "bitbucket.org", "codeberg.org")
_URL_PATTERN = re.compile(r"https?://[^\s<>\]\[)\"']+")


class PdfEnricher:
    def __init__(self, timeout: int = 45, max_pages: int = 2) -> None:
        self.timeout = timeout
        self.max_pages = max_pages

    def enrich(self, ranked: list[RankedPaper]) -> list[RankedPaper]:
        return [self._enrich_one(item) for item in ranked]

    def _enrich_one(self, ranked: RankedPaper) -> RankedPaper:
        pdf_url = ranked.paper.pdf_url
        if not pdf_url:
            return self._enrich_from_project_page(ranked, "")
        try:
            pdf_text = ""
            project_text = ""
            if ranked.paper.project_url:
                try:
                    project_text = self._download_web_text(ranked.paper.project_url)
                except Exception:
                    project_text = ""
            try:
                pdf_text = self._download_text(pdf_url)
            except Exception:
                if not project_text:
                    raise
            # Affiliations come from the paper PDF only. Project pages often
            # repeat the author block and contain footer/promotional text.
            institutions = self._extract_institutions(pdf_text)
            code_links, code_status = self._extract_code_links(
                f"{pdf_text}\n{project_text}", ranked.paper.abstract
            )
            paper = replace(
                ranked.paper,
                institutions=tuple(institutions),
                code_links=tuple(code_links),
                code_status=code_status,
            )
            return replace(ranked, paper=paper)
        except Exception:
            return ranked

    def _enrich_from_project_page(self, ranked: RankedPaper, text: str) -> RankedPaper:
        if not text or not ranked.paper.project_url:
            return ranked
        code_links, code_status = self._extract_code_links(text, ranked.paper.abstract)
        paper = replace(ranked.paper, code_links=tuple(code_links), code_status=code_status)
        return replace(ranked, paper=paper)

    def _download_text(self, url: str) -> str:
        from pypdf import PdfReader

        request = urllib.request.Request(
            url,
            headers={"User-Agent": "paper-rec/0.1 (PDF metadata extraction)"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = response.read()
        reader = PdfReader(io.BytesIO(payload))
        pages = reader.pages[: self.max_pages]
        return "\n".join(page.extract_text() or "" for page in pages)

    def _download_web_text(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "paper-rec/0.1 (project page metadata extraction)"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            content = response.read().decode("utf-8", errors="ignore")
        return html.unescape(re.sub(r"<[^>]+>", " ", content))

    @staticmethod
    def _extract_institutions(text: str) -> list[str]:
        normalized_text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
        raw_lines = [re.sub(r"\s+", " ", line).strip(" •") for line in normalized_text.splitlines()]
        lines: list[str] = []
        index = 0
        while index < len(raw_lines):
            line = raw_lines[index]
            if PdfEnricher._is_affiliation_noise(line):
                index += 1
                continue
            if line and any(hint in line.lower() for hint in _INSTITUTION_HINTS):
                chunks = PdfEnricher._split_numbered_affiliations(line)
                merged = chunks[0]
                next_index = index + 1
                while next_index < len(raw_lines) and PdfEnricher._is_wrapped_affiliation_line(
                    merged, raw_lines[next_index]
                ):
                    merged = f"{merged} {raw_lines[next_index]}".strip()
                    next_index += 1
                lines.extend([merged, *chunks[1:]])
                index = next_index
                continue
            lines.append(line)
            index += 1

        results: list[str] = []
        seen: set[str] = set()
        for line in lines:
            was_numbered = re.match(r"^\s*\d+\s*[A-Z]", line) is not None
            line = re.sub(r"^\s*\d+\s*[.)-]?\s*", "", line).strip(" ,;:")
            if not line or len(line) < 4 or len(line) > 180:
                continue
            if PdfEnricher._is_affiliation_noise(line):
                continue
            lower = line.lower()
            # Some affiliations use a lab/unit name plus a university (for
            # example "Cognitive Robotics, TU Delft") without the literal
            # words university/institute. Such numbered chunks are still
            # affiliations when they contain a location-style comma.
            if not any(hint in lower for hint in _INSTITUTION_HINTS) and not (
                was_numbered
                and "," in line
                and len(line.split()) >= 4
            ):
                continue
            key = re.sub(r"\W+", " ", lower).strip()
            if key not in seen:
                seen.add(key)
                results.append(line)
        return results[:6]

    @staticmethod
    def _split_numbered_affiliations(line: str) -> list[str]:
        # PDF extraction may produce both "2 University" and "2University".
        markers = list(re.finditer(r"(?<!\w)(?=\d{1,2}\s*[A-Z])", line))
        if len(markers) < 2:
            return [line]
        starts = [match.start() for match in markers]
        chunks = []
        for offset, start in enumerate(starts):
            end = starts[offset + 1] if offset + 1 < len(starts) else len(line)
            chunk = line[start:end].strip()
            if chunk:
                chunks.append(chunk)
        return chunks or [line]

    @staticmethod
    def _is_affiliation_noise(line: str) -> bool:
        lower = line.lower()
        return (
            not line
            or "http://" in lower
            or "https://" in lower
            or "project page" in lower
            or "project website" in lower
            or "paper and code are available" in lower
            or "videos and more details" in lower
            or "available above" in lower
            or lower.startswith(("abstract", "keywords"))
        )

    @staticmethod
    def _is_wrapped_affiliation_line(current: str, candidate: str) -> bool:
        if not candidate or len(candidate) > 100:
            return False
        lower = candidate.lower()
        if any(marker in lower for marker in ("@", "http://", "https://", "abstract", "keywords", "arxiv")):
            return False
        if re.match(r"^(?:\d+\s*[.)-]?|[a-z]\s*[.)-])\s*", candidate, re.I):
            return False
        if current.endswith((",", ";", ":")):
            return True
        if any(hint in lower for hint in _INSTITUTION_HINTS):
            return False
        if candidate[:1].islower() or lower.startswith(("of ", "and ", "for ", "the ", "at ", "room ", "building ")):
            return True
        return bool(re.search(r"\d{3,}|\b(?:usa|china|japan|italy|germany|france|uk|taiwan)\b", lower))

    @staticmethod
    def _extract_code_links(text: str, abstract: str) -> tuple[list[str], str]:
        links: list[str] = []
        for value in _URL_PATTERN.findall(f"{text}\n{abstract}"):
            cleaned = value.rstrip(".,;:)}]")
            if any(host in cleaned.lower() for host in _CODE_HOSTS) and cleaned not in links:
                links.append(cleaned)
        if links:
            return links[:3], "open_source"
        combined = f"{text}\n{abstract}".lower()
        planned = ("code will be released", "code will be made available", "source code will be released")
        if any(marker in combined for marker in planned):
            return [], "planned_release"
        return [], "not_found"
