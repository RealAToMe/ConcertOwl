"""存储后端：Google Sheets（云端）或本地 CSV（dry-run，无需凭证）。

统一接口：
  - read_rows(sheet)            -> List[List[str]]（含表头）
  - append_rows(sheet, rows)    追加多行
  - ensure_sheet(sheet, header) 确保表存在且有表头
  - overwrite(sheet, rows)      整表覆盖（用于 Decision 刷新）
"""
from __future__ import annotations

import csv
import json
import os
from typing import List, Optional

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


class GoogleSheetsStorage(Storage):
    """基于 gspread + service account 的 Google Sheets 后端。"""

    def __init__(self, spreadsheet_id: str, credentials_json: str):
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        info = json.loads(credentials_json)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        self._gc = gspread.authorize(creds)
        self._ss = self._gc.open_by_key(spreadsheet_id)

    def _ws(self, sheet: str):
        try:
            return self._ss.worksheet(sheet)
        except Exception:
            return None

    def read_rows(self, sheet: str) -> List[List[str]]:
        ws = self._ws(sheet)
        if ws is None:
            return []
        return ws.get_all_values()

    def ensure_sheet(self, sheet: str, header: List[str]) -> None:
        ws = self._ws(sheet)
        if ws is None:
            ws = self._ss.add_worksheet(title=sheet, rows=100, cols=max(len(header), 10))
            ws.append_row(header, value_input_option="RAW")
            return
        existing = ws.row_values(1)
        if not existing:
            ws.append_row(header, value_input_option="RAW")

    def append_rows(self, sheet: str, rows: List[List[str]]) -> None:
        if not rows:
            return
        ws = self._ws(sheet)
        if ws is None:
            raise RuntimeError(f"worksheet 不存在: {sheet}，请先 ensure_sheet")
        ws.append_rows(rows, value_input_option="RAW")

    def overwrite(self, sheet: str, rows: List[List[str]]) -> None:
        ws = self._ws(sheet)
        if ws is None:
            ws = self._ss.add_worksheet(title=sheet, rows=max(len(rows) + 5, 20), cols=20)
        ws.clear()
        if rows:
            ws.update(rows, value_input_option="RAW")


def get_storage() -> Storage:
    """按环境变量选择后端。

    设置 GOOGLE_CREDENTIALS + SHEET_ID -> Google Sheets
    否则 -> 本地 CSV（dry-run）
    强制本地：CONCERTOWL_DRYRUN=1
    """
    dryrun = os.environ.get("CONCERTOWL_DRYRUN") == "1"
    creds = os.environ.get("GOOGLE_CREDENTIALS")
    sheet_id = os.environ.get("SHEET_ID")
    if not dryrun and creds and sheet_id:
        return GoogleSheetsStorage(sheet_id, creds)
    return LocalCsvStorage()
