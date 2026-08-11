from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

from paper_rec.config import Profile
from paper_rec.models import Digest, RankedPaper


class CodexDigestEditor:
    def __init__(self, executable: str = "codex", timeout: int = 300) -> None:
        self.executable = executable
        self.timeout = timeout

    def render(self, profile: Profile, papers: list[RankedPaper]) -> Digest:
        executable = shutil.which(self.executable)
        if executable is None and pathlib.Path(self.executable).suffix == "":
            executable = shutil.which(f"{self.executable}.cmd")
        if executable is None:
            raise RuntimeError(f"Codex CLI not found: {self.executable}")

        result = subprocess.run(
            [executable, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", "-"],
            input=self._prompt(profile, papers),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            timeout=self.timeout,
        )
        content = self._normalize(result.stdout)
        return Digest(profile.id, profile.title, content, tuple(papers))

    def _prompt(self, profile: Profile, papers: list[RankedPaper]) -> str:
        sections = "\n".join(
            f"{index}. {interest.id}: {interest.label} — {interest.description}"
            for index, interest in enumerate(profile.interests, 1)
        )
        items = []
        for paper in papers:
            items.append(
                {
                    "id": paper.paper.id,
                    "title": paper.paper.title,
                    "url": paper.paper.url,
                    "project_url": paper.paper.project_url,
                    "authors": paper.paper.authors,
                    "published": paper.paper.published[:10],
                    "abstract": paper.paper.abstract,
                    "categories": paper.paper.categories,
                    "institutions": paper.paper.institutions,
                    "code_links": paper.paper.code_links,
                    "code_status": paper.paper.code_status,
                    "section": paper.section,
                    "score": paper.score,
                    "matched_terms": paper.matched_terms,
                }
            )
        return f"""你是研究论文日报编辑。请用中文输出一份高质量 Markdown-free 纯文本日报。

必须严格遵守以下格式：

今日论文速递

然后按照以下方向依次输出，每个方向标题为“第N部分：<label>”：
{sections}

每篇论文严格使用以下字段：
N. <title>
【Paper】
<url>
【Project】
<project_url，如果没有则省略这两行>
【Authors】
<authors>
【Institutions】
<每个机构单独一行，格式为“1. <机构>”；从1开始且序号不得重复；如果为空则写“未获取到作者机构信息”>
【Code】
<代码仓库链接；只有输入数据中存在代码仓库链接时才输出这两行，没有链接时省略，不要猜测或补充链接>
【Published】
<date>
【Tags】
<comma-separated tags>
【摘要】
<2-3句准确的中文摘要，不要编造原文没有的信息>
【值得关注】
<1-2句说明方法、实验或应用价值>

所有字段标签必须单独占一行，内容从下一行开始。不要把内容写在标签同一行。

每个方向从1重新编号。没有论文的方向保留标题，并写“今天没有特别值得关注的新论文。”
最后写一行“今日趋势: <1-2句总结>”。不要使用 #、*、代码块或额外解释。

Profile title: {profile.title}
Papers JSON:
{self._json(items)}
"""

    @staticmethod
    def _json(value: object) -> str:
        import json

        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _normalize(content: str) -> str:
        lines = [line.rstrip() for line in content.splitlines()]
        lines = [line for line in lines if not line.strip().startswith("```")]
        replacements = {
            "[Link]": "【Paper】",
            "[Paper]": "【Paper】",
            "[Project]": "【Project】",
            "[Code]": "【Code】",
            "[Authors]": "【Authors】",
            "[Institutions]": "【Institutions】",
            "[Open Source]": "【Open Source】",
            "[Published]": "【Published】",
            "[Tags]": "【Tags】",
            "[摘要]": "【摘要】",
            "[值得关注]": "【值得关注】",
        }
        for index, line in enumerate(lines):
            for old, new in replacements.items():
                lines[index] = lines[index].replace(old, new)
            lines[index] = lines[index].replace("**", "")
        normalized: list[str] = []
        for line in lines:
            match = re.match(r"^(【[^】]+】)\s+(.+)$", line)
            if match:
                normalized.extend([match.group(1), match.group(2)])
            else:
                normalized.append(line)
        return "\n".join(normalized).strip() + "\n"
