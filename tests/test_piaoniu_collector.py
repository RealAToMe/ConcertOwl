from datetime import datetime, timedelta, timezone

from concertowl.collectors.piaoniu import PiaoniuCollector
from concertowl.models import WatchEvent


def _millis(value: str) -> int:
    zone = timezone(timedelta(hours=8))
    return int(datetime.fromisoformat(value).replace(tzinfo=zone).timestamp() * 1000)


def test_piaoniu_collects_only_the_linked_date_and_caches_requests(monkeypatch):
    collector = PiaoniuCollector(min_interval=0)
    calls = []
    sessions = [
        {"id": 101, "start": _millis("2026-08-08T20:15"), "specification": "8日"},
        {"id": 102, "start": _millis("2026-08-09T19:15"), "specification": "9日"},
    ]

    def fake_json(path, **kwargs):
        calls.append((path, kwargs.get("params")))
        if path.endswith("/780000.json"):
            return {"events": sessions}
        event_id = kwargs["params"]["eventId"]
        return [
            {
                "originPrice": 688,
                "lowPrice": 700 if event_id == "101" else 800,
                "hasTicket": True,
                "specification": "688",
            }
        ]

    monkeypatch.setattr(collector, "_json", fake_json)
    first = WatchEvent(
        event_id="mtl-first",
        artist="陈粒",
        city="香港",
        show_datetime="2026-08-08T19:00",
        piaoniu_url="https://x.piaoniu.com/activity/780000",
    )
    second = WatchEvent(
        event_id="mtl-second",
        artist="陈粒",
        city="香港",
        show_datetime="2026-08-09T19:00",
        piaoniu_url="https://x.piaoniu.com/activity/780000",
    )

    first_rows = collector.fetch(first)
    second_rows = collector.fetch(second)

    assert [row.show_datetime for row in first_rows] == ["2026-08-08T20:15"]
    assert [row.observed_price for row in first_rows] == [700]
    assert [row.show_datetime for row in second_rows] == ["2026-08-09T19:15"]
    assert [row.observed_price for row in second_rows] == [800]
    assert calls.count(("/api/v1/activities/780000.json", None)) == 1
    assert calls.count(
        ("/api/v1/ticketCategories.json", {"b2c": "true", "eventId": "101"})
    ) == 1
    assert calls.count(
        ("/api/v1/ticketCategories.json", {"b2c": "true", "eventId": "102"})
    ) == 1


def test_piaoniu_skips_ambiguous_activity_without_event_date(monkeypatch):
    collector = PiaoniuCollector(min_interval=0)
    monkeypatch.setattr(
        collector,
        "_json",
        lambda path, **kwargs: {
            "events": [
                {"id": 101, "start": _millis("2026-08-08T20:15")},
                {"id": 102, "start": _millis("2026-08-09T19:15")},
            ]
        },
    )
    event = WatchEvent(
        event_id="manual",
        artist="陈粒",
        piaoniu_url="https://x.piaoniu.com/activity/780000",
    )

    assert collector.fetch(event) == []
