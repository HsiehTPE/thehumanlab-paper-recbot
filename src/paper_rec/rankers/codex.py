from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

from paper_rec.config import Profile
from paper_rec.models import RankedPaper


class CodexRanker:
    def __init__(self, executable: str = "codex", timeout: int = 300) -> None:
        self.executable = executable
        self.timeout = timeout

    def rank(self, candidates: list[RankedPaper], profile: Profile) -> list[RankedPaper]:
        if not candidates:
            return []
        prompt = self._build_prompt(candidates, profile)
        command = [
            self.executable,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "-",
        ]
        executable = shutil.which(self.executable)
        if executable is None and pathlib.Path(self.executable).suffix == "":
            executable = shutil.which(f"{self.executable}.cmd")
        if executable is None:
            raise RuntimeError(f"Codex CLI not found: {self.executable}")
        command[0] = executable
        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            timeout=self.timeout,
        )
        payload = self._extract_json(result.stdout)
        ranked_by_id = self._validate(payload, candidates, profile)
        ranked = []
        for candidate in candidates:
            item = ranked_by_id[candidate.paper.id]
            ranked.append(
                RankedPaper(
                    paper=candidate.paper,
                    section=item["section"],
                    score=item["score"],
                    reason=item["reason"],
                    matched_terms=candidate.matched_terms,
                )
            )
        ranked.sort(key=lambda item: (item.score, item.paper.published), reverse=True)
        return ranked

    @staticmethod
    def _build_prompt(candidates: list[RankedPaper], profile: Profile) -> str:
        interests = [
            {
                "id": interest.id,
                "description": interest.description,
                "include": interest.include,
                "exclude": interest.exclude,
            }
            for interest in profile.interests
        ]
        papers = [
            {
                "id": candidate.paper.id,
                "title": candidate.paper.title,
                "abstract": candidate.paper.abstract,
                "authors": candidate.paper.authors,
                "categories": candidate.paper.categories,
                "recall_section": candidate.section,
                "recall_score": candidate.score,
            }
            for candidate in candidates
        ]
        return (
            "Rank the papers against the research interests. Return only a JSON array with exactly one item per paper. "
            "Each item must contain id (string), section (one supplied interest id), score (integer 0-100), and "
            f"reason (one concise {profile.language} sentence).\n\nInterests:\n"
            f"{json.dumps(interests, ensure_ascii=False, indent=2)}\n\nPapers:\n"
            f"{json.dumps(papers, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def _extract_json(output: str) -> object:
        start = output.find("[")
        end = output.rfind("]")
        if start < 0 or end < start:
            raise ValueError("Codex output does not contain a JSON array")
        return json.loads(output[start : end + 1])

    @staticmethod
    def _validate(payload: object, candidates: list[RankedPaper], profile: Profile) -> dict[str, dict]:
        if not isinstance(payload, list):
            raise ValueError("Codex ranking must be a JSON array")
        expected_ids = {candidate.paper.id for candidate in candidates}
        sections = {interest.id for interest in profile.interests}
        validated = {}
        for item in payload:
            if not isinstance(item, dict) or set(item) != {"id", "section", "score", "reason"}:
                raise ValueError("Codex ranking item has an invalid schema")
            if item["id"] not in expected_ids or item["id"] in validated:
                raise ValueError("Codex ranking contains an unknown or duplicate paper id")
            if item["section"] not in sections:
                raise ValueError("Codex ranking contains an unknown section")
            if not isinstance(item["score"], int) or not 0 <= item["score"] <= 100:
                raise ValueError("Codex ranking score must be an integer from 0 to 100")
            if not isinstance(item["reason"], str) or not item["reason"].strip():
                raise ValueError("Codex ranking reason must be a non-empty string")
            validated[item["id"]] = item
        if set(validated) != expected_ids:
            raise ValueError("Codex ranking does not contain every candidate")
        return validated
