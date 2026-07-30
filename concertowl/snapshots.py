"""按时序追加价格观测到「按歌手分表」。"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from .models import (
    SNAPSHOT_HEADER,
    PriceSnapshot,
    WatchEvent,
    artist_price_sheet,
    days_between,
    days_since,
    now_local_iso,
)
from .storage import Storage


def build_observation(
    event: WatchEvent,
    *,
    observed_price: Optional[float],
    face_price: Optional[float] = None,
    source: str = "",
    status: str = "未知",
    currency: str = "",
    note: str = "",
    observed_at: Optional[str] = None,
) -> PriceSnapshot:
    """构造一条时序观测。无观测价时仍可记录（少用），一般应有 observed_price。"""
    prem = None
    if observed_price is not None and face_price and face_price > 0:
        prem = round(observed_price / face_price, 3)
    return PriceSnapshot(
        observed_at=observed_at or now_local_iso(True),
        event_id=event.event_id,
        artist=event.artist,
        city=event.city,
        tour=event.tour,
        show_datetime=event.show_datetime,
        face_price=face_price,
        observed_price=observed_price,
        premium_ratio=prem,
        days_to_show=days_between(event.show_datetime),
        days_since_onsale=days_since(getattr(event, "onsale_datetime", "") or ""),
        currency=currency,
        source=source,
        status=status,
        note=note,
    )


def append_observations(storage: Storage, snaps: Iterable[PriceSnapshot]) -> int:
    """Append observations to repository history or legacy local CSV."""
    snapshots = list(snaps)
    append_snapshots = getattr(storage, "append_snapshots", None)
    if append_snapshots is not None:
        written = append_snapshots(snapshots)
        print(f"[snapshot] 仓库批次暂存 {written}/{len(snapshots)} 条变化/心跳")
        return written

    by_artist: Dict[str, List[List[str]]] = defaultdict(list)
    count = 0
    for snap in snapshots:
        if not snap.artist:
            continue
        # 没有观测价的行对时序分析价值低，默认跳过（除非 note 标明 face_only）
        if snap.observed_price is None and "face_only" not in (snap.note or ""):
            continue
        sheet = artist_price_sheet(snap.artist)
        by_artist[sheet].append(snap.as_row(SNAPSHOT_HEADER))
        count += 1

    for sheet, rows in by_artist.items():
        storage.ensure_sheet(sheet, SNAPSHOT_HEADER)
        storage.append_rows(sheet, rows)
        print(f"[snapshot] {sheet} += {len(rows)}")
    return count


def ensure_artist_price_sheets(storage: Storage, artists: Iterable[str]) -> None:
    for name in artists:
        if not name:
            continue
        storage.ensure_sheet(artist_price_sheet(name), SNAPSHOT_HEADER)
