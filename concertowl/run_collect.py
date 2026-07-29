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
    # 按歌手顺序采并即时落表，避免最后一次性打满 Sheets 写配额
    events = sorted(events, key=lambda e: (e.artist or "", e.city or "", e.event_id))
    pending: List[PriceSnapshot] = []
    current_artist = None
    written = 0
    write_errors: List[str] = []

    def flush() -> None:
        nonlocal pending, written
        if not pending:
            return
        batch = pending
        pending = []
        try:
            written += append_observations(storage, batch)
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            write_errors.append(msg)
            print(f"[collect] 写表失败（已跳过本批，继续）：{msg}")

    for ev in events:
        if current_artist is not None and ev.artist != current_artist:
            flush()
        current_artist = ev.artist

        matched = [c for c in collectors if c.handles(ev)]
        if not matched:
            print(f"[warn] {ev.event_id} 无匹配采集器（检查 official_url/secondary_url）")
            continue
        for c in matched:
            snaps = c.collect(ev)
            pending.extend(snaps)
            for s in snaps:
                price = s.observed_price if s.observed_price is not None else "-"
                print(
                    f"  [{c.source}] {ev.artist}@{ev.city} "
                    f"face={s.face_price or '-'} obs={price} {s.currency} note={s.note}"
                )

    flush()
    print(f"[collect] 完成：{len(events)} 场，写入 {written} 条时序观测。")
    if write_errors:
        print(f"[collect] 有 {len(write_errors)} 次写表错误")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
