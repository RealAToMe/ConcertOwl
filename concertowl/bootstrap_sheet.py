"""Initialize repository metadata for a new data branch."""
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
    if hasattr(storage, "data_root"):
        from .repo_history import rebuild_latest

        rebuild_latest(storage.data_root)
    print("[bootstrap] 完成：仓库元数据、价格目录与 latest 索引")


if __name__ == "__main__":
    main()
