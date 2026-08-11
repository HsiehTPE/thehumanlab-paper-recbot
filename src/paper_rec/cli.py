from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from paper_rec.config import (
    ConfigError,
    apply_environment_overrides,
    load_app_config,
    load_profile,
    validate_profile_channels,
)
from paper_rec.customize import customize_profile
from paper_rec.pipeline import Pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-rec")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--config", type=pathlib.Path, default=pathlib.Path("config/app.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate application and profile configuration")
    validate.add_argument("--profile", type=pathlib.Path, required=True)

    run = commands.add_parser("run", help="run one profile")
    run.add_argument("--profile", type=pathlib.Path, required=True)
    run.add_argument("--skip-send", action="store_true")
    run.add_argument("--force-send", action="store_true", help="send selected papers even if already delivered")

    customize = commands.add_parser("customize", help="build a profile from categorized arXiv seed links")
    customize.add_argument(
        "--input",
        type=pathlib.Path,
        required=True,
        help="directory containing config.base.yaml/config.local.yaml",
    )
    customize.add_argument("--target", type=pathlib.Path, help="profile YAML to write")
    customize.add_argument("--codex", default="codex", help="Codex executable")
    return parser


def resolve(root: pathlib.Path, path: pathlib.Path) -> pathlib.Path:
    return path if path.is_absolute() else root / path


def load_dotenv(path: pathlib.Path) -> None:
    """Load simple KEY=VALUE entries without overriding existing variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def main() -> None:
    args = build_parser().parse_args()
    root = args.root.resolve()
    try:
        load_dotenv(root / ".env")
        if args.command == "customize":
            input_dir = resolve(root, args.input)
            target = resolve(root, args.target) if args.target else input_dir.parent / "research.yaml"
            output = customize_profile(input_dir, target, executable=args.codex)
            print(f"wrote profile: {output}")
            return
        app = load_app_config(resolve(root, args.config), root)
        profile = apply_environment_overrides(load_profile(resolve(root, args.profile)))
        validate_profile_channels(profile, app)
        if args.command == "validate":
            print(f"valid profile: {profile.id}")
            return
        result = Pipeline(app).run(profile, skip_send=args.skip_send, force_send=args.force_send)
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    except ConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
