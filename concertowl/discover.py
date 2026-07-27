"""自动发现关注歌手的场次（全国），写入 Watchlist，并追加时序价格观测。"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Dict, List, Tuple

from .config import active_artists, match_artist, match_city
from .models import WatchEvent
from .mtl_api import LOCATION_IDS, MoreTicketsClient, MtlShow
from .mtl_cn_api import MtlChinaClient
from .piaoniu_api import PiaoniuActivity, PiaoniuClient
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
    match = re.search(
        r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})",
        show_date,
    )
    if match:
        year, month, day = (int(part) for part in match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}T19:00"
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


def _plain_city(value: str) -> str:
    hit = match_city(value or "")
    if hit:
        return hit.name
    return (
        (value or "")
        .strip()
        .replace("中国香港", "香港")
        .replace("中国澳门", "澳门")
        .replace("香港特别行政区", "香港")
        .replace("澳门特别行政区", "澳门")
    )


def _event_date(event: WatchEvent) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", event.show_datetime or "")
    return match.group(0) if match else ""


def _match_piaoniu(
    event: WatchEvent, candidates: List[PiaoniuActivity]
) -> PiaoniuActivity | None:
    """只在「同歌手、同城、日期落在活动区间」唯一命中时自动绑定。"""
    target_date = _event_date(event)
    target_city = _plain_city(event.city)
    if not target_date or not target_city or target_city == "未知":
        return None

    matched: List[PiaoniuActivity] = []
    for item in candidates:
        if item.proxy_buy or _plain_city(item.city) != target_city:
            continue
        if not item.start_date:
            continue
        end_date = item.end_date or item.start_date
        if item.start_date <= target_date <= end_date:
            matched.append(item)
    return matched[0] if len(matched) == 1 else None


def attach_piaoniu_urls(
    pairs: List[Tuple[WatchEvent, MtlShow]], client: PiaoniuClient
) -> List[Tuple[WatchEvent, MtlShow]]:
    """按歌手批量发现候选，再用城市和日期安全关联到摩天轮场次。"""
    by_artist: Dict[str, List[PiaoniuActivity]] = {}
    for artist_name in sorted({ev.artist for ev, _ in pairs if ev.artist}):
        print(f"[discover] 票牛搜索 {artist_name}…")
        by_artist[artist_name] = client.search_artist(artist_name)

    out: List[Tuple[WatchEvent, MtlShow]] = []
    linked = 0
    for event, show in pairs:
        activity = _match_piaoniu(
            event, by_artist.get(event.artist) or []
        )
        if activity:
            event = replace(event, piaoniu_url=activity.web_url)
            linked += 1
            print(
                f"[discover] 票牛关联 {event.artist}@{event.city}: "
                f"{activity.activity_id} {activity.name}"
            )
        out.append((event, show))
    print(f"[discover] 票牛自动关联 {linked}/{len(pairs)} 场")
    return out


def discover_shows(
    client: MoreTicketsClient,
    cn_client: MtlChinaClient,
    piaoniu_client: PiaoniuClient,
) -> List[Tuple[WatchEvent, MtlShow]]:
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
        print(f"[discover] 国内摩天轮搜索 {art.name}…")
        for show in cn_client.search(art.name):
            hit = match_artist(show.title, active_only=True)
            if not hit or hit.name != art.name:
                continue
            ev = _to_event(show, art.name, _city_label(show))
            found[ev.event_id] = (ev, show)

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

    return attach_piaoniu_urls(list(found.values()), piaoniu_client)


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
                source=(
                    "motianlun_cn"
                    if "motianlun.cn" in show.web_url
                    else "moretickets"
                ),
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
    cn_client = MtlChinaClient()
    piaoniu_client = PiaoniuClient()
    pairs = discover_shows(client, cn_client, piaoniu_client)
    events = [ev for ev, _ in pairs]
    added, updated, total = upsert_watchlist(storage, events)
    print(f"[discover] Watchlist 现有 {total} 场（新增 {added}，更新 {updated}）")
    for ev, show in pairs:
        price = show.min_price if show.min_price is not None else "-"
        print(f"  - {ev.artist} @ {ev.city}: {ev.tour} min={price} {show.currency}")
    if also_snapshot:
        n = write_snapshots(storage, pairs)
        print(f"[discover] 写入 {n} 条时序观测")
    else:
        print("[discover] 跳过快照写入（交给后续 collect）")
    return 0


if __name__ == "__main__":
    import os

    # Actions 里紧接着会跑 collect，默认跳过发现阶段写快照，降低 Sheets 限流。
    also = os.environ.get("CONCERTOWL_DISCOVER_SNAPSHOT", "1") == "1"
    raise SystemExit(run(also_snapshot=also))
