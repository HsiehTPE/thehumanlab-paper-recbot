from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
from typing import Any

import yaml

from paper_rec.config import ConfigError, load_profile, load_yaml
from paper_rec.models import Paper
from paper_rec.sources.arxiv import ArxivSource


def _base_paper_id(value: str) -> str:
    return re.sub(r"v\d+$", "", value)


def _resolve_executable(executable: str) -> str:
    resolved = shutil.which(executable)
    if resolved is None and pathlib.Path(executable).suffix == "":
        resolved = shutil.which(f"{executable}.cmd")
    if resolved is None:
        raise RuntimeError(
            f"Codex CLI not found: {executable}. Install/authenticate Codex or pass --codex with its executable path."
        )
    return resolved


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{context} must be a non-empty string")
    return value.strip()


def _read_seed_config(input_dir: pathlib.Path) -> tuple[dict[str, Any], pathlib.Path]:
    local_path = input_dir / "config.local.yaml"
    legacy_path = input_dir / "config.yaml"
    base_path = input_dir / "config.base.yaml"
    config_path = local_path if local_path.is_file() else legacy_path if legacy_path.is_file() else base_path
    if not config_path.is_file():
        raise ConfigError(
            f"seed config not found: create {local_path.name} from {base_path.name}"
        )
    raw = load_yaml(config_path)
    inherit = raw.get("inherit")
    if inherit:
        inherit_path = input_dir / _text(inherit, "inherit")
        if not inherit_path.is_file():
            raise ConfigError(f"inherited seed config not found: {inherit_path}")
        base = load_yaml(inherit_path)
        raw = _merge_config(base, raw)
    mode = raw.get("mode", "preserve")
    if mode not in {"rewrite", "preserve"}:
        raise ConfigError("customize mode must be rewrite or preserve")
    max_papers = raw.get("max_papers_per_interest", 5)
    if not isinstance(max_papers, int) or isinstance(max_papers, bool) or not 1 <= max_papers <= 5:
        raise ConfigError("max_papers_per_interest must be an integer from 1 to 5")
    interests = raw.get("interests")
    if not isinstance(interests, list) or not interests:
        raise ConfigError("customize interests must be a non-empty list")
    for index, item in enumerate(interests):
        if not isinstance(item, dict):
            raise ConfigError(f"interests[{index}] must be a mapping")
        _text(item.get("id"), f"interests[{index}].id")
        _text(item.get("label"), f"interests[{index}].label")
        links_value = item.get("links")
        if links_value is not None:
            if not isinstance(links_value, list) or not all(isinstance(link, str) for link in links_value):
                raise ConfigError(f"interests[{index}].links must be a list of strings")
            links = [link.strip() for link in links_value if link.strip()]
        else:
            source_file = _text(item.get("file"), f"interests[{index}].file")
            seed_path = input_dir / source_file
            if not seed_path.is_file():
                raise ConfigError(f"seed file not found: {seed_path}")
            links = [
                line.strip()
                for line in seed_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
        if not 1 <= len(links) <= max_papers:
            source_name = item.get("file", f"interests[{index}].links")
            raise ConfigError(f"{source_name} must contain 1-{max_papers} arXiv links")
        item["_links"] = links
    return raw, config_path


def _merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge a local seed config over its public base config."""
    merged = dict(base)
    for key, value in override.items():
        if key == "inherit":
            continue
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def _extract_json(output: str) -> object:
    start = output.find("{")
    end = output.rfind("}")
    if start < 0 or end < start:
        raise ValueError("customizer output does not contain a JSON object")
    return json.loads(output[start : end + 1])


def _build_prompt(raw: dict[str, Any], papers_by_interest: dict[str, list[Paper]], existing: dict[str, Any] | None) -> str:
    seeds = {
        interest_id: [
            {"id": paper.id, "title": paper.title, "abstract": paper.abstract, "categories": paper.categories}
            for paper in papers
        ]
        for interest_id, papers in papers_by_interest.items()
    }
    instruction = (
        "Rewrite the research interests from the seed papers. Return only a JSON object with an interests array. "
        "Each interest must contain id, label, description, include, exclude, limit, and weight. "
        "Keep each limit at most 5, use concise English keyword phrases in include/exclude, and do not invent papers."
    )
    if raw.get("mode", "preserve") == "preserve":
        instruction += " Preserve existing interests when relevant and supplement them using the seed papers."
    else:
        instruction += " Replace the existing interests entirely with the seed-based interests."
    return (
        f"{instruction}\nLanguage: {raw.get('language', 'zh-CN')}\n"
        f"Seed groups:\n{json.dumps(seeds, ensure_ascii=False, indent=2)}\n"
        f"Existing profile:\n{json.dumps(existing or {}, ensure_ascii=False, indent=2)}"
    )


def _validate_interests(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("interests"), list) or not payload["interests"]:
        raise ValueError("customizer must return a non-empty interests array")
    result = []
    ids = set()
    for item in payload["interests"]:
        if not isinstance(item, dict):
            raise ValueError("customizer interest must be an object")
        required = {"id", "label", "description", "include", "exclude", "limit", "weight"}
        if set(item) != required:
            raise ValueError("customizer interest has an invalid schema")
        if not all(isinstance(item[key], str) and item[key].strip() for key in ("id", "label", "description")):
            raise ValueError("customizer interest text fields are invalid")
        if item["id"] in ids:
            raise ValueError("customizer returned duplicate interest id")
        if not isinstance(item["include"], list) or not item["include"] or not all(isinstance(x, str) for x in item["include"]):
            raise ValueError("customizer include must be a non-empty string array")
        if not isinstance(item["exclude"], list) or not all(isinstance(x, str) for x in item["exclude"]):
            raise ValueError("customizer exclude must be a string array")
        if not isinstance(item["limit"], int) or not 1 <= item["limit"] <= 5:
            raise ValueError("customizer limit must be between 1 and 5")
        if not isinstance(item["weight"], int) or item["weight"] <= 0:
            raise ValueError("customizer weight must be positive")
        ids.add(item["id"])
        result.append(item)
    return result


def customize_profile(input_dir: pathlib.Path, target: pathlib.Path, executable: str = "codex") -> pathlib.Path:
    raw, _ = _read_seed_config(input_dir)
    source = ArxivSource()
    papers_by_interest: dict[str, list[Paper]] = {}
    all_ids = []
    for item in raw["interests"]:
        ids = [source.paper_id_from_url(link) for link in item["_links"]]
        all_ids.extend(ids)
        papers_by_interest[item["id"]] = []
    fetched = {_base_paper_id(paper.id): paper for paper in source.fetch_ids(all_ids)}
    missing = sorted({_base_paper_id(paper_id) for paper_id in all_ids} - set(fetched))
    if missing:
        raise RuntimeError(f"arXiv papers not found: {', '.join(missing)}")
    for item in raw["interests"]:
        papers_by_interest[item["id"]] = [
            fetched[_base_paper_id(source.paper_id_from_url(link))]
            for link in item["_links"]
        ]

    existing_raw = load_yaml(target) if target.exists() else None
    prompt = _build_prompt(raw, papers_by_interest, existing_raw)
    try:
        result = subprocess.run(
            [_resolve_executable(executable), "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", "-"],
            input=prompt,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "no error output").strip()
        raise RuntimeError(f"Codex CLI failed with exit code {error.returncode}: {detail}") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Codex CLI timed out after 300 seconds") from error
    generated = _validate_interests(_extract_json(result.stdout))
    output = dict(existing_raw or {})
    output.update({key: raw[key] for key in ("id", "title", "language") if key in raw})
    if "id" not in output:
        output["id"] = target.stem
    output.setdefault("title", "Research Digest")
    output.setdefault("language", "zh-CN")
    if raw.get("mode", "preserve") == "preserve" and existing_raw:
        generated_ids = {item["id"] for item in generated}
        generated.extend(
            item for item in existing_raw.get("interests", [])
            if isinstance(item, dict) and item.get("id") not in generated_ids
        )
    output["interests"] = generated
    if isinstance(output.get("selection"), dict):
        output["selection"] = dict(output["selection"])
        output["selection"].pop("ranker", None)
    labels = [item["label"] for item in generated if item.get("label")]
    output["title"] = f"{output['id']} 相关主题：{'、'.join(labels)}"
    output.setdefault("sources", {"arxiv": {"categories": ["cs.CV"]}})
    output.setdefault("selection", {})
    output.setdefault("delivery", {"channels": []})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(output, allow_unicode=True, sort_keys=False), encoding="utf-8")
    load_profile(target)
    return target
