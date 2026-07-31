"""Generate a static per-event price trend dashboard from repository JSONL."""
from __future__ import annotations

import argparse
import csv
import json
import webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .repo_history import (
    data_root_from_env,
    iter_observations,
    iter_run_manifests,
)


def _watchlist_metadata(data_root: Path | str) -> dict[str, dict[str, str]]:
    """Load canonical event labels used to reject cross-session observations."""
    path = Path(data_root) / "meta" / "Watchlist.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return {
            str(row.get("event_id") or ""): {
                "artist": str(row.get("artist") or ""),
                "city": str(row.get("city") or ""),
                "tour": str(row.get("tour") or ""),
                "show": str(row.get("show_datetime") or "")[:16],
            }
            for row in rows
            if row.get("event_id")
        }


def build_payload(data_root: Path | str) -> dict:
    events: dict[str, dict] = {}
    metadata = _watchlist_metadata(data_root)
    for row in iter_observations(data_root):
        event_id = str(row.get("event_id") or "")
        observed_at = str(row.get("observed_at") or "")[:16]
        if not event_id or not observed_at or row.get("observed_price") is None:
            continue
        canonical = metadata.get(event_id, {})
        canonical_show = str(canonical.get("show") or "")
        observed_show = str(row.get("show_datetime") or "")
        if (
            canonical_show[:10]
            and observed_show[:10]
            and canonical_show[:10] != observed_show[:10]
        ):
            # A Piaoniu activity may contain several sessions. Older collectors
            # wrote every session under each linked Watchlist event; those rows
            # must not leak into a different date's chart.
            continue
        try:
            observed_price = float(row["observed_price"])
        except (TypeError, ValueError):
            continue
        if observed_price <= 0:
            continue
        face = row.get("face_price")
        try:
            face_number = float(face) if face not in (None, "") else None
        except (TypeError, ValueError):
            face_number = None
        if face_number is not None and face_number < 50:
            continue
        series_label = (
            f"面值{int(face_number) if face_number.is_integer() else face_number}"
            if face_number is not None
            else "全场最低"
        )
        event = events.setdefault(
            event_id,
            {
                "id": event_id,
                "artist": canonical.get("artist") or row.get("artist") or "",
                "city": canonical.get("city") or row.get("city") or "",
                "tour": canonical.get("tour") or row.get("tour") or "",
                "show": canonical_show or str(row.get("show_datetime") or "")[:16],
                "sources": set(),
                "series": defaultdict(dict),
            },
        )
        event["sources"].add(str(row.get("source") or "?"))
        event["series"][series_label][observed_at] = observed_price

    output = []
    for event in events.values():
        stamps = sorted(
            {stamp for series in event["series"].values() for stamp in series}
        )
        if not stamps:
            continue
        series_output = []
        for name, values in sorted(event["series"].items()):
            if not values:
                continue
            first_value = next(values[t] for t in stamps if t in values)
            last_value = first_value
            data = []
            for stamp in stamps:
                if stamp in values:
                    last_value = values[stamp]
                data.append(last_value)
            series_output.append({"name": name, "data": data})
        if not series_output:
            continue
        primary = next(
            (series for series in series_output if series["name"] == "全场最低"),
            series_output[0],
        )
        first, last = primary["data"][0], primary["data"][-1]
        output.append(
            {
                "id": event["id"],
                "artist": event["artist"],
                "city": event["city"],
                "tour": event["tour"],
                "show": event["show"],
                "label": (
                    f"{event['artist']} · {event['city']} · {event['show'][:10]}"
                ),
                "categories": [stamp[5:].replace("T", " ") for stamp in stamps],
                "series": series_output,
                "first": first,
                "last": last,
                "delta": round(last - first, 2),
                "delta_pct": round((last / first - 1) * 100, 2) if first else 0,
                "points": len(stamps),
                "sources": sorted(event["sources"]),
            }
        )

    output.sort(key=lambda event: (event["artist"], event["show"], event["city"]))
    runs = sorted(
        iter_run_manifests(data_root),
        key=lambda run: str(run.get("completed_at") or ""),
        reverse=True,
    )[:20]
    movers = sorted(output, key=lambda event: abs(event["delta_pct"]), reverse=True)[
        :12
    ]
    return {
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "event_count": len(output),
        "artists": sorted({event["artist"] for event in output}),
        "events": output,
        "movers": movers,
        "runs": runs,
    }


def _page(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ConcertOwl 价格走势</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--text:#17202a;--muted:#667085;--line:#e5e7eb;--ok:#16855b;--bad:#c43d3d}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:14px system-ui,"Microsoft YaHei",sans-serif}}
main{{max-width:1180px;margin:auto;padding:24px}} h1{{margin:0 0 6px;font-size:25px}} h2{{font-size:17px;margin:0 0 12px}}
.muted{{color:var(--muted)}} .grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:14px 0}}
.stat b{{display:block;font-size:22px;margin-bottom:3px}} .controls{{display:flex;gap:12px;flex-wrap:wrap}}
label{{color:var(--muted)}} select{{display:block;margin-top:5px;padding:8px;min-width:240px;border:1px solid var(--line);border-radius:6px;background:white}}
#event{{min-width:380px}} .run{{display:grid;grid-template-columns:145px 80px 90px 1fr;gap:8px;padding:8px 0;border-top:1px solid var(--line)}}
.ok{{color:var(--ok)}} .bad{{color:var(--bad)}} canvas{{max-height:400px}}
table{{width:100%;border-collapse:collapse}} td,th{{text-align:left;padding:8px;border-bottom:1px solid var(--line)}}
@media(max-width:700px){{.grid{{grid-template-columns:repeat(2,1fr)}} #event{{min-width:240px}} .run{{grid-template-columns:1fr 80px}}}}
</style>
</head>
<body><main>
<h1>ConcertOwl 场次价格走势</h1>
<div class="muted">仓库 JSONL 数据 · 生成于 {payload["generated_at"]}</div>
<div class="grid">
 <div class="card stat"><b>{payload["event_count"]}</b><span class="muted">有历史的场次</span></div>
 <div class="card stat"><b>{len(payload["artists"])}</b><span class="muted">歌手</span></div>
 <div class="card stat"><b id="lastStatus">-</b><span class="muted">最近采集</span></div>
 <div class="card stat"><b id="lastRows">-</b><span class="muted">最近新增记录</span></div>
</div>
<section class="card">
 <h2>单场走势</h2>
 <div class="controls">
  <label>歌手<select id="artist" autocomplete="off"></select></label>
  <label>场次<select id="event" autocomplete="off"></select></label>
 </div>
 <h2 id="title" style="margin-top:18px"></h2>
 <div class="muted" id="summary"></div>
 <canvas id="chart"></canvas>
</section>
<section class="card"><h2>最近运行</h2><div id="runs"></div></section>
<section class="card"><h2>变动幅度 Top</h2>
 <table><thead><tr><th>场次</th><th>首价</th><th>最新</th><th>变化</th><th>时点</th></tr></thead><tbody id="movers"></tbody></table>
</section>
</main>
<script>
const DATA={data}; let chart;
const artist=document.querySelector("#artist"), eventSel=document.querySelector("#event");
const eventList=()=>DATA.events.filter(e=>e.artist===artist.value);
function fillArtists(preferredArtist=artist.value,preferredEvent=eventSel.value){{
 artist.innerHTML=DATA.artists.map(a=>`<option>${{a}}</option>`).join("");
 artist.value=DATA.artists.includes(preferredArtist)?preferredArtist:(DATA.artists[0]||"");
 fillEvents(preferredEvent);
}}
function fillEvents(preferredEvent=eventSel.value){{
 const events=eventList();
 eventSel.innerHTML=events.map(e=>`<option value="${{e.id}}">${{e.city}} · ${{e.show.slice(0,10)}} · ${{e.delta_pct>=0?"+":""}}${{e.delta_pct}}%</option>`).join("");
 eventSel.value=events.some(e=>e.id===preferredEvent)?preferredEvent:(events[0]?.id||"");
 render();
}}
function render(){{
 const events=eventList(), e=events.find(x=>x.id===eventSel.value)||events[0];
 if(!e){{
  document.querySelector("#title").textContent="";
  document.querySelector("#summary").textContent="";
  if(chart){{chart.destroy();chart=undefined}}
  return;
 }}
 eventSel.value=e.id;
 document.querySelector("#title").textContent=e.label+" — "+e.tour;
 document.querySelector("#summary").textContent=`首价 ${{e.first}} · 最新 ${{e.last}} · 变化 ${{e.delta>=0?"+":""}}${{e.delta}} (${{e.delta_pct}}%) · ${{e.points}} 个时点 · ${{e.sources.join(" / ")}}`;
 if(chart)chart.destroy();
 chart=new Chart(document.querySelector("#chart"),{{type:"line",data:{{labels:e.categories,datasets:e.series.map(s=>({{label:s.name,data:s.data,tension:.2,borderWidth:2,pointRadius:2}}))}},options:{{responsive:true,interaction:{{mode:"index",intersect:false}},scales:{{y:{{title:{{display:true,text:"挂牌价（元）"}}}},x:{{title:{{display:true,text:"观测时间"}}}}}},plugins:{{legend:{{position:"bottom"}}}}}}}});
}}
artist.addEventListener("change",()=>fillEvents("")); eventSel.addEventListener("change",render);
fillArtists();
window.addEventListener("pageshow",()=>fillArtists(artist.value,eventSel.value));
const latest=DATA.runs[0]; if(latest){{
 const ok=["success","partial"].includes(latest.status);
 document.querySelector("#lastStatus").innerHTML=`<span class="${{ok?"ok":"bad"}}">${{latest.status}}</span>`;
 document.querySelector("#lastRows").textContent=latest.records_written??0;
}}
document.querySelector("#runs").innerHTML=DATA.runs.map(r=>`<div class="run"><span>${{r.completed_at||""}}</span><b class="${{["success","partial"].includes(r.status)?"ok":"bad"}}">${{r.status}}</b><span>${{r.records_written??0}} 条</span><span class="muted">${{Object.entries(r.sources||{{}}).map(([k,v])=>`${{k}}: ${{v.snapshots??0}}`).join(" · ")}}</span></div>`).join("");
document.querySelector("#movers").innerHTML=DATA.movers.map(e=>`<tr><td>${{e.label}}</td><td>${{e.first}}</td><td>${{e.last}}</td><td class="${{e.delta_pct<=0?"ok":"bad"}}">${{e.delta_pct>=0?"+":""}}${{e.delta_pct}}%</td><td>${{e.points}}</td></tr>`).join("");
</script></body></html>"""


def write_dashboard(payload: dict, output_dir: Path | str) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "trends.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    index = out / "index.html"
    index.write_text(_page(payload), encoding="utf-8")
    return index


def run(
    data_root: Path | str | None = None,
    output_dir: Path | str | None = None,
    *,
    open_browser: bool = True,
) -> int:
    root = Path(data_root) if data_root else data_root_from_env()
    destination = Path(output_dir) if output_dir else root / "site"
    payload = build_payload(root)
    path = write_dashboard(payload, destination)
    print(f"[trends] {payload['event_count']} 场 → {path}")
    if open_browser:
        webbrowser.open(path.resolve().as_uri())
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir")
    parser.add_argument("--output-dir")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    return run(args.data_dir, args.output_dir, open_browser=not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
