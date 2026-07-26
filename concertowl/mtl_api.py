"""MoreTickets 国际站公开 API 客户端（api-global.moretickets.com）。

用于：
- 按歌手搜索场次
- 按港澳 location 分页拉列表
- 读取最低挂牌价（search/list 里的 minSalePrice / salePrice）

挂牌价 ≠ 成交价；仅作观察指标。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

import requests

API_BASE = "https://api-global.moretickets.com"
WEB_ORIGIN = "https://www.moretickets.com"

# 国际站城市 locationId（来自 /pub/home/v1/location/list）
LOCATION_IDS = {
    "香港": "662e61ac5aa19945010236bf",
    "澳门": "668faeed407ad900018875b9",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": WEB_ORIGIN,
    "Referer": f"{WEB_ORIGIN}/",
}


@dataclass
class MtlShow:
    show_id: str
    tour_id: str = ""
    show_code: str = ""
    title: str = ""
    venue: str = ""
    location: str = ""
    show_date: str = ""
    status: str = ""
    min_price: Optional[float] = None
    currency: str = ""

    @property
    def web_url(self) -> str:
        code = self.show_code or self.show_id
        q = []
        if self.show_id:
            q.append(f"showId={self.show_id}")
        if self.tour_id:
            q.append(f"tourId={self.tour_id}")
        qs = ("?" + "&".join(q)) if q else ""
        return f"{WEB_ORIGIN}/show-detail/{code}{qs}"

    @property
    def event_id(self) -> str:
        return f"mtl_{self.show_id}"


class MoreTicketsClient:
    def __init__(self, min_interval: float = 1.2, timeout: float = 20.0):
        self.min_interval = min_interval
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._last = 0.0

    def _throttle(self) -> None:
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def get_json(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        self._throttle()
        try:
            resp = self._session.get(
                API_BASE + path, params=params or {}, timeout=self.timeout
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            # 正常成功：statusCode == 200（或缺省）
            if data.get("statusCode") not in (200, None):
                return None
            return data
        except (requests.RequestException, ValueError):
            return None

    def search(self, keyword: str, page: int = 1, page_size: int = 20) -> List[MtlShow]:
        data = self.get_json(
            "/pub/search/v1/search",
            {"keyword": keyword, "page": page, "pageSize": page_size},
        )
        if not data:
            return []
        out: List[MtlShow] = []
        for item in data.get("data") or []:
            show = item.get("show") if isinstance(item, dict) else None
            if not show and isinstance(item, dict) and item.get("id"):
                show = item
            parsed = self._parse_show(show or {})
            if parsed:
                out.append(parsed)
        return out

    def list_by_location(
        self, location_id: str, max_pages: int = 8, page_size: int = 20
    ) -> List[MtlShow]:
        out: List[MtlShow] = []
        for page in range(1, max_pages + 1):
            data = self.get_json(
                "/pub/home/v2/show/list",
                {"page": page, "pageSize": page_size, "locationId": location_id},
            )
            if not data:
                break
            rows = data.get("data") or []
            if not rows:
                break
            for item in rows:
                parsed = self._parse_show(item or {})
                if parsed:
                    out.append(parsed)
            total = ((data.get("pagination") or {}).get("total")) or 0
            if page * page_size >= int(total):
                break
        return out

    def fetch_show_price(self, show: MtlShow, artist_keywords: Iterable[str]) -> Optional[float]:
        """用歌手关键词搜索，找到同一 showId 的最新最低挂牌价。"""
        for kw in artist_keywords:
            if not kw:
                continue
            for hit in self.search(kw):
                if hit.show_id == show.show_id and hit.min_price is not None:
                    return hit.min_price
        return show.min_price

    @staticmethod
    def _parse_show(raw: dict) -> Optional[MtlShow]:
        if not raw:
            return None
        show_id = str(raw.get("id") or raw.get("showId") or "").strip()
        if not show_id:
            return None
        price_obj = raw.get("price") or {}
        min_price = _to_float(
            price_obj.get("minSalePrice")
            if isinstance(price_obj, dict)
            else None
        )
        if min_price is None:
            min_price = _to_float(raw.get("salePrice") or raw.get("discountPrice"))
        currency = ""
        if isinstance(price_obj, dict):
            currency = str(price_obj.get("currencySymbol") or "")
        currency = currency or str(raw.get("currencySymbol") or "")

        nav = str(raw.get("navigateUrl") or "")
        qs = parse_qs(urlparse(nav.replace("moretickets://moretickets.com/", "https://x/")).query)
        tour_id = str(raw.get("tourId") or (qs.get("tourId") or [""])[0] or "")
        show_code = str((qs.get("showCode") or [""])[0] or "")
        # also try from navigateUrl regex
        if not show_code:
            m = re.search(r"showCode=([^&]+)", nav)
            if m:
                show_code = m.group(1)

        return MtlShow(
            show_id=show_id,
            tour_id=tour_id,
            show_code=show_code,
            title=str(raw.get("title") or raw.get("showName") or ""),
            venue=str(raw.get("venueName") or ""),
            location=str(raw.get("location") or ""),
            show_date=str(raw.get("showDate") or ""),
            status=str(raw.get("status") or raw.get("statusDesc") or ""),
            min_price=min_price,
            currency=currency,
        )


def parse_show_id_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"showId=([0-9a-fA-F]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"mtl_([0-9a-fA-F]+)", url)
    if m:
        return m.group(1)
    return None


def _to_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None
