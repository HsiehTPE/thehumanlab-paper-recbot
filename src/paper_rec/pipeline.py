from __future__ import annotations

import os
import pathlib
import uuid
from datetime import datetime, timezone

from paper_rec.channels.feishu import FeishuChannel
from paper_rec.config import AppConfig, ConfigError, Profile
from paper_rec.editor import CodexDigestEditor
from paper_rec.models import RunResult
from paper_rec.pdf import PdfEnricher
from paper_rec.rankers import CodexRanker, HeuristicRanker
from paper_rec.recall import recall
from paper_rec.render import render_markdown
from paper_rec.sources.arxiv import ArxivSource
from paper_rec.storage import Storage


class Pipeline:
    def __init__(self, app: AppConfig, source: ArxivSource | None = None) -> None:
        self.app = app
        self.source = source or ArxivSource()

    def run(self, profile: Profile, *, skip_send: bool = False, force_send: bool = False) -> RunResult:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        storage = Storage(self.app.state_dir / "paper-rec.sqlite3")
        storage.start_run(run_id, profile.id)
        try:
            fetched = self.source.fetch(profile.arxiv, profile.interests)
            candidates = recall(fetched, profile)
            ranker = CodexRanker() if profile.selection.ranker == "codex" else HeuristicRanker()
            ranked = ranker.rank(candidates, profile)
            storage.save_papers(ranked)
            active_channels = () if skip_send else profile.delivery.channels
            delivered = set() if force_send else storage.delivered_ids(profile.id, active_channels)
            unseen = [item for item in ranked if item.paper.id not in delivered]
            selected = self._select(unseen, profile)
            selected = PdfEnricher().enrich(selected)
            digest = self._render(profile, selected)
            output_path = self._write_output(profile, run_id, digest.content)
            deliveries = {}
            for channel_id in active_channels:
                channel = self.app.channels[channel_id]
                webhook = os.environ.get(channel.webhook_env)
                if not webhook:
                    raise ConfigError(f"missing environment variable: {channel.webhook_env}")
                channel_delivered = set() if force_send else storage.delivered_ids_for_channel(profile.id, channel_id)
                channel_papers = [item for item in selected if item.paper.id not in channel_delivered]
                if not channel_papers:
                    deliveries[channel_id] = "up-to-date"
                    continue
                channel_digest = self._render(profile, channel_papers)
                FeishuChannel(webhook).send(channel_digest.content)
                storage.record_delivery(
                    profile.id,
                    channel_id,
                    run_id,
                    [item.paper.id for item in channel_papers],
                )
                deliveries[channel_id] = "sent"
            storage.finish_run(run_id, "succeeded")
            return RunResult(
                run_id=run_id,
                fetched_count=len(fetched),
                candidate_count=len(candidates),
                selected_count=len(selected),
                output_path=str(output_path),
                deliveries=deliveries,
            )
        except Exception as error:
            storage.finish_run(run_id, "failed", str(error))
            raise
        finally:
            storage.close()

    @staticmethod
    def _select(ranked, profile: Profile):
        selected = []
        for interest in profile.interests:
            section = [
                item
                for item in ranked
                if item.section == interest.id and item.score >= profile.selection.minimum_score
            ]
            selected.extend(section[: interest.limit])
        selected.sort(key=lambda item: (item.score, item.paper.published), reverse=True)
        return selected[: profile.selection.max_items]

    @staticmethod
    def _render(profile: Profile, papers):
        if profile.selection.ranker == "codex":
            return CodexDigestEditor().render(profile, papers)
        return render_markdown(profile, papers)

    def _write_output(self, profile: Profile, run_id: str, content: str) -> pathlib.Path:
        profile_dir = self.app.output_dir / profile.id
        profile_dir.mkdir(parents=True, exist_ok=True)
        output_path = profile_dir / f"{run_id}.md"
        output_path.write_text(content, encoding="utf-8")
        (profile_dir / "latest.md").write_text(content, encoding="utf-8")
        return output_path
