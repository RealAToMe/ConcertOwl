"""读取 Watchlist 表，转成 WatchEvent，并按白名单校验。"""
from __future__ import annotations

from typing import List, Tuple

from .config import match_artist, match_city
from .models import WatchEvent
from .storage import Storage

WATCHLIST_HEADER = [
    "event_id", "artist", "tour", "city", "region", "venue",
    "show_datetime", "face_prices", "official_url", "secondary_url",
    "priority", "active",
]


def read_watchlist(storage: Storage) -> Tuple[List[WatchEvent], List[str]]:
    """返回 (在范围内的场次, 被跳过的原因说明)。"""
    rows = storage.read_rows("Watchlist")
    events: List[WatchEvent] = []
    skipped: List[str] = []
    if not rows:
        return events, skipped

    header = rows[0]
    idx = {name: header.index(name) for name in header}

    def cell(row, name):
        i = idx.get(name)
        if i is None or i >= len(row):
            return ""
        return (row[i] or "").strip()

    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue
        ev = WatchEvent(
            event_id=cell(row, "event_id"),
            artist=cell(row, "artist"),
            tour=cell(row, "tour"),
            city=cell(row, "city"),
            region=cell(row, "region"),
            venue=cell(row, "venue"),
            show_datetime=cell(row, "show_datetime"),
            face_prices=cell(row, "face_prices"),
            official_url=cell(row, "official_url"),
            secondary_url=cell(row, "secondary_url"),
            priority=cell(row, "priority") or "normal",
            active=(cell(row, "active").lower() not in ("false", "0", "no", "")),
        )
        if not ev.active:
            continue

        # 白名单硬校验
        if match_city(ev.city) is None:
            skipped.append(f"{ev.event_id or ev.artist}: 城市不在白名单({ev.city})")
            continue
        if match_artist(ev.artist) is None:
            skipped.append(f"{ev.event_id or ev.artist}: 歌手不在采集名单({ev.artist})")
            continue
        events.append(ev)

    return events, skipped
