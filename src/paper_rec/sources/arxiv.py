from __future__ import annotations

import html
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from paper_rec.config import ArxivConfig, InterestConfig
from paper_rec.models import Paper

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
ARXIV_NS = {"arxiv": "http://arxiv.org/schemas/atom"}


class ArxivSource:
    def __init__(self, timeout: int = 30, retries: int = 3) -> None:
        self.timeout = timeout
        self.retries = retries

    def fetch(self, config: ArxivConfig, interests: tuple[InterestConfig, ...] = ()) -> list[Paper]:
        category_query = " OR ".join(f"cat:{category}" for category in config.categories)
        include_terms = tuple(
            dict.fromkeys(term.strip() for interest in interests for term in interest.include if term.strip())
        )
        if include_terms:
            keyword_query = " OR ".join(f'all:"{self._escape_query_term(term)}"' for term in include_terms)
            query = f"({category_query}) AND ({keyword_query})"
        else:
            query = category_query
        parameters = urllib.parse.urlencode(
            {
                "search_query": query,
                "start": 0,
                "max_results": config.max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        payload = self._request(f"{ARXIV_API}?{parameters}")
        cutoff = datetime.now(timezone.utc) - timedelta(hours=config.hours)
        papers = self._parse(payload)
        return [paper for paper in papers if datetime.fromisoformat(paper.published) >= cutoff]

    @staticmethod
    def _escape_query_term(term: str) -> str:
        return term.replace("\\", "\\\\").replace('"', '\\"')

    def fetch_ids(self, paper_ids: list[str]) -> list[Paper]:
        if not paper_ids:
            return []
        parameters = urllib.parse.urlencode({"id_list": ",".join(paper_ids)})
        return self._parse(self._request(f"{ARXIV_API}?{parameters}"))

    @staticmethod
    def paper_id_from_url(value: str) -> str:
        parsed = urllib.parse.urlparse(value)
        if parsed.netloc not in {"arxiv.org", "www.arxiv.org"}:
            raise ValueError(f"not an arXiv URL: {value}")
        path = parsed.path.strip("/")
        if path.startswith("abs/"):
            paper_id = path[4:]
        elif path.startswith("pdf/"):
            paper_id = path[4:]
            if paper_id.endswith(".pdf"):
                paper_id = paper_id[:-4]
        else:
            raise ValueError(f"unsupported arXiv URL: {value}")
        if not paper_id:
            raise ValueError(f"missing arXiv paper id: {value}")
        return paper_id

    def _parse(self, payload: bytes) -> list[Paper]:
        root = ET.fromstring(payload)
        papers = []
        for entry in root.findall("atom:entry", ATOM_NS):
            published_text = entry.findtext("atom:published", default="", namespaces=ATOM_NS)
            published = datetime.fromisoformat(published_text.replace("Z", "+00:00"))
            entry_url = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
            paper_id = entry_url.rsplit("/", 1)[-1]
            canonical_url = f"https://arxiv.org/abs/{paper_id}"
            links = {
                link.attrib.get("type"): link.attrib.get("href", "")
                for link in entry.findall("atom:link", ATOM_NS)
            }
            pdf_url = links.get("application/pdf", f"https://arxiv.org/pdf/{paper_id}")
            if pdf_url.startswith("http://arxiv.org/"):
                pdf_url = "https://" + pdf_url[len("http://"):]
            comment = entry.findtext("arxiv:comment", default="", namespaces=ARXIV_NS)
            abstract = self._normalize(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
            project_url = self._project_url(comment, abstract)
            papers.append(
                Paper(
                    id=paper_id,
                    title=self._normalize(entry.findtext("atom:title", default="", namespaces=ATOM_NS)),
                    abstract=abstract,
                    authors=tuple(
                        author.findtext("atom:name", default="", namespaces=ATOM_NS)
                        for author in entry.findall("atom:author", ATOM_NS)
                    ),
                    published=published.isoformat(),
                    url=canonical_url,
                    pdf_url=pdf_url,
                    categories=tuple(
                        category.attrib.get("term", "") for category in entry.findall("atom:category", ATOM_NS)
                    ),
                    project_url=project_url,
                )
            )
        return papers

    @staticmethod
    def _project_url(comment: str, abstract: str) -> str:
        """Find a project page in arXiv metadata or its abstract.

        arXiv comments commonly use ``Project page: ...``. Some papers put
        the link at the end of the abstract instead, so use the URL nearest a
        project-website phrase as a fallback.
        """
        for text in (comment, abstract):
            match = re.search(
                r"(?:project\s+(?:page|website|webpage)|website)\s*:?\s*(https?://\S+)",
                text,
                re.I,
            )
            if match:
                return match.group(1).rstrip(".,;)")
            # Depending on the arXiv representation, the visible text can be
            # rendered as "this https URL" while the actual target survives
            # as HTML or TeX markup in the API payload.
            linked = re.search(
                r"(?:href\s*=\s*[\"']|\\(?:url|href)\{)(https?://[^\"'\s}]+)",
                text,
                re.I,
            )
            if linked and re.search(r"project\s+(?:page|website|webpage)|website", text, re.I):
                return linked.group(1).rstrip(".,;)")
        return ""

    def _request(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "paper-rec/0.1 (profile-driven research digest)"},
        )
        last_error = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                last_error = error
                if error.code == 429 and attempt + 1 < self.retries:
                    retry_after = error.headers.get("Retry-After")
                    try:
                        delay = max(5, int(retry_after)) if retry_after else 15 * (2**attempt)
                    except ValueError:
                        delay = 15 * (2**attempt)
                    time.sleep(min(delay, 120))
                elif attempt + 1 < self.retries:
                    time.sleep(2**attempt)
            except Exception as error:
                last_error = error
                if attempt + 1 < self.retries:
                    time.sleep(2**attempt)
        if isinstance(last_error, urllib.error.HTTPError) and last_error.code == 429:
            raise RuntimeError(
                "arXiv rate limit reached (HTTP 429); wait a few minutes before retrying"
            ) from last_error
        raise RuntimeError(f"arXiv request failed after {self.retries} attempts") from last_error

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(html.unescape(value).split())
