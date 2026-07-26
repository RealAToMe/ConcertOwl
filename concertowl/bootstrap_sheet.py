"""初始化各 Sheet 表头，并把 Cities / Artists 白名单同步进表。

用法：
  python -m concertowl.bootstrap_sheet
Dry-run（本地 CSV，无需凭证）：
  CONCERTOWL_DRYRUN=1 python -m concertowl.bootstrap_sheet
"""
from __future__ import annotations

from .config import load_artists, load_cities
from .models import SNAPSHOT_HEADER
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
    storage.ensure_sheet("PriceSnapshots", SNAPSHOT_HEADER)
    storage.ensure_sheet("ArtistProfiles", ARTIST_PROFILES_HEADER)
    storage.ensure_sheet("Decision", DECISION_HEADER)
    print("[bootstrap] 完成：Cities / Artists / Watchlist / PriceSnapshots / ArtistProfiles / Decision")


if __name__ == "__main__":
    main()
