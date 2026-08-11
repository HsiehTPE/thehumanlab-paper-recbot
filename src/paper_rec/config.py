from __future__ import annotations

import dataclasses
import os
import pathlib
from typing import Any

import yaml


class ConfigError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class InterestConfig:
    id: str
    label: str
    description: str
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    limit: int = 5
    weight: int = 1


@dataclasses.dataclass(frozen=True)
class ArxivConfig:
    categories: tuple[str, ...]
    hours: int = 72
    max_results: int = 200


@dataclasses.dataclass(frozen=True)
class SelectionConfig:
    ranker: str = "heuristic"
    recall_limit: int = 60
    minimum_score: int = 55
    max_items: int = 10


@dataclasses.dataclass(frozen=True)
class DeliveryConfig:
    channels: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Profile:
    id: str
    title: str
    language: str
    interests: tuple[InterestConfig, ...]
    arxiv: ArxivConfig
    selection: SelectionConfig
    delivery: DeliveryConfig


@dataclasses.dataclass(frozen=True)
class ChannelConfig:
    id: str
    type: str
    webhook_env: str


@dataclasses.dataclass(frozen=True)
class AppConfig:
    state_dir: pathlib.Path
    output_dir: pathlib.Path
    channels: dict[str, ChannelConfig]


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{context} must be a mapping")
    return value


def _non_empty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{context} must be a non-empty string")
    return value.strip()


def _string_tuple(value: Any, context: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "a list" if allow_empty else "a non-empty list"
        raise ConfigError(f"{context} must be {qualifier} of strings")
    return tuple(_non_empty_string(item, context) for item in value)


def _positive_int(value: Any, context: str, default: int) -> int:
    resolved = default if value is None else value
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved <= 0:
        raise ConfigError(f"{context} must be a positive integer")
    return resolved


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"configuration file not found: {path}")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigError(f"invalid YAML in {path}: {error}") from error
    return _mapping(value, str(path))


def load_profile(path: pathlib.Path) -> Profile:
    raw = load_yaml(path)
    source = _mapping(raw.get("sources"), "sources")
    arxiv_raw = _mapping(source.get("arxiv"), "sources.arxiv")
    selection_raw = _mapping(raw.get("selection", {}), "selection")
    delivery_raw = _mapping(raw.get("delivery", {}), "delivery")
    interests_raw = raw.get("interests")
    if not isinstance(interests_raw, list) or not interests_raw:
        raise ConfigError("interests must be a non-empty list")

    interests = []
    interest_ids = set()
    for index, value in enumerate(interests_raw):
        item = _mapping(value, f"interests[{index}]")
        interest_id = _non_empty_string(item.get("id"), f"interests[{index}].id")
        if interest_id in interest_ids:
            raise ConfigError(f"duplicate interest id: {interest_id}")
        interest_ids.add(interest_id)
        interests.append(
            InterestConfig(
                id=interest_id,
                label=_non_empty_string(item.get("label"), f"interests[{index}].label"),
                description=_non_empty_string(item.get("description"), f"interests[{index}].description"),
                include=_string_tuple(item.get("include"), f"interests[{index}].include"),
                exclude=_string_tuple(item.get("exclude", []), f"interests[{index}].exclude", allow_empty=True),
                limit=_positive_int(item.get("limit"), f"interests[{index}].limit", 5),
                weight=_positive_int(item.get("weight"), f"interests[{index}].weight", 1),
            )
        )

    ranker = selection_raw.get("ranker", "heuristic")
    if ranker not in {"heuristic", "codex"}:
        raise ConfigError("selection.ranker must be heuristic or codex")
    profile = Profile(
        id=_non_empty_string(raw.get("id"), "id"),
        title=_non_empty_string(raw.get("title"), "title"),
        language=_non_empty_string(raw.get("language", "zh-CN"), "language"),
        interests=tuple(interests),
        arxiv=ArxivConfig(
            categories=_string_tuple(arxiv_raw.get("categories"), "sources.arxiv.categories"),
            hours=_positive_int(arxiv_raw.get("hours"), "sources.arxiv.hours", 72),
            max_results=_positive_int(arxiv_raw.get("max_results"), "sources.arxiv.max_results", 200),
        ),
        selection=SelectionConfig(
            ranker=ranker,
            recall_limit=_positive_int(selection_raw.get("recall_limit"), "selection.recall_limit", 60),
            minimum_score=_positive_int(selection_raw.get("minimum_score"), "selection.minimum_score", 55),
            max_items=_positive_int(selection_raw.get("max_items"), "selection.max_items", 10),
        ),
        delivery=DeliveryConfig(
            channels=_string_tuple(delivery_raw.get("channels", []), "delivery.channels", allow_empty=True)
        ),
    )
    if profile.selection.minimum_score > 100:
        raise ConfigError("selection.minimum_score cannot exceed 100")
    return profile


def load_app_config(path: pathlib.Path, root: pathlib.Path) -> AppConfig:
    raw = load_yaml(path)
    storage = _mapping(raw.get("storage", {}), "storage")
    channels_raw = raw.get("channels", [])
    if not isinstance(channels_raw, list):
        raise ConfigError("channels must be a list")
    channels = {}
    for index, value in enumerate(channels_raw):
        item = _mapping(value, f"channels[{index}]")
        channel = ChannelConfig(
            id=_non_empty_string(item.get("id"), f"channels[{index}].id"),
            type=_non_empty_string(item.get("type"), f"channels[{index}].type"),
            webhook_env=_non_empty_string(item.get("webhook_env"), f"channels[{index}].webhook_env"),
        )
        if channel.type != "feishu":
            raise ConfigError(f"unsupported channel type: {channel.type}")
        if channel.id in channels:
            raise ConfigError(f"duplicate channel id: {channel.id}")
        channels[channel.id] = channel

    def resolve_path(value: Any, default: str) -> pathlib.Path:
        configured = pathlib.Path(_non_empty_string(value or default, "storage path"))
        return configured if configured.is_absolute() else root / configured

    return AppConfig(
        state_dir=resolve_path(storage.get("state_dir"), "state"),
        output_dir=resolve_path(storage.get("output_dir"), "output"),
        channels=channels,
    )


def validate_profile_channels(profile: Profile, app: AppConfig) -> None:
    unknown = sorted(set(profile.delivery.channels) - set(app.channels))
    if unknown:
        raise ConfigError(f"profile references unknown channels: {', '.join(unknown)}")


def apply_environment_overrides(profile: Profile) -> Profile:
    ranker = os.environ.get("PAPER_REC_RANKER", "").strip()
    if not ranker:
        return profile
    if ranker not in {"heuristic", "codex"}:
        raise ConfigError("PAPER_REC_RANKER must be heuristic or codex")
    selection = dataclasses.replace(profile.selection, ranker=ranker)
    return dataclasses.replace(profile, selection=selection)
