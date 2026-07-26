# ConcertOwl

零预算的**演唱会票价走势采集与购票决策助手**。用 GitHub Actions 在云端定时采集你关注的歌手/城市的官方与二手票价，写入 Google Sheets，并给出三类决策建议：

1. **抢票倾向** —— 开售后二手大概率溢价，值得抢/可接受代抢成本吗？
2. **等待降价倾向** —— 大概率软场（卖不完），可以等二手更便宜吗？
3. **临场底价区间** —— 临时想去，开演前几天的底价大概是多少？

> 仅供个人研究与购票决策使用。严格低频采集；不做脚本抢票/下单；不对外提供服务。二手挂牌价 ≠ 成交价，仅作代理指标。

## 架构

```
Cities/Artists 白名单  ->  Watchlist(你维护)  ->  GitHub Actions(cron)
                                                     |
                    大麦官方价/售罄  摩天轮二手最低价  Cityline港澳官方
                                                     |
                                              PriceSnapshots(历史)
                                                     |
                                              Decision(三类建议)
```

| 层级 | 方案 | 费用 |
|------|------|------|
| 定时任务 | GitHub Actions（cron） | 免费 |
| 存储/看板 | Google Sheets | 免费 |
| 本地调试 | 落地为 `data/*.csv` 的 dry-run | 免费 |

## 关注范围（第一版硬边界）

- **城市**：香港、澳门、广州、深圳、上海、苏州、杭州、南京、北京、天津（见 [`config/cities.yml`](config/cities.yml)）
- **歌手**：陈奕迅、孙燕姿、王菲、林俊杰、王力宏、陶喆、李宇春、张靓颖、杨千嬅、陈粒、周深、韦礼安、汪苏泷、张远、王铮亮等（见 [`config/artists.yml`](config/artists.yml)）
- 港星默认只开杨千嬅，其余把 `active` 改成 `true` 即可采集。
- 白名单外的城市/歌手一律不采集（例如某歌手成都站会被跳过）。

## 目录结构

```
config/                白名单：cities.yml / artists.yml
concertowl/
  models.py            数据模型（WatchEvent / PriceSnapshot）
  config.py            加载白名单与匹配
  storage.py           存储后端：Google Sheets 或本地 CSV
  watchlist.py         读 Watchlist + 白名单校验
  bootstrap_sheet.py   初始化表头 + 写入白名单
  run_collect.py       采集主入口
  decision.py          生成三类决策，刷新 Decision 表
  collectors/          damai / moretickets / cityline 适配器
.github/workflows/     collect.yml(定时) / bootstrap.yml(手动)
```

## 观察期怎么跑（先攒数据，暂不做分析）

你现在还不需要手动填关注场次。系统会：

1. **自动发现**：按 `config/artists.yml` 里 `active: true` 的歌手，在白名单城市里找 MoreTickets 挂牌场次，写入 `Watchlist`
2. **定时采价**：把每场最低挂牌价追加到 `PriceSnapshots`
3. **暂不跑 Decision**（分析以后再说）

### 推荐频率

| 任务 | 频率 | 原因 |
|------|------|------|
| 发现 + 采价 | **每 6 小时（一天 4 次）** | 够画走势，又不至于触发反爬 / 烧光 Actions 分钟 |
| 临场加密 | 以后再加（开演前 7 天可改为 3–4 小时） | 临场波动大时才需要更密 |

当前 workflow 已按「每 6 小时」配置。在 GitHub Actions 里手动跑一次 `collect-prices` 即可开始观察；之后关机也没关系，云端会继续跑。

> 现阶段主数据源是 **MoreTickets 国际站公开 API**（港澳覆盖最好，部分大陆场次也会出现）。大麦反爬强，观察期先不依赖它。

## 本地跑通（dry-run，无需任何凭证）

```bash
pip install -r requirements.txt

# 1) 生成本地表（data/*.csv），并写入白名单
set CONCERTOWL_DRYRUN=1        # PowerShell: $env:CONCERTOWL_DRYRUN=1
python -m concertowl.bootstrap_sheet

# 2) 手动往 data/Watchlist.csv 加几场演出（列见下），保存

# 3) 采集（会真的去请求你填的 URL）
python -m concertowl.run_collect

# 4) 生成决策
python -m concertowl.decision
```

`Watchlist` 列：
`event_id, artist, tour, city, region, venue, show_datetime, face_prices, official_url, secondary_url, priority, active`

- `official_url`：大麦详情页或 Cityline 事件页
- `secondary_url`：摩天轮/MoreTickets 详情页
- `face_prices`：官方档位，如 `380/680/980/1280`
- `show_datetime`：ISO，如 `2026-08-22T19:00`

## 部署到云端（GitHub Actions + Google Sheets）

1. 新建一个 Google Sheet，记下 URL 里的 `SHEET_ID`。
2. Google Cloud 建 Service Account，开启 **Google Sheets API** 与 **Drive API**，下载 JSON 密钥。
3. 把该 Sheet **共享给** service account 邮箱（编辑者）。
4. 在仓库 Settings → Secrets → Actions 里加：
   - `GOOGLE_CREDENTIALS`：整段 JSON
   - `SHEET_ID`：表格 ID
5. 手动跑一次 **bootstrap-sheet** 工作流生成各表与白名单。
6. 在表格的 `Watchlist` 页填入关注场次。
7. **collect-prices** 会按 cron（默认每天 4 次，北京时间约 01/09/15/21 点）自动采集并刷新 `Decision`。

### 采集频率建议

在 `.github/workflows/collect.yml` 的 cron 里按需调整：距开演越近可以越密（临场 2-3 小时一次），平时每天 2-4 次即可，避免烧配额与触发反爬。

## 已知局限与维护

- **适配器会坏**：平台改接口/加验证码是常态，按「坏了再修」维护 `collectors/`。
- **解析是 best-effort**：拿不到结构化 JSON 时退回正则抓最低价，可能不准；`raw_note` 会标注来源。
- **挂牌价 ≠ 成交价**，决策时请留余量。
- **置信度初期低**：前期主要在攒你自己的历史，名单内场次越多，相似对照越准。

## 明确不做

自动抢票/下单、代理 IP 池、机器学习大模型、独立公网网站、任何付费云资源、白名单外的全站爬取。
