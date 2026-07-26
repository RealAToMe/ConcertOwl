"""自动发现关注歌手的场次（全国，不限城市），写入 Watchlist，并落价格快照。

收录规则（观察期）：
- 只看歌手：`config/artists.yml` 里 active=true 命中即收录，城市不限。
- 城市列表（cities.yml）留给以后分析加权（例如「同城更可参考」），不参与采集过滤。

当前主数据源：MoreTickets 国际站公开 API。
大麦等反爬强的源留待后续适配。

用法：
  python -m concertowl.discover
  CONCERTOWL_DRYRUN=1 python -m concertowl.discover
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .config import active_artists, match_artist, match_city
from .models import SNAPSHOT_HEADER, PriceSnapshot, WatchEvent, days_between, now_local_iso
from .mtl_api import LOCATION_IDS, MoreTicketsClient, MtlShow
from .storage import Storage, get_storage
from .watchlist import WATCHLIST_HEADER, upsert_watchlist


@dataclass
class CityLabel:
    name: str
    region: str = "CN"


def _normalize_show_datetime(show_date: str) -> str:
    """把 '2026/08/08 - 2026/08/09' 收成起始日 ISO 日期。"""
    if not show_date:
        return ""
    part = show_date.split("-")[0].strip().replace("/", "-")
    if len(part) >= 10:
        return part[:10] + "T19:00"
    return show_date


def _city_label(show: MtlShow) -> CityLabel:
    """尽量识别城市；未命中偏好城市表时，仍用地点原文入库。"""
    blob = " ".join([show.title, show.location, show.venue, show.show_code])
    hit = match_city(blob)
    if hit:
        return CityLabel(name=hit.name, region=hit.region)

    loc = (show.location or "").strip()
    if loc:
        # "HongKong, CHINA" / "Guiyang, CHINA" / "Shanghai, CHINA"
        name = loc.split(",")[0].strip() or loc
        region = "CN"
        low = loc.lower()
        if "hongkong" in low.replace(" ", "") or "hong kong" in low:
            name, region = "香港", "HK"
        elif "macau" in low or "macao" in low:
            name, region = "澳门", "MO"
        return CityLabel(name=name, region=region)

    # 从英文 showCode 里抠城市词，如 chenli-hongkong-2026-concert
    code = (show.show_code or "").lower()
    for token, label, region in [
        ("hongkong", "香港", "HK"),
        ("hong-kong", "香港", "HK"),
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
    """歌手命中即收录（全国）。"""
    found: Dict[str, Tuple[WatchEvent, MtlShow]] = {}

    # 1) 港澳列表：只用来提高召回，仍以歌手白名单过滤（不因城市过滤掉其它城市）
    for city_name, loc_id in LOCATION_IDS.items():
        print(f"[discover] 拉取 {city_name} 列表（仅作召回）…")
        for show in client.list_by_location(loc_id, max_pages=10):
            art = match_artist(show.title, active_only=True)
            if not art:
                continue
            ev = _to_event(show, art.name, _city_label(show))
            found[ev.event_id] = (ev, show)

    # 2) 按关注歌手搜索：全国场次，城市不限
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


def _tier_snapshots(ev: WatchEvent, show: MtlShow) -> List[PriceSnapshot]:
    """按官方档位分行；若尚无分档数据，先记 overall，并保留 face_prices 占位行。

    目标结构：每一行 = 一个官方档位在某一时刻的挂牌情况。
    当面值档已知（face_prices=380/680/980）但二手接口暂只给总最低价时：
    - 写一条 overall_min 便于先攒走势
    - 再为每个面值档写一行（listed 为空），方便以后补齐分档挂牌
    """
    base_kwargs = dict(
        ts=now_local_iso(),
        event_id=ev.event_id,
        source="moretickets",
        days_to_show=days_between(ev.show_datetime),
        days_since_onsale=None,
        official_status=_status_cn(show.status),
    )
    note_prefix = f"{show.currency} showId={show.show_id}".strip()
    faces = _parse_faces(ev.face_prices)
    out: List[PriceSnapshot] = []

    # 总最低挂牌（API 目前稳定能拿到的）
    out.append(
        PriceSnapshot(
            **base_kwargs,
            tier="overall_min",
            face_price=None,
            listed_min=show.min_price,
            listed_median=None,
            premium_ratio=None,
            raw_note=f"discover {note_prefix}",
        )
    )

    for face in faces:
        prem = None
        # 尚无分档挂牌时 listed 留空；有了分档接口再填
        out.append(
            PriceSnapshot(
                **base_kwargs,
                tier=str(int(face) if face == int(face) else face),
                face_price=face,
                listed_min=None,
                listed_median=None,
                premium_ratio=prem,
                raw_note=f"tier-placeholder {note_prefix}",
            )
        )
    return out


def _parse_faces(face_prices: str) -> List[float]:
    out: List[float] = []
    for part in (face_prices or "").replace("，", "/").replace(",", "/").split("/"):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError:
            continue
    return out


def write_snapshots(storage: Storage, pairs: List[Tuple[WatchEvent, MtlShow]]) -> int:
    rows = []
    for ev, show in pairs:
        for snap in _tier_snapshots(ev, show):
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
