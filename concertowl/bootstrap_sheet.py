"""初始化元数据表，并为每位 active 歌手建「价_歌手」空表。"""
from __future__ import annotations

from .config import active_artists, load_artists, load_cities
from .snapshots import ensure_artist_price_sheets
from .storage import get_storage
from .watchlist import WATCHLIST_HEADER

CITIES_HEADER = ["name", "region", "band", "aliases"]
ARTISTS_HEADER = ["name", "tier", "active", "aliases"]
ARTIST_PROFILES_HEADER = ["artist", "tier", "hist_premium_median", "soft_tendency", "note"]
DECISION_HEADER = [
    "event_id", "artist", "city", "show_datetime", "days_to_show",
    "latest_min", "latest_premium", "official_status",
    "抢票倾向", "等待降价倾向", "临场底价区间", "依据场次数", "置信度", "updated_at",
]


def seed_cities(storage) -> None:
    storage.ensure_sheet("Cities", CITIES_HEADER)
    rows = [CITIES_HEADER]
    for c in load_cities():
        rows.append([c.name, c.region, c.band, "/".join(c.aliases)])
    storage.overwrite("Cities", rows)


def seed_artists(storage) -> None:
    storage.ensure_sheet("Artists", ARTISTS_HEADER)
    rows = [ARTISTS_HEADER]
    for a in load_artists():
        rows.append([a.name, a.tier, "true" if a.active else "false", "/".join(a.aliases)])
    storage.overwrite("Artists", rows)


def main() -> None:
    storage = get_storage()
    seed_cities(storage)
    seed_artists(storage)
    storage.ensure_sheet("Watchlist", WATCHLIST_HEADER)
    storage.ensure_sheet("ArtistProfiles", ARTIST_PROFILES_HEADER)
    storage.ensure_sheet("Decision", DECISION_HEADER)
    ensure_artist_price_sheets(storage, [a.name for a in active_artists()])
    print("[bootstrap] 完成：Cities / Artists / Watchlist / 价_* / ArtistProfiles / Decision")
    print("[bootstrap] 说明：旧的 PriceSnapshots 大表可手动删除；新观测写入「价_歌手名」。")


if __name__ == "__main__":
    main()
