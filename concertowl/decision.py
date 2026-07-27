"""基于各「价_歌手」时序表生成决策（观察期可暂不跑）。"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .bootstrap_sheet import DECISION_HEADER
from .config import match_artist, match_city
from .models import artist_price_sheet, now_local_iso
from .storage import Storage, get_storage
from .watchlist import read_watchlist

SECONDARY_SOURCES = {"moretickets"}


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


def _load_artist_snaps(storage: Storage, artist: str) -> List[dict]:
    rows = storage.read_rows(artist_price_sheet(artist))
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
    # 按歌手缓存时序
    cache: Dict[str, List[dict]] = {}
    for ev in events:
        if ev.artist not in cache:
            cache[ev.artist] = _load_artist_snaps(storage, ev.artist)

    rows = [DECISION_HEADER]
    for ev in events:
        snaps = [s for s in cache.get(ev.artist, []) if s.get("event_id") == ev.event_id]
        latest_min, latest_premium, status, dts = _latest_metrics(snaps)
        grab, wait, floor_range, sample_n, conf = _advise(ev, cache)
        rows.append([
            ev.event_id, ev.artist, ev.city, ev.show_datetime,
            "" if dts is None else dts,
            "" if latest_min is None else latest_min,
            "" if latest_premium is None else latest_premium,
            status,
            grab, wait, floor_range, sample_n, conf, now_local_iso(False),
        ])

    storage.ensure_sheet("Decision", DECISION_HEADER)
    storage.overwrite("Decision", rows)
    print(f"[decision] 刷新 {len(events)} 场决策。")
    return 0


def _latest_metrics(snaps: List[dict]) -> Tuple[Optional[float], Optional[float], str, Optional[int]]:
    snaps = sorted(snaps, key=lambda s: s.get("observed_at", ""))
    latest_min = None
    latest_premium = None
    status = "未知"
    dts = None
    for s in snaps:
        if s.get("source") in SECONDARY_SOURCES:
            m = _to_float(s.get("observed_price"))
            if m is not None:
                latest_min = m
                latest_premium = _to_float(s.get("premium_ratio"))
        st = s.get("status")
        if st and st != "未知":
            status = st
        d = _to_int(s.get("days_to_show"))
        if d is not None:
            dts = d
    return latest_min, latest_premium, status, dts


def _advise(ev, cache: Dict[str, List[dict]]) -> Tuple[str, str, str, int, str]:
    art = match_artist(ev.artist)
    tier = art.tier if art else "B"
    sim = list(cache.get(ev.artist, []))
    premiums = [p for p in (_to_float(s.get("premium_ratio")) for s in sim) if p is not None]
    sample_n = len(premiums)

    conf = "中" if sample_n >= 12 else ("低-中" if sample_n >= 4 else "低")
    med = _percentile(premiums, 0.5) if premiums else None
    if med is not None:
        if med >= 1.2:
            grab = f"值得抢/可接受代抢(中位溢价×{med})"
        elif med <= 1.0:
            grab = f"可不抢(中位溢价×{med})"
        else:
            grab = f"看情况(中位溢价×{med})"
    else:
        grab = {"S": "大概率值得抢(S档经验)", "A": "偏向可抢(A档经验)", "B": "可不急(B档经验)"}.get(tier, "数据不足")

    if premiums:
        below = sum(1 for p in premiums if p <= 1.0) / len(premiums)
        if below >= 0.5:
            wait = f"可等二手(约{int(below*100)}%时段低于面值)"
        elif below >= 0.2:
            wait = f"边等边设心理价({int(below*100)}%时段跌破面值)"
        else:
            wait = "不建议等(很少跌破面值)"
    else:
        wait = {"S": "不建议等", "A": "谨慎等", "B": "可以等"}.get(tier, "数据不足")

    late = []
    for s in sim:
        d = _to_int(s.get("days_to_show"))
        m = _to_float(s.get("observed_price"))
        if d is not None and m is not None and d <= 3:
            late.append(m)
    if late:
        floor_range = f"{_percentile(late, 0.25)}~{_percentile(late, 0.5)}"
    else:
        floor_range = "样本不足"

    return grab, wait, floor_range, sample_n, conf


if __name__ == "__main__":
    raise SystemExit(refresh())
