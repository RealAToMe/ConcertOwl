"""读取 / 写入 Watchlist。

观察期校验：只要求歌手在关注名单；城市可任意，用于以后分析加权。
"""
from __future__ import annotations

from typing import List, Tuple

from .config import match_artist
from .models import WatchEvent
from .storage import Storage

WATCHLIST_HEADER = [
    "event_id", "artist", "tour", "city", "region", "venue",
    "show_datetime", "face_prices", "official_url", "secondary_url",
    "priority", "active",
]


def _row_from_event(ev: WatchEvent) -> List[str]:
    return [
        ev.event_id,
        ev.artist,
        ev.tour,
        ev.city,
        ev.region,
        ev.venue,
        ev.show_datetime,
        ev.face_prices,
        ev.official_url,
        ev.secondary_url,
        ev.priority,
        "true" if ev.active else "false",
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
            active=(cell(row, "active").lower() not in ("false", "0", "no")),
        )
        if not ev.active:
            continue

        if match_artist(ev.artist) is None:
            skipped.append(f"{ev.event_id or ev.artist}: 歌手不在采集名单({ev.artist})")
            continue
        # 城市不作为采集过滤条件；偏好城市仅用于以后分析加权
        events.append(ev)

    return events, skipped


def upsert_watchlist(storage: Storage, events: List[WatchEvent]) -> Tuple[int, int, int]:
    """按 event_id 合并写入 Watchlist。返回 (新增, 更新, 总数)。"""
    storage.ensure_sheet("Watchlist", WATCHLIST_HEADER)
    existing_rows = storage.read_rows("Watchlist")
    by_id = {}
    extras = []

    if existing_rows:
        header = existing_rows[0]
        idx = {name: i for i, name in enumerate(header)}
        id_i = idx.get("event_id", 0)
        for row in existing_rows[1:]:
            if not any(str(c).strip() for c in row):
                continue
            eid = row[id_i].strip() if id_i < len(row) else ""
            if eid:
                by_id[eid] = row
            else:
                extras.append(row)

    added = updated = 0
    for ev in events:
        row = _row_from_event(ev)
        if ev.event_id in by_id:
            old = by_id[ev.event_id]
            if existing_rows:
                header = existing_rows[0]
                old_map = {
                    header[i]: (old[i] if i < len(old) else "")
                    for i in range(len(header))
                }
                if not ev.face_prices and old_map.get("face_prices"):
                    row[WATCHLIST_HEADER.index("face_prices")] = old_map["face_prices"]
                if not ev.official_url and old_map.get("official_url"):
                    row[WATCHLIST_HEADER.index("official_url")] = old_map["official_url"]
            by_id[ev.event_id] = row
            updated += 1
        else:
            by_id[ev.event_id] = row
            added += 1

    out = [WATCHLIST_HEADER] + list(by_id.values()) + extras
    storage.overwrite("Watchlist", out)
    return added, updated, len(by_id) + len(extras)
