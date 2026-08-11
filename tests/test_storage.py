from __future__ import annotations

from paper_rec.storage import Storage


def test_delivery_state_is_tracked_per_channel(tmp_path) -> None:
    storage = Storage(tmp_path / "state.sqlite3")
    storage.start_run("run-1", "profile")
    storage.record_delivery("profile", "primary", "run-1", ["paper-1"])

    assert storage.delivered_ids_for_channel("profile", "primary") == {"paper-1"}
    assert storage.delivered_ids_for_channel("profile", "secondary") == set()
    assert storage.delivered_ids("profile", ("primary", "secondary")) == set()

    storage.record_delivery("profile", "secondary", "run-1", ["paper-1"])

    assert storage.delivered_ids("profile", ("primary", "secondary")) == {"paper-1"}
    storage.close()

