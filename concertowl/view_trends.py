"""从 Google Sheets 导出并打开「按场次」价格走势看板。

用法：
  python -m concertowl.view_trends

会生成 data/trends.html 并用默认浏览器打开。
"""
from __future__ import annotations

import json
import os
import time
import webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .storage import get_storage
from .models import artist_price_sheet
from .config import active_artists

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "data" / "trends_export.json"
OUT_HTML = ROOT / "data" / "trends.html"


def _build_events_from_storage() -> dict:
    storage = get_storage()
    events: dict[str, dict] = {}

    # 直接扫已有「价_*」表，避免对空歌手表做无效读取
    if hasattr(storage, "_ss"):
        sheet_names = [
            ws.title for ws in storage._ss.worksheets() if ws.title.startswith("价_")
        ]
    else:
        from .watchlist import read_watchlist

        watch_events, _ = read_watchlist(storage)
        artist_names = sorted(
            {a.name for a in active_artists()}
            | {e.artist for e in watch_events if e.artist}
        )
        sheet_names = [artist_price_sheet(a) for a in artist_names]

    for sheet in sheet_names:
        artist = sheet[2:] if sheet.startswith("价_") else sheet
        vals = storage.read_rows(sheet)
        time.sleep(0.35)
        if len(vals) < 2:
            continue
        header = vals[0]
        idx = {name: i for i, name in enumerate(header)}

        def cell(row, name, default=""):
            i = idx.get(name)
            if i is None or i >= len(row):
                return default
            return (row[i] or "").strip()

        for row in vals[1:]:
            eid = cell(row, "event_id")
            price_s = cell(row, "observed_price")
            at = cell(row, "observed_at")
            if not eid or not price_s or not at:
                continue
            try:
                price = float(price_s)
            except ValueError:
                continue
            face_s = cell(row, "face_price")
            source = cell(row, "source") or "?"
            if face_s:
                try:
                    face = float(face_s)
                    if face < 50:
                        continue
                    series = f"面值{int(face) if face == int(face) else face}"
                except ValueError:
                    series = f"面值{face_s}"
            else:
                series = "全场最低"

            if eid not in events:
                events[eid] = {
                    "event_id": eid,
                    "artist": artist,
                    "city": cell(row, "city"),
                    "tour": cell(row, "tour"),
                    "show_datetime": cell(row, "show_datetime"),
                    "series": defaultdict(dict),
                    "sources": set(),
                }
            ev = events[eid]
            if cell(row, "city"):
                ev["city"] = cell(row, "city")
            if cell(row, "tour"):
                ev["tour"] = cell(row, "tour")
            if cell(row, "show_datetime"):
                ev["show_datetime"] = cell(row, "show_datetime")
            ev["sources"].add(source)
            ev["series"][series][at[:16]] = price

    out = []
    for eid, ev in events.items():
        stamps = sorted({t for mp in ev["series"].values() for t in mp})
        if len(stamps) < 2:
            continue
        series_out = []
        for name, mp in sorted(ev["series"].items(), key=lambda x: x[0]):
            data = [mp.get(t) for t in stamps]
            if sum(1 for v in data if v is not None) < 2:
                continue
            first_real = next(v for v in data if v is not None)
            filled, last = [], first_real
            for v in data:
                if v is not None:
                    last = v
                filled.append(last)
            series_out.append({"name": name, "data": filled, "raw": data})
        if not series_out:
            continue
        cats = [t[5:].replace("T", " ") for t in stamps]
        primary = next((s for s in series_out if s["name"] == "全场最低"), series_out[0])
        first = next(v for v in primary["raw"] if v is not None)
        last = next(v for v in reversed(primary["raw"]) if v is not None)
        overall = [s for s in series_out if s["name"] == "全场最低"]
        faces = [s for s in series_out if s["name"] != "全场最低"][:5]
        keep = overall + faces
        out.append(
            {
                "id": eid,
                "artist": ev["artist"],
                "city": ev["city"],
                "tour": (ev["tour"] or "")[:40],
                "show": (ev["show_datetime"] or "")[:16],
                "label": f"{ev['artist']} · {ev['city']} · {(ev['show_datetime'] or '')[:10]}",
                "categories": cats,
                "series": [{"name": s["name"], "data": s["data"]} for s in keep],
                "first": first,
                "last": last,
                "delta": round(last - first, 1),
                "delta_pct": round((last / first - 1) * 100, 1) if first else 0,
                "points": len(stamps),
                "sources": sorted(ev["sources"]),
            }
        )

    out.sort(key=lambda e: (e["artist"], e["show"], e["city"]))
    artists = sorted({e["artist"] for e in out})
    movers = sorted(out, key=lambda e: abs(e["delta_pct"]), reverse=True)[:12]
    return {
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "event_count": len(out),
        "artists": artists,
        "events": out,
        "movers": [
            {
                "label": m["label"],
                "delta": m["delta"],
                "delta_pct": m["delta_pct"],
                "first": m["first"],
                "last": m["last"],
                "points": m["points"],
            }
            for m in movers
        ],
    }


def _write_html(payload: dict) -> Path:
    html_data = json.dumps(payload, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ConcertOwl 场次价格走势</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  body {{ font-family: "Segoe UI", "PingFang SC", sans-serif; margin: 24px; background:#f7f7f5; color:#1a1a1a; }}
  h1 {{ font-size: 22px; margin: 0 0 8px; }}
  .sub {{ color:#666; margin-bottom: 20px; }}
  .row {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:16px; }}
  select {{ min-width: 220px; padding:8px 10px; font-size:14px; }}
  .card {{ background:#fff; border:1px solid #e5e5e2; border-radius:8px; padding:16px; }}
  .stats {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin:12px 0 16px; }}
  .stat {{ background:#fafafa; border:1px solid #eee; border-radius:6px; padding:10px; }}
  .stat b {{ display:block; font-size:18px; }}
  .stat span {{ color:#666; font-size:12px; }}
</style>
</head>
<body>
<h1>ConcertOwl 场次价格走势</h1>
<p class="sub">本地看板 · 导出于 {payload["generated_at"]} · 共 {payload["event_count"]} 场有时序（≥2 个观测时刻）</p>
<div class="row">
  <label>歌手 <select id="artist"></select></label>
  <label>场次 <select id="event" style="min-width:360px"></select></label>
</div>
<div class="card">
  <div id="title" style="font-weight:600;margin-bottom:8px"></div>
  <div class="stats" id="stats"></div>
  <canvas id="chart" height="120"></canvas>
</div>
<script>
const DATA = {html_data};
let chart;
function eventsFor(artist) {{ return DATA.events.filter(e => e.artist === artist); }}
function fillArtists() {{
  const sel = document.getElementById('artist');
  sel.innerHTML = DATA.artists.map(a => {{
    const n = DATA.events.filter(e => e.artist === a).length;
    return `<option value="${{a}}">${{a}}（${{n}}场）</option>`;
  }}).join('');
}}
function fillEvents() {{
  const artist = document.getElementById('artist').value;
  const sel = document.getElementById('event');
  const list = eventsFor(artist);
  sel.innerHTML = list.map(e =>
    `<option value="${{e.id}}">${{e.city}} · ${{e.show.slice(0,10)}} · ${{e.delta_pct>=0?'+':''}}${{e.delta_pct}}%</option>`
  ).join('');
  render();
}}
function render() {{
  const artist = document.getElementById('artist').value;
  const id = document.getElementById('event').value;
  const ev = eventsFor(artist).find(e => e.id === id) || eventsFor(artist)[0];
  if (!ev) return;
  document.getElementById('title').textContent = ev.label + ' — ' + (ev.tour || '');
  document.getElementById('stats').innerHTML = `
    <div class="stat"><b>${{ev.first}}</b><span>首观测价</span></div>
    <div class="stat"><b>${{ev.last}}</b><span>最新观测价</span></div>
    <div class="stat"><b>${{ev.delta>=0?'+':''}}${{ev.delta}}</b><span>绝对变动</span></div>
    <div class="stat"><b>${{ev.delta_pct>=0?'+':''}}${{ev.delta_pct}}%</b><span>相对变动</span></div>`;
  const ctx = document.getElementById('chart');
  if (chart) chart.destroy();
  chart = new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: ev.categories,
      datasets: ev.series.map(s => ({{ label: s.name, data: s.data, tension: 0.2, borderWidth: 2, pointRadius: 3 }})),
    }},
    options: {{
      responsive: true,
      scales: {{
        y: {{ title: {{ display: true, text: '挂牌价（元）' }} }},
        x: {{ title: {{ display: true, text: '观测时间' }} }},
      }},
      plugins: {{ legend: {{ position: 'bottom' }} }},
    }},
  }});
}}
document.getElementById('artist').addEventListener('change', fillEvents);
document.getElementById('event').addEventListener('change', render);
fillArtists();
fillEvents();
</script>
</body>
</html>
"""
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    return OUT_HTML


def run(open_browser: bool = True) -> int:
    payload = _build_events_from_storage()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    path = _write_html(payload)
    print(f"[trends] {payload['event_count']} 场可画走势 → {path}")
    if open_browser:
        webbrowser.open(path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    # 默认连 Google Sheets；本地调试可设 CONCERTOWL_DRYRUN=1 读 data/*.csv
    raise SystemExit(run(open_browser=os.environ.get("CONCERTOWL_NO_BROWSER") != "1"))
