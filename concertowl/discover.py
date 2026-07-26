"""自动发现白名单歌手在关注城市的场次，写入 Watchlist，并可选同时落一条价格快照。

当前主数据源：MoreTickets 国际站公开 API（覆盖港澳，并含部分大陆场次）。
大麦等反爬强的源留待后续适配。

用法：
  python -m concertowl.discover
  CONCERTOWL_DRYRUN=1 python -m concertowl.discover
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .config import active_artists, match_artist, match_city
from .models import SNAPSHOT_HEADER, PriceSnapshot, WatchEvent, days_between, now_local_iso
from .mtl_api import LOCATION_IDS, MoreTicketsClient, MtlShow
from .storage import Storage, get_storage
from .watchlist import WATCHLIST_HEADER, read_watchlist, upsert_watchlist


def _normalize_show_datetime(show_date: str) -> str:
    """把 '2026/08/08 - 2026/08/09' 收成起始日 ISO 日期。"""
    if not show_date:
        return ""
    part = show_date.split("-")[0].strip().replace("/", "-")
    # 已是 YYYY-MM-DD 或带时间
    if len(part) >= 10:
        return part[:10] + "T19:00"
    return show_date


def _city_from_show(show: MtlShow):
    blob = " ".join([show.title, show.location, show.venue, show.show_code])
    return match_city(blob)


def _artist_from_show(show: MtlShow):
    return match_artist(show.title)


def _status_cn(status: str) -> str:
    s = (status or "").upper()
    if s in ("ONSALE", "ON_SALE", "SALE"):
        return "在售"
    if s in ("SOLDOUT", "SOLD_OUT", "SOLD OUT"):
        return "售罄"
    if s in ("PENDING", "COMING"):
        return "预售/待开售"
    return status or "未知"


def discover_shows(client: MoreTicketsClient) -> List[Tuple[WatchEvent, MtlShow]]:
    found: Dict[str, Tuple[WatchEvent, MtlShow]] = {}

    # 1) 港澳全量列表（按 location），再按歌手白名单过滤 —— 召回更全
    for city_name, loc_id in LOCATION_IDS.items():
        print(f"[discover] 拉取 {city_name} 列表…")
        for show in client.list_by_location(loc_id, max_pages=10):
            art = _artist_from_show(show)
            city = _city_from_show(show) or match_city(city_name)
            if not art or not city:
                continue
            ev = _to_event(show, art.name, city)
            found[ev.event_id] = (ev, show)

    # 2) 按歌手搜索（覆盖上海等大陆城市挂在国际站的场次）
    for art in active_artists():
        keywords = [art.name] + list(art.aliases)
        # 优先较长关键词，减少模糊噪声
        keywords = sorted({k for k in keywords if k}, key=len, reverse=True)
        for kw in keywords[:4]:
            print(f"[discover] 搜索 {art.name} / {kw}…")
            for show in client.search(kw):
                hit_art = _artist_from_show(show)
                city = _city_from_show(show)
                if not hit_art or hit_art.name != art.name:
                    continue
                if not city:
                    continue
                ev = _to_event(show, art.name, city)
                found[ev.event_id] = (ev, show)

    return list(found.values())


def _to_event(show: MtlShow, artist_name: str, city) -> WatchEvent:
    return WatchEvent(
        event_id=show.event_id,
        artist=artist_name,
        tour=show.title,
        city=city.name,
        region=city.region,
        venue=show.venue,
        show_datetime=_normalize_show_datetime(show.show_date),
        face_prices="",
        official_url="",
        secondary_url=show.web_url,
        priority="auto",
        active=True,
    )


def write_snapshots(storage: Storage, pairs: List[Tuple[WatchEvent, MtlShow]]) -> int:
    rows = []
    for ev, show in pairs:
        snap = PriceSnapshot(
            ts=now_local_iso(),
            event_id=ev.event_id,
            source="moretickets",
            tier="最低挂牌",
            listed_min=show.min_price,
            listed_median=None,
            premium_ratio=None,
            days_to_show=days_between(ev.show_datetime),
            days_since_onsale=None,
            official_status=_status_cn(show.status),
            raw_note=f"discover {show.currency} showId={show.show_id}".strip(),
        )
        rows.append(snap.as_row(SNAPSHOT_HEADER))
    if rows:
        storage.ensure_sheet("PriceSnapshots", SNAPSHOT_HEADER)
        storage.append_rows("PriceSnapshots", rows)
    return len(rows)


def run(also_snapshot: bool = True) -> int:
    storage = get_storage()
    storage.ensure_sheet("Watchlist", WATCHLIST_HEADER)
    client = MoreTicketsClient()
    pairs = discover_shows(client)
    events = [ev for ev, _ in pairs]
    added, updated, total = upsert_watchlist(storage, events)
    print(f"[discover] Watchlist 现有 {total} 场（新增 {added}，更新 {updated}）")
    for ev, show in pairs:
        price = show.min_price if show.min_price is not None else "-"
        print(f"  - {ev.artist} @ {ev.city}: {ev.tour} min={price} {show.currency}")
    if also_snapshot:
        n = write_snapshots(storage, pairs)
        print(f"[discover] 写入 {n} 条价格快照")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(also_snapshot=True))
