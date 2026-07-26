"""基于历史快照生成三类购票决策，刷新 Decision 表。

第一版是「相似场次经验对照 + 规则」，不是 ML：
  1. 抢票倾向     —— 二手溢价长期 > 1.2 则值得抢/可接受代抢
  2. 等待降价倾向 —— 官方长期在售且溢价 <= 1 则可等二手
  3. 临场底价区间 —— 相似场次「开演前<=3天」最低挂牌的 P25/P50

相似优先级：同歌手历史 > 同 tier + 同区域带 > 同 tier。
样本越少置信度越低。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .bootstrap_sheet import DECISION_HEADER
from .config import load_cities, match_artist, match_city
from .models import SNAPSHOT_HEADER, now_local_iso
from .storage import Storage, get_storage
from .watchlist import read_watchlist

SECONDARY_SOURCES = {"moretickets"}
OFFICIAL_SOURCES = {"damai", "cityline"}


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _percentile(values: List[float], pct: float) -> Optional[float]:
    vals = sorted(values)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    frac = k - lo
    return round(vals[lo] * (1 - frac) + vals[hi] * frac, 1)


def _load_snapshots(storage: Storage) -> List[dict]:
    rows = storage.read_rows("PriceSnapshots")
    if not rows:
        return []
    header = rows[0]
    out = []
    for row in rows[1:]:
        rec = {header[i]: (row[i] if i < len(row) else "") for i in range(len(header))}
        out.append(rec)
    return out


def _band_of(city: str) -> str:
    c = match_city(city)
    return c.band if c else ""


def refresh() -> int:
    storage = get_storage()
    events, _ = read_watchlist(storage)
    snaps = _load_snapshots(storage)

    # 按 event_id 归组二手快照
    by_event_secondary: Dict[str, List[dict]] = defaultdict(list)
    for s in snaps:
        if s.get("source") in SECONDARY_SOURCES:
            by_event_secondary[s.get("event_id", "")].append(s)

    # event_id -> artist/city（来自 watchlist），用于相似匹配
    ev_meta = {e.event_id: e for e in events}

    rows = [DECISION_HEADER]
    for ev in events:
        latest_min, latest_premium, official_status, dts = _latest_metrics(ev, snaps)
        grab, wait, floor_range, sample_n, conf = _advise(ev, snaps, ev_meta)
        rows.append([
            ev.event_id, ev.artist, ev.city, ev.show_datetime,
            "" if dts is None else dts,
            "" if latest_min is None else latest_min,
            "" if latest_premium is None else latest_premium,
            official_status,
            grab, wait, floor_range, sample_n, conf, now_local_iso(),
        ])

    storage.ensure_sheet("Decision", DECISION_HEADER)
    storage.overwrite("Decision", rows)
    print(f"[decision] 刷新 {len(events)} 场决策。")
    return 0


def _latest_metrics(ev, snaps) -> Tuple[Optional[float], Optional[float], str, Optional[int]]:
    ev_snaps = [s for s in snaps if s.get("event_id") == ev.event_id]
    ev_snaps.sort(key=lambda s: s.get("ts", ""))
    latest_min = None
    latest_premium = None
    official_status = "未知"
    dts = None
    for s in ev_snaps:
        if s.get("source") in SECONDARY_SOURCES:
            m = _to_float(s.get("listed_min"))
            if m is not None:
                latest_min = m
                latest_premium = _to_float(s.get("premium_ratio"))
        if s.get("source") in OFFICIAL_SOURCES:
            st = s.get("official_status")
            if st and st != "未知":
                official_status = st
        d = _to_int(s.get("days_to_show"))
        if d is not None:
            dts = d
    return latest_min, latest_premium, official_status, dts


def _similar_secondary(ev, snaps, ev_meta) -> List[dict]:
    """挑选相似场次的二手快照。优先同歌手，其次同 tier+同区域带。"""
    art = match_artist(ev.artist)
    tier = art.tier if art else "B"
    band = _band_of(ev.city)

    same_artist, same_tier_band, same_tier = [], [], []
    for s in snaps:
        if s.get("source") not in SECONDARY_SOURCES:
            continue
        eid = s.get("event_id")
        meta = ev_meta.get(eid)
        if meta is None:
            continue
        s_art = match_artist(meta.artist)
        s_tier = s_art.tier if s_art else "B"
        s_band = _band_of(meta.city)
        if match_artist(meta.artist) and art and s_art and s_art.name == art.name:
            same_artist.append(s)
        elif s_tier == tier and s_band == band:
            same_tier_band.append(s)
        elif s_tier == tier:
            same_tier.append(s)

    if same_artist:
        return same_artist
    if same_tier_band:
        return same_tier_band
    return same_tier


def _advise(ev, snaps, ev_meta) -> Tuple[str, str, str, int, str]:
    sim = _similar_secondary(ev, snaps, ev_meta)
    premiums = [p for p in (_to_float(s.get("premium_ratio")) for s in sim) if p is not None]
    sample_n = len(premiums)

    art = match_artist(ev.artist)
    tier = art.tier if art else "B"

    # 置信度：主要看相似样本量
    if sample_n >= 12:
        conf = "中"
    elif sample_n >= 4:
        conf = "低-中"
    else:
        conf = "低"

    # 抢票倾向
    med_premium = _percentile(premiums, 0.5) if premiums else None
    if med_premium is not None:
        if med_premium >= 1.2:
            grab = f"值得抢/可接受代抢(中位溢价×{med_premium})"
        elif med_premium <= 1.0:
            grab = f"可不抢(中位溢价×{med_premium})"
        else:
            grab = f"看情况(中位溢价×{med_premium})"
    else:
        # 无历史，用 tier 经验先给弱先验
        prior = {"S": "大概率值得抢(S档经验)", "A": "偏向可抢(A档经验)", "B": "可不急(B档经验)"}
        grab = prior.get(tier, "数据不足")

    # 等待降价倾向：相似样本里溢价<=1 的比例
    if premiums:
        below = sum(1 for p in premiums if p <= 1.0)
        ratio = below / len(premiums)
        if ratio >= 0.5:
            wait = f"可等二手(约{int(ratio*100)}%时段低于面值)"
        elif ratio >= 0.2:
            wait = f"边等边设心理价({int(ratio*100)}%时段跌破面值)"
        else:
            wait = "不建议等(很少跌破面值)"
    else:
        wait = {"S": "不建议等", "A": "谨慎等", "B": "可以等"}.get(tier, "数据不足")

    # 临场底价区间：相似场次 days_to_show<=3 的最低挂牌
    late_mins = []
    for s in sim:
        d = _to_int(s.get("days_to_show"))
        m = _to_float(s.get("listed_min"))
        if d is not None and m is not None and d <= 3:
            late_mins.append(m)
    if late_mins:
        p25 = _percentile(late_mins, 0.25)
        p50 = _percentile(late_mins, 0.5)
        floor_range = f"{p25}~{p50}"
    else:
        floor_range = "样本不足"

    return grab, wait, floor_range, sample_n, conf


if __name__ == "__main__":
    raise SystemExit(refresh())
