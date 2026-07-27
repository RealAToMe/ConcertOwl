"""自动发现关注歌手的场次（全国），写入 Watchlist，并追加时序价格观测。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .config import active_artists, match_artist, match_city
from .models import WatchEvent
from .mtl_api import LOCATION_IDS, MoreTicketsClient, MtlShow
from .snapshots import append_observations, build_observation
from .storage import get_storage
from .watchlist import WATCHLIST_HEADER, upsert_watchlist


@dataclass
class CityLabel:
    name: str
    region: str = "CN"


def _normalize_show_datetime(show_date: str) -> str:
    if not show_date:
        return ""
    part = show_date.split("-")[0].strip().replace("/", "-")
    if len(part) >= 10:
        return part[:10] + "T19:00"
    return show_date


def _city_label(show: MtlShow) -> CityLabel:
    blob = " ".join([show.title, show.location, show.venue, show.show_code])
    hit = match_city(blob)
    if hit:
        return CityLabel(name=hit.name, region=hit.region)

    loc = (show.location or "").strip()
    if loc:
        name = loc.split(",")[0].strip() or loc
        region = "CN"
        low = loc.lower().replace(" ", "")
        if "hongkong" in low:
            name, region = "香港", "HK"
        elif "macau" in low or "macao" in low:
            name, region = "澳门", "MO"
        return CityLabel(name=name, region=region)

    code = (show.show_code or "").lower()
    for token, label, region in [
        ("hongkong", "香港", "HK"),
        ("macao", "澳门", "MO"),
        ("macau", "澳门", "MO"),
        ("shanghai", "上海", "CN"),
        ("beijing", "北京", "CN"),
        ("guangzhou", "广州", "CN"),
        ("shenzhen", "深圳", "CN"),
        ("hangzhou", "杭州", "CN"),
        ("nanjing", "南京", "CN"),
        ("suzhou", "苏州", "CN"),
        ("tianjin", "天津", "CN"),
    ]:
        if token in code:
            return CityLabel(name=label, region=region)

    m = re.search(r"\bin\s+([A-Za-z\u4e00-\u9fff ]+)$", show.title or "", re.I)
    if m:
        return CityLabel(name=m.group(1).strip(), region="CN")
    return CityLabel(name="未知", region="CN")


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

    for city_name, loc_id in LOCATION_IDS.items():
        print(f"[discover] 拉取 {city_name} 列表（仅作召回）…")
        for show in client.list_by_location(loc_id, max_pages=10):
            art = match_artist(show.title, active_only=True)
            if not art:
                continue
            ev = _to_event(show, art.name, _city_label(show))
            found[ev.event_id] = (ev, show)

    for art in active_artists():
        keywords = [art.name] + list(art.aliases)
        keywords = sorted({k for k in keywords if k}, key=len, reverse=True)
        for kw in keywords[:4]:
            print(f"[discover] 搜索 {art.name} / {kw}…")
            for show in client.search(kw):
                hit = match_artist(show.title, active_only=True)
                if not hit or hit.name != art.name:
                    continue
                ev = _to_event(show, art.name, _city_label(show))
                found[ev.event_id] = (ev, show)

    return list(found.values())


def _to_event(show: MtlShow, artist_name: str, city: CityLabel) -> WatchEvent:
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


def write_snapshots(storage, pairs: List[Tuple[WatchEvent, MtlShow]]) -> int:
    snaps = []
    for ev, show in pairs:
        if show.min_price is None:
            continue
        snaps.append(
            build_observation(
                ev,
                observed_price=show.min_price,
                face_price=None,
                source="moretickets",
                status=_status_cn(show.status),
                currency=show.currency or "",
                note=f"overall_min showId={show.show_id}",
            )
        )
    return append_observations(storage, snaps)


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
        print(f"[discover] 写入 {n} 条时序观测")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(also_snapshot=True))
