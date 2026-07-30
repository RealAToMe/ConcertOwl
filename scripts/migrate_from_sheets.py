"""One-time migration from Google Sheets to repository JSONL history."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from concertowl.repo_history import (
    observation_series_key,
    rebuild_latest,
)
from concertowl.models import SNAPSHOT_HEADER

NUMERIC_FLOATS = {"face_price", "observed_price", "premium_ratio"}
NUMERIC_INTS = {"days_to_show", "days_since_onsale"}


def _credentials(value: str) -> dict:
    path = Path(value)
    text = path.read_text(encoding="utf-8") if path.exists() else value
    return json.loads(text)


def _coerce(record: dict) -> dict:
    for name in NUMERIC_FLOATS:
        value = record.get(name)
        if value in ("", None):
            record[name] = None
        else:
            try:
                record[name] = float(value)
            except (TypeError, ValueError):
                pass
    for name in NUMERIC_INTS:
        value = record.get(name)
        if value in ("", None):
            record[name] = None
        else:
            try:
                record[name] = int(float(value))
            except (TypeError, ValueError):
                pass
    return record


def _day_key(value: object) -> str:
    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", str(value or ""))
    if not match:
        return "unknown"
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def migrate(
    sheet_id: str,
    credentials: str,
    data_dir: Path | str,
    *,
    force: bool = False,
) -> dict:
    import gspread
    from google.oauth2.service_account import Credentials

    root = Path(data_dir)
    if force:
        for old in (root / "prices").glob("*/*/*/migration-*.jsonl"):
            old.unlink()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        _credentials(credentials), scopes=scopes
    )
    spreadsheet = gspread.authorize(creds).open_by_key(sheet_id)

    meta = root / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    watchlist = spreadsheet.worksheet("Watchlist").get_all_values()
    with (meta / "Watchlist.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        csv.writer(handle).writerows(watchlist)

    partitions: dict[str, list[dict]] = defaultdict(list)
    exact_seen: set[str] = set()
    source_counts: Counter[str] = Counter()
    artist_counts: Counter[str] = Counter()
    source_total = 0
    invalid_price_rows = 0
    repaired_headers: list[str] = []

    for worksheet in spreadsheet.worksheets():
        if not worksheet.title.startswith("价_"):
            continue
        artist = worksheet.title[2:]
        rows = worksheet.get_all_values()
        if len(rows) < 2:
            continue
        header = rows[0]
        if (
            len(header) == len(SNAPSHOT_HEADER)
            and header[:2] == ["", "observed_at"]
            and header[2:] == SNAPSHOT_HEADER[2:]
        ):
            header = SNAPSHOT_HEADER
            repaired_headers.append(worksheet.title)
        for values in rows[1:]:
            if not any(str(value).strip() for value in values):
                continue
            source_total += 1
            record = {
                name: values[index] if index < len(values) else ""
                for index, name in enumerate(header)
            }
            record["artist"] = artist
            record = _coerce(record)
            price = record.get("observed_price")
            if isinstance(price, (int, float)) and price <= 0:
                invalid_price_rows += 1
                continue
            observed_at = str(record.get("observed_at") or "")
            day = _day_key(observed_at)
            canonical = json.dumps(
                record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            if canonical in exact_seen:
                continue
            exact_seen.add(canonical)
            record.update(
                {
                    "series_key": observation_series_key(record),
                    "collect_run_id": f"migration-{day}",
                    "record_kind": "migration",
                }
            )
            partitions[day].append(record)
            source_counts[str(record.get("source") or "?")] += 1
            artist_counts[artist] += 1

    for day, records in partitions.items():
        if day == "unknown":
            year, month, date = "unknown", "00", "00"
        else:
            year, month, date = day.split("-")
        path = root / "prices" / year / month / date / f"migration-{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            raise FileExistsError(f"{path} 已存在；需要覆盖时传 --force")
        with path.open("w", encoding="utf-8", newline="\n") as out:
            for record in sorted(
                records,
                key=lambda item: (
                    str(item.get("observed_at") or ""),
                    str(item.get("event_id") or ""),
                    str(item.get("source") or ""),
                    str(item.get("face_price") or ""),
                ),
            ):
                out.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )

    latest = rebuild_latest(root)
    report = {
        "migrated_at": datetime.now().isoformat(timespec="seconds"),
        "sheet_id": sheet_id,
        "watchlist_rows": max(0, len(watchlist) - 1),
        "source_rows": source_total,
        "migrated_rows": len(exact_seen),
        "invalid_price_rows_removed": invalid_price_rows,
        "exact_duplicates_removed": (
            source_total - invalid_price_rows - len(exact_seen)
        ),
        "partitions": len(partitions),
        "latest_series": len(latest),
        "repaired_headers": repaired_headers,
        "sources": dict(source_counts),
        "artists": dict(artist_counts),
        "samples": {
            artist: artist_counts.get(artist, 0)
            for artist in ("薛之谦", "周杰伦", "王力宏")
        },
    }
    (meta / "migration_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sheet-id", default=os.environ.get("SHEET_ID", ""), required=False
    )
    parser.add_argument(
        "--credentials",
        default=os.environ.get("GOOGLE_CREDENTIALS", ""),
        help="JSON 文件路径或 JSON 内容",
    )
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.sheet_id or not args.credentials:
        parser.error("需要 --sheet-id 与 --credentials")
    report = migrate(
        args.sheet_id, args.credentials, args.data_dir, force=args.force
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
