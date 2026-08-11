from __future__ import annotations

import json
import pathlib
import sqlite3
from datetime import datetime, timezone

from paper_rec.models import RankedPaper


class Storage:
    def __init__(self, path: pathlib.Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS papers (
                source TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (source, paper_id)
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                profile_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                delivered_at TEXT NOT NULL,
                PRIMARY KEY (profile_id, channel_id, paper_id)
            );
            """
        )
        self.connection.commit()

    def start_run(self, run_id: str, profile_id: str) -> None:
        self.connection.execute(
            "INSERT INTO runs (id, profile_id, status, started_at) VALUES (?, ?, 'running', ?)",
            (run_id, profile_id, self._now()),
        )
        self.connection.commit()

    def finish_run(self, run_id: str, status: str, error: str | None = None) -> None:
        self.connection.execute(
            "UPDATE runs SET status = ?, finished_at = ?, error = ? WHERE id = ?",
            (status, self._now(), error, run_id),
        )
        self.connection.commit()

    def save_papers(self, papers: list[RankedPaper]) -> None:
        for ranked in papers:
            paper = ranked.paper
            self.connection.execute(
                "INSERT OR REPLACE INTO papers (source, paper_id, payload) VALUES (?, ?, ?)",
                (paper.source, paper.id, json.dumps(paper.__dict__, ensure_ascii=False)),
            )
        self.connection.commit()

    def delivered_ids(self, profile_id: str, channel_ids: tuple[str, ...]) -> set[str]:
        if not channel_ids:
            return set()
        placeholders = ",".join("?" for _ in channel_ids)
        rows = self.connection.execute(
            f"SELECT paper_id, COUNT(DISTINCT channel_id) AS channel_count FROM deliveries "
            f"WHERE profile_id = ? AND channel_id IN ({placeholders}) GROUP BY paper_id",
            (profile_id, *channel_ids),
        )
        return {row["paper_id"] for row in rows if row["channel_count"] == len(channel_ids)}

    def delivered_ids_for_channel(self, profile_id: str, channel_id: str) -> set[str]:
        rows = self.connection.execute(
            "SELECT paper_id FROM deliveries WHERE profile_id = ? AND channel_id = ?",
            (profile_id, channel_id),
        )
        return {row["paper_id"] for row in rows}

    def record_delivery(self, profile_id: str, channel_id: str, run_id: str, paper_ids: list[str]) -> None:
        with self.connection:
            self.connection.executemany(
                "INSERT OR IGNORE INTO deliveries "
                "(profile_id, channel_id, paper_id, run_id, delivered_at) VALUES (?, ?, ?, ?, ?)",
                [(profile_id, channel_id, paper_id, run_id, self._now()) for paper_id in paper_ids],
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def close(self) -> None:
        self.connection.close()
