"""Metadata storage backends.

统一接口：
  - read_rows(sheet)            -> List[List[str]]（含表头）
  - append_rows(sheet, rows)    追加多行
  - ensure_sheet(sheet, header) 确保表存在且有表头
  - overwrite(sheet, rows)      整表覆盖（用于 Decision 刷新）

Production metadata lives under ``CONCERTOWL_DATA_DIR/meta`` on the dedicated
Git data branch. Price history is handled by :mod:`concertowl.repo_history`.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import List

SHEET_NAMES = ["Cities", "Artists", "Watchlist", "PriceSnapshots", "ArtistProfiles", "Decision"]


class Storage:
    def read_rows(self, sheet: str) -> List[List[str]]:
        raise NotImplementedError

    def append_rows(self, sheet: str, rows: List[List[str]]) -> None:
        raise NotImplementedError

    def ensure_sheet(self, sheet: str, header: List[str]) -> None:
        raise NotImplementedError

    def overwrite(self, sheet: str, rows: List[List[str]]) -> None:
        raise NotImplementedError


class LocalCsvStorage(Storage):
    """把每个 sheet 存成 data/<sheet>.csv，方便本地跑通与查看。"""

    def __init__(self, base_dir: str = "data"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _path(self, sheet: str) -> str:
        return os.path.join(self.base_dir, f"{sheet}.csv")

    def read_rows(self, sheet: str) -> List[List[str]]:
        path = self._path(sheet)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return [row for row in csv.reader(f)]

    def ensure_sheet(self, sheet: str, header: List[str]) -> None:
        path = self._path(sheet)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerow(header)

    def append_rows(self, sheet: str, rows: List[List[str]]) -> None:
        if not rows:
            return
        with open(self._path(sheet), "a", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(rows)

    def overwrite(self, sheet: str, rows: List[List[str]]) -> None:
        with open(self._path(sheet), "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(rows)

class RepoStorage(LocalCsvStorage):
    """CSV metadata plus immutable JSONL history on the repository data branch."""

    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root)
        super().__init__(str(self.data_root / "meta"))
        from .repo_history import RepoHistory

        self.history = RepoHistory(self.data_root)

    def append_snapshots(self, snapshots) -> int:
        return self.history.record(snapshots)

    def finalize_run(self, manifest=None) -> dict:
        return self.history.finalize(manifest)

    def list_price_sheets(self) -> List[str]:
        artists = {
            str(record.get("artist") or "")
            for record in self.iter_observations()
            if record.get("artist")
        }
        return [f"价_{name}" for name in sorted(artists)]

    def iter_observations(self):
        from .repo_history import iter_observations

        return iter_observations(self.data_root)

    def read_rows(self, sheet: str) -> List[List[str]]:
        if not sheet.startswith("价_"):
            return super().read_rows(sheet)

        from .models import SNAPSHOT_HEADER

        artist = sheet[2:]
        rows = [SNAPSHOT_HEADER]
        for record in self.iter_observations():
            if record.get("artist") != artist:
                continue
            rows.append(
                [
                    "" if record.get(name) is None else str(record.get(name))
                    for name in SNAPSHOT_HEADER
                ]
            )
        return rows

    def ensure_sheet(self, sheet: str, header: List[str]) -> None:
        if not sheet.startswith("价_"):
            super().ensure_sheet(sheet, header)

    def append_rows(self, sheet: str, rows: List[List[str]]) -> None:
        if sheet.startswith("价_"):
            raise RuntimeError("价格历史必须通过 append_snapshots 写入")
        super().append_rows(sheet, rows)


def get_storage() -> Storage:
    """Use repository storage in production and local CSV for dry runs."""
    data_dir = os.environ.get("CONCERTOWL_DATA_DIR", "").strip()
    if data_dir and os.environ.get("CONCERTOWL_DRYRUN") != "1":
        return RepoStorage(data_dir)
    local_dir = os.environ.get("CONCERTOWL_LOCAL_DATA_DIR", "data")
    return LocalCsvStorage(local_dir)
