from datetime import datetime

from concertowl.models import PriceSnapshot, WatchEvent
from concertowl.storage import RepoStorage
from concertowl.watchlist import WATCHLIST_HEADER, read_watchlist, upsert_watchlist


def event(piaoniu_url=""):
    return WatchEvent(
        event_id="event-1",
        artist="薛之谦",
        tour="天外来物",
        city="重庆",
        show_datetime="2026-08-07T19:30",
        piaoniu_url=piaoniu_url,
        active=True,
    )


def test_repo_storage_watchlist_preserves_manual_url(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCERTOWL_RUN_ID", "test-run")
    storage = RepoStorage(tmp_path)
    storage.ensure_sheet("Watchlist", WATCHLIST_HEADER)
    upsert_watchlist(storage, [event("https://x.piaoniu.com/activity/1")])
    upsert_watchlist(storage, [event("https://x.piaoniu.com/activity/2")])

    events, skipped = read_watchlist(storage)
    assert not skipped
    assert len(events) == 1
    assert events[0].piaoniu_url == "https://x.piaoniu.com/activity/1"


def test_repo_storage_reconstructs_artist_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCERTOWL_RUN_ID", "test-run")
    storage = RepoStorage(tmp_path)
    snap = PriceSnapshot(
        observed_at="2026-07-30T08:00",
        event_id="event-1",
        artist="薛之谦",
        observed_price=600,
        source="piaoniu",
    )
    assert storage.append_snapshots([snap]) == 1
    storage.finalize_run({"status": "success"})

    rows = storage.read_rows("价_薛之谦")
    assert len(rows) == 2
    assert rows[1][rows[0].index("observed_price")] == "600"
