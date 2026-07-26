"""采集主入口：读 Watchlist -> 跑各采集器 -> 追加写入 PriceSnapshots。

用法：
  python -m concertowl.run_collect
Dry-run：
  CONCERTOWL_DRYRUN=1 python -m concertowl.run_collect
"""
from __future__ import annotations

from typing import List

from .collectors import all_collectors
from .models import SNAPSHOT_HEADER, PriceSnapshot
from .storage import get_storage
from .watchlist import read_watchlist


def run() -> int:
    storage = get_storage()
    storage.ensure_sheet("PriceSnapshots", SNAPSHOT_HEADER)

    events, skipped = read_watchlist(storage)
    for s in skipped:
        print(f"[skip] {s}")

    if not events:
        print("[collect] Watchlist 为空或无在范围内的场次，未采集。")
        return 0

    collectors = all_collectors()
    all_rows: List[List[str]] = []
    snap_count = 0

    for ev in events:
        matched = [c for c in collectors if c.handles(ev)]
        if not matched:
            print(f"[warn] {ev.event_id} 无匹配采集器（检查 official_url/secondary_url）")
            continue
        for c in matched:
            snaps: List[PriceSnapshot] = c.collect(ev)
            for snap in snaps:
                all_rows.append(snap.as_row(SNAPSHOT_HEADER))
                snap_count += 1
            _log(ev, c.source, snaps)

    if all_rows:
        storage.append_rows("PriceSnapshots", all_rows)
    print(f"[collect] 完成：{len(events)} 场，写入 {snap_count} 条快照。")
    return 0


def _log(ev, source, snaps) -> None:
    for s in snaps:
        price = s.listed_min if s.listed_min is not None else "-"
        print(f"  [{source}] {ev.event_id} {ev.artist}@{ev.city} "
              f"min={price} status={s.official_status} note={s.raw_note}")


if __name__ == "__main__":
    raise SystemExit(run())
