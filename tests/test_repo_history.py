from datetime import datetime

from concertowl.models import PriceSnapshot
from concertowl.repo_history import (
    RepoHistory,
    iter_observations,
    iter_run_manifests,
    observation_series_key,
)


def snapshot(price=600, observed_at="2026-07-30T08:00"):
    return PriceSnapshot(
        observed_at=observed_at,
        event_id="event-1",
        artist="薛之谦",
        city="重庆",
        show_datetime="2026-08-07T19:30",
        face_price=517,
        observed_price=price,
        currency="CNY",
        source="piaoniu",
        status="在售",
        note="activity=1 session=2 tier=517看台",
    )


def test_change_only_and_daily_heartbeat(tmp_path):
    first = RepoHistory(
        tmp_path, run_id="run-1", now=datetime(2026, 7, 30, 8)
    )
    assert first.record([snapshot()]) == 1
    assert first.finalize()["changes"] == 1

    same_day = RepoHistory(
        tmp_path, run_id="run-2", now=datetime(2026, 7, 30, 14)
    )
    assert same_day.record([snapshot(observed_at="2026-07-30T14:00")]) == 0
    manifest = same_day.finalize()
    assert manifest["unchanged"] == 1
    assert not (tmp_path / "prices/2026/07/30/run-2.jsonl").exists()

    next_day = RepoHistory(
        tmp_path, run_id="run-3", now=datetime(2026, 7, 31, 8)
    )
    assert next_day.record([snapshot(observed_at="2026-07-31T08:00")]) == 1
    assert next_day.finalize()["heartbeats"] == 1

    changed = RepoHistory(
        tmp_path, run_id="run-4", now=datetime(2026, 7, 31, 14)
    )
    assert changed.record([snapshot(580, "2026-07-31T14:00")]) == 1
    assert changed.finalize()["changes"] == 1

    records = list(iter_observations(tmp_path))
    assert [row["record_kind"] for row in records] == [
        "initial",
        "heartbeat",
        "change",
    ]
    assert len(list(iter_run_manifests(tmp_path))) == 4


def test_finalize_is_idempotent(tmp_path):
    history = RepoHistory(
        tmp_path, run_id="same-run", now=datetime(2026, 7, 30, 8)
    )
    history.record([snapshot()])
    first = history.finalize()

    replay = RepoHistory(
        tmp_path, run_id="same-run", now=datetime(2026, 7, 30, 9)
    )
    replay.record([snapshot(700, "2026-07-30T09:00")])
    second = replay.finalize()

    assert first["records_written"] == 1
    assert second["idempotent_replay"] is True
    assert len(list(iter_observations(tmp_path))) == 1


def test_series_key_distinguishes_ticket_tiers():
    a = snapshot()
    b = snapshot()
    b.note = "activity=1 session=2 tier=517内场"
    assert observation_series_key(a.__dict__) != observation_series_key(b.__dict__)


def test_nonpositive_prices_are_not_persisted(tmp_path):
    history = RepoHistory(
        tmp_path, run_id="zero", now=datetime(2026, 7, 30, 8)
    )
    assert history.record([snapshot(0)]) == 0
    manifest = history.finalize()
    assert manifest["records_written"] == 0
