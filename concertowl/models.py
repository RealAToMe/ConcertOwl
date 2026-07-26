"""统一的数据模型：白名单条目、关注场次、价格快照。

所有采集器最终都归一化成 PriceSnapshot，写入同一张 PriceSnapshots 表。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class City:
    name: str
    region: str  # CN / HK / MO
    band: str    # 珠三角 / 长三角 / 京津 / 港澳
    aliases: List[str] = field(default_factory=list)

    def matches(self, text: str) -> bool:
        if not text:
            return False
        needles = [self.name] + list(self.aliases)
        return any(n and n.lower() in text.lower() for n in needles)


@dataclass
class Artist:
    name: str
    tier: str = "B"  # S / A / B
    active: bool = True
    aliases: List[str] = field(default_factory=list)

    def matches(self, text: str) -> bool:
        if not text:
            return False
        needles = [self.name] + list(self.aliases)
        return any(n and n.lower() in text.lower() for n in needles)


@dataclass
class WatchEvent:
    """Watchlist 中的一场演出。city/artist 必须落在白名单内。"""
    event_id: str
    artist: str
    tour: str = ""
    city: str = ""
    region: str = ""
    venue: str = ""
    show_datetime: str = ""   # ISO 字符串，如 2026-08-22T19:00
    face_prices: str = ""     # "380/680/980/1280"
    official_url: str = ""
    secondary_url: str = ""
    priority: str = "normal"
    active: bool = True

    def weekday(self) -> str:
        dt = parse_dt(self.show_datetime)
        if not dt:
            return ""
        return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]


@dataclass
class PriceSnapshot:
    """一次采集得到的单档位价格快照。"""
    ts: str                       # 采集时间（本地 ISO）
    event_id: str
    source: str                   # damai / moretickets / cityline ...
    tier: str = ""                # 票档名或面值
    listed_min: Optional[float] = None
    listed_median: Optional[float] = None
    premium_ratio: Optional[float] = None  # 二手价 / 面值
    days_to_show: Optional[int] = None
    days_since_onsale: Optional[int] = None
    official_status: str = "未知"  # 在售 / 售罄 / 未知
    raw_note: str = ""

    def as_row(self, header: List[str]) -> List[str]:
        d = asdict(self)
        return ["" if d.get(k) is None else str(d.get(k)) for k in header]


SNAPSHOT_HEADER = [
    "ts", "event_id", "source", "tier",
    "listed_min", "listed_median", "premium_ratio",
    "days_to_show", "days_since_onsale", "official_status", "raw_note",
]


def now_local_iso() -> str:
    # 用东八区时间记录，便于对照场次时间
    return datetime.now().replace(microsecond=0).isoformat()


def parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        from dateutil import parser as _p
        return _p.parse(value)
    except Exception:
        return None


def days_between(target_iso: str, ref: Optional[datetime] = None) -> Optional[int]:
    dt = parse_dt(target_iso)
    if not dt:
        return None
    ref = ref or datetime.now()
    if dt.tzinfo:
        ref = ref.replace(tzinfo=dt.tzinfo)
    return (dt.date() - ref.date()).days
