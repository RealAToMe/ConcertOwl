"""统一的数据模型：白名单、关注场次、按档位的时序价格观测。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
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
        """标题命中本名或别名。

        规则：
        - 中文名 / 长别名：子串或去空格后子串
        - 拉丁短别名（<=3）：整词匹配，且禁止单独用常见单名（如 Jay）避免误伤
        """
        if not text:
            return False
        import re

        hay = text.lower()
        hay_compact = re.sub(r"[\s_\-]+", "", hay)
        needles = [self.name] + list(self.aliases)
        # 单独使用时极易误匹配的拉丁短名
        risky_short = {"jay", "jj", "mc", "li", "yu", "bo", "jo"}

        for n in needles:
            if not n:
                continue
            needle = n.lower().strip()
            compact = re.sub(r"[\s_\-]+", "", needle)
            if not compact:
                continue
            # 纯拉丁且很短：必须整词，且若在 risky 列表则要求至少带姓/全名（有空格的别名才用）
            if compact.isascii() and len(compact) <= 3:
                if compact in risky_short and " " not in needle:
                    continue  # 跳过单独的 Jay / JJ 等
                if re.search(rf"(?<![a-z0-9]){re.escape(compact)}(?![a-z0-9])", hay):
                    return True
            else:
                if needle in hay or compact in hay_compact:
                    return True
        return False


@dataclass
class WatchEvent:
    """Watchlist 中的一场演出。关注歌手命中即收录（城市不限）。"""
    event_id: str
    artist: str
    tour: str = ""
    city: str = ""
    region: str = ""
    venue: str = ""
    show_datetime: str = ""   # ISO，如 2026-08-22T19:00
    face_prices: str = ""     # 官方各档面值，如 "380/680/980/1280"
    onsale_datetime: str = "" # 开售时间（有则填，用于 days_since_onsale）
    official_url: str = ""
    secondary_url: str = ""
    piaoniu_url: str = ""     # 票牛活动页；可与摩天轮 secondary_url 并存
    priority: str = "normal"
    active: bool = True

    def weekday(self) -> str:
        dt = parse_dt(self.show_datetime)
        if not dt:
            return ""
        return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]


@dataclass
class PriceSnapshot:
    """一次「档位 × 时刻」的价格观测，用于时序分析。

    每次采集、每个档位（或 overall）追加一行，不覆盖历史。
    """
    observed_at: str                 # 观测时间，精确到分钟，如 2026-07-27T18:04
    event_id: str
    artist: str
    city: str = ""
    tour: str = ""
    show_datetime: str = ""
    face_price: Optional[float] = None   # 官方档位面值，如 388；overall 时可空
    observed_price: Optional[float] = None  # 本次观测到的挂牌/成交代理价
    premium_ratio: Optional[float] = None   # observed_price / face_price
    days_to_show: Optional[int] = None
    days_since_onsale: Optional[int] = None
    currency: str = ""
    source: str = ""                 # moretickets / damai / cityline
    status: str = "未知"             # 在售 / 售罄 / 预售...
    note: str = ""

    def as_row(self, header: List[str] | None = None) -> List[str]:
        header = header or SNAPSHOT_HEADER
        d = asdict(self)
        return ["" if d.get(k) is None else str(d.get(k)) for k in header]


# 按歌手分表后的统一列（每张「价_歌手」表共用）
SNAPSHOT_HEADER = [
    "observed_at",
    "event_id",
    "city",
    "tour",
    "show_datetime",
    "face_price",
    "observed_price",
    "premium_ratio",
    "days_to_show",
    "days_since_onsale",
    "currency",
    "source",
    "status",
    "note",
]


def artist_price_sheet(artist: str) -> str:
    """Google Sheet / CSV 名：价_陈奕迅。"""
    name = (artist or "未知").strip() or "未知"
    # Sheets 标题限制约 100 字符；去掉非法字符
    for ch in "[]:*?/\\":
        name = name.replace(ch, "")
    return f"价_{name}"[:90]


def now_local_iso(minute_precision: bool = True) -> str:
    dt = datetime.now().replace(second=0, microsecond=0) if minute_precision else datetime.now().replace(microsecond=0)
    return dt.isoformat()


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


def days_since(start_iso: str, ref: Optional[datetime] = None) -> Optional[int]:
    """开售以来天数；start 为空则返回 None。"""
    dt = parse_dt(start_iso)
    if not dt:
        return None
    ref = ref or datetime.now()
    if dt.tzinfo:
        ref = ref.replace(tzinfo=dt.tzinfo)
    return (ref.date() - dt.date()).days
