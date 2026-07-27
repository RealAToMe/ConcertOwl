"""摩天轮国内站公开接口客户端。

网页端可公开搜索全国演出并读取演出最低挂牌价；分档库存仍只在 App
购买链路中展示，因此这里输出 overall minimum。
"""
from __future__ import annotations

import time
from typing import List, Optional

import requests

from .mtl_api import MtlShow, _to_float

WEB_ORIGIN = "https://www.motianlun.cn"
DEFAULT_SITE_CITY = "3101"

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


class MtlChinaClient:
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

    def _request(self, method: str, path: str, **kwargs) -> Optional[dict]:
        self._throttle()
        try:
            resp = self._session.request(
                method, WEB_ORIGIN + path, timeout=self.timeout, **kwargs
            )
            if resp.status_code != 200:
                return None
            resp.encoding = "utf-8"
            data = resp.json()
            if data.get("statusCode") not in (200, None):
                return None
            return data
        except (requests.RequestException, ValueError):
            return None

    def search(
        self, keyword: str, page_size: int = 30, max_pages: int = 3
    ) -> List[MtlShow]:
        """按关键词全国搜索；cityId 只是站点上下文，不限制 showCityList。"""
        out: List[MtlShow] = []
        for page in range(max_pages):
            payload = {
                "cityId": DEFAULT_SITE_CITY,
                "showCityList": None,
                "tagId": None,
                "beginDateTime": None,
                "endDateTime": None,
                "sorting": "weight",
                "showType": "All",
                "keyword": keyword,
                "needShowTypeOption": page == 0,
                "offset": page * page_size,
                "length": page_size,
            }
            raw = self._request(
                "POST",
                "/mtl_recommendapi/pub/search/v4/show/by_keyword",
                json=payload,
            )
            body = (raw or {}).get("data") or {}
            rows = body.get("searchData") or []
            for row in rows:
                parsed = self._parse_search_show(row)
                if parsed:
                    out.append(parsed)
            total = int(((body.get("pagination") or {}).get("total")) or 0)
            if not rows or (page + 1) * page_size >= total:
                break
        return out

    def detail(self, show_id: str) -> Optional[MtlShow]:
        raw = self._request("GET", f"/showapi/pub/show/{show_id}")
        body = (((raw or {}).get("result") or {}).get("data")) or {}
        if not body:
            return None
        status = body.get("showStatus") or {}
        return MtlShow(
            show_id=str(body.get("showOID") or show_id),
            title=str(body.get("showName") or body.get("originalShowName") or ""),
            venue=str(body.get("venueName") or ""),
            location=str(body.get("cityName") or body.get("siteName") or ""),
            show_date=str(body.get("showDate") or body.get("latestShowTime") or ""),
            status=str(
                (status.get("name") if isinstance(status, dict) else status) or ""
            ),
            min_price=_to_float(body.get("minPrice")),
            currency="CNY",
            web_url_value=self.show_url(show_id),
        )

    @staticmethod
    def show_url(show_id: str) -> str:
        return (
            f"{WEB_ORIGIN}/show-detail/show-detail"
            f"?showId={show_id}"
        )

    def _parse_search_show(self, raw: dict) -> Optional[MtlShow]:
        show_id = str(raw.get("showId") or "").strip()
        if not show_id:
            return None
        price = raw.get("priceInfo") or {}
        amount = price.get("yuanNum") if isinstance(price, dict) else None
        return MtlShow(
            show_id=show_id,
            title=str(raw.get("showName") or ""),
            venue=str(raw.get("venueName") or ""),
            location=str(raw.get("showCity") or raw.get("showSite") or ""),
            show_date=str(raw.get("showDate") or ""),
            status=str(raw.get("showStatus") or raw.get("showState") or ""),
            min_price=_to_float(amount),
            currency="CNY",
            web_url_value=self.show_url(show_id),
        )
