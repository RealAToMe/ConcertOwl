# ConcertOwl

零预算的**演唱会票价走势采集与购票决策助手**。用 GitHub Actions 在云端定时采集你关注歌手的官方与二手票价，写入 Google Sheets；城市偏好用于以后分析加权。

观察期先攒历史；以后再做三类决策建议：

1. **抢票倾向** —— 开售后二手大概率溢价，值得抢/可接受代抢成本吗？
2. **等待降价倾向** —— 大概率软场（卖不完），可以等二手更便宜吗？
3. **临场底价区间** —— 临时想去，开演前几天的底价大概是多少？

> 仅供个人研究与购票决策使用。严格低频采集；不做脚本抢票/下单；不对外提供服务。二手挂牌价 ≠ 成交价，仅作代理指标。

## 架构

```
Artists关注名单  ->  自动发现全国场次  ->  GitHub Actions(cron)
Cities偏好城市  ----------------------+->  以后分析时同城加权
                                      |
       大麦官方分档 / 摩天轮国内+国际 / 票牛分档 / Cityline
                                      |
                               PriceSnapshots(按档位分行)
```

| 层级 | 方案 | 费用 |
|------|------|------|
| 定时任务 | GitHub Actions（cron） | 免费 |
| 存储/看板 | Google Sheets | 免费 |
| 本地调试 | 落地为 `data/*.csv` 的 dry-run | 免费 |

## 关注范围

- **采集（歌手为主）**：`config/artists.yml` 里 `active: true` 的歌手，**全国场次都收录**。想加歌手告诉我，或自己改 yml。
- **城市偏好（分析用）**：见 [`config/cities.yml`](config/cities.yml)。不参与采集过滤；以后问「北京杨千嬅」时，同城样本权重更高。
- **价格表结构（时序）**：每位歌手一张表 `价_歌手名`，**每次观测追加一行**，便于画走势：
  - `observed_at`：观测时间（精确到分钟）
  - `event_id` / `city` / `tour` / `show_datetime`
  - `face_price`：官方档位面值（如 388）
  - `observed_price`：本次观测挂牌价
  - `premium_ratio`、`days_to_show`、`days_since_onsale`、`currency`、`source`、`status`、`note`
- **数据源现状**：
  - 摩天轮国内站：全国歌手搜索、演出详情、全场最低挂牌价（`overall_min`）
  - MoreTickets 国际站：港澳及海外场次、全场最低挂牌价
  - 票牛：公开网页 API，可按日期场次和官方票面档位采集最低挂牌价
  - 大麦反爬较强，官方分档接口仍不稳定
  - 摩天轮国内网页端不返回分档卖家库存，分档价格仍只在 App 购买链路中
  - 旧的整表 `PriceSnapshots` 可手动删除

## 目录结构

```
config/                artists.yml（采集）/ cities.yml（分析偏好）
concertowl/
  models.py            WatchEvent / PriceSnapshot
  snapshots.py         按歌手分表追加时序观测
  discover.py          按歌手自动发现全国场次
  run_collect.py       采集主入口
  collectors/          damai / moretickets / piaoniu / cityline
  mtl_cn_api.py        摩天轮国内站全国搜索与详情
.github/workflows/     collect.yml(定时) / bootstrap.yml(手动)
```

## 观察期怎么跑（先攒数据，暂不做分析）

1. **自动发现**：关注歌手的全国场次写入 `Watchlist`
2. **定时采价**：写入对应 `价_歌手` 表（每次观测一行）
3. **暂不跑 Decision**

### 推荐频率

| 任务 | 频率 | 原因 |
|------|------|------|
| 发现 + 采价 | **每 6 小时（一天 4 次）** | 够画走势，又不易触发反爬 |
| 临场加密 | 以后再加 | 临场波动大时再加密 |

推送后请手动跑一次 **bootstrap-sheet**（重建 `价_*` 表头），再跑 **collect-prices**。

> 票牛活动暂不能稳定按歌手自动搜索关联。自动发现仍以摩天轮为主；找到同一活动的票牛链接后填入 `piaoniu_url`，即可同时采集票牛分档价。

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
`event_id, artist, tour, city, region, venue, show_datetime, face_prices, onsale_datetime, official_url, secondary_url, piaoniu_url, priority, active`

- `official_url`：大麦详情页或 Cityline 事件页
- `secondary_url`：摩天轮/MoreTickets 详情页
- `piaoniu_url`：票牛活动页，如 `https://x.piaoniu.com/activity/769142`
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

自动抢票/下单、代理 IP 池、机器学习大模型、独立公网网站、任何付费云资源、非关注歌手的全站爬取。
