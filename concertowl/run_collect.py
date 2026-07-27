"""采集主入口：读 Watchlist -> 各采集器 -> 按歌手分表追加时序观测。"""
from __future__ import annotations

from typing import List

from .collectors import all_collectors
from .models import PriceSnapshot
from .snapshots import append_observations
from .storage import get_storage
from .watchlist import read_watchlist


def run() -> int:
    storage = get_storage()
    events, skipped = read_watchlist(storage)
    for s in skipped:
        print(f"[skip] {s}")

    if not events:
        print("[collect] Watchlist 为空或无在范围内的场次，未采集。")
        return 0

    collectors = all_collectors()
    all_snaps: List[PriceSnapshot] = []

    for ev in events:
        matched = [c for c in collectors if c.handles(ev)]
        if not matched:
            print(f"[warn] {ev.event_id} 无匹配采集器（检查 official_url/secondary_url）")
            continue
        for c in matched:
            snaps = c.collect(ev)
            all_snaps.extend(snaps)
            for s in snaps:
                price = s.observed_price if s.observed_price is not None else "-"
                print(
                    f"  [{c.source}] {ev.artist}@{ev.city} "
                    f"face={s.face_price or '-'} obs={price} {s.currency} note={s.note}"
                )

    n = append_observations(storage, all_snaps)
    print(f"[collect] 完成：{len(events)} 场，写入 {n} 条时序观测。")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
