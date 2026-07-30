# ConcertOwl

零预算的演唱会票价走势采集与购票决策助手。GitHub Actions 每 6 小时自动发现关注歌手的全国场次，采集官方与二手挂牌价，并把历史写入仓库独立的 [`data`](../../tree/data) 分支。

> 仅供个人研究与购票决策。二手挂牌价不等于成交价；不提供自动抢票或下单。

## 稳定架构

```text
config/artists.yml
        │
GitHub Actions（每天 4 次）
        ├─ 自动发现场次
        ├─ 摩天轮 / MoreTickets / 票牛 / Cityline
        ├─ 变化检测 + 每日心跳
        └─ data 分支
             ├─ meta/Watchlist.csv
             ├─ meta/latest.json
             ├─ prices/YYYY/MM/DD/<run_id>.jsonl
             ├─ runs/YYYY/MM/DD/<run_id>.json
             └─ site/（静态走势页）
```

- `main`：代码、配置、测试和 Actions。
- `data`：由 `github-actions[bot]` 串行写入的数据分支。
- 价格或状态变化立即记录；价格不变时每天只留一次 `heartbeat`。
- 每轮都会写 run manifest，因此可以区分“价格没变”和“采集失败”。
- 不再依赖 Google Sheets，不需要 Google Secrets，也没有在线表格写配额。

## 直接查看

- [每场价格走势（GitHub Pages）](https://realatome.github.io/ConcertOwl/)
- [原始数据分支](https://github.com/RealAToMe/ConcertOwl/tree/data)
- Actions → `export-excel-report`：按歌手和日期范围生成 Excel，运行完成后下载 Artifact。

看板可按歌手和场次切换，显示：

- 摩天轮 / MoreTickets 的全场最低挂牌价；
- 票牛各官方面值档位的最低挂牌价；
- 首价、最新价、涨跌幅和观测时点；
- 最近采集是否成功、各来源返回量。

## 数据布局

### 元数据

`data` 分支的 `meta/Watchlist.csv`：

```text
event_id,artist,tour,city,region,venue,show_datetime,face_prices,
onsale_datetime,official_url,secondary_url,piaoniu_url,priority,active
```

自动发现会更新场次；人工填写的 `piaoniu_url`、官方链接和票面档位会被保留。

### 时序记录

一行 JSONL 代表一个“场次 × 来源 × 档位”的观测，核心字段包括：

- `observed_at`、`event_id`、`artist`、`city`、`show_datetime`
- `face_price`、`observed_price`、`premium_ratio`
- `currency`、`source`、`status`、`note`
- `series_key`、`collect_run_id`、`record_kind`

`record_kind` 为：

- `initial`：第一次见到该序列；
- `change`：价格或状态变化；
- `heartbeat`：当天首次确认价格未变；
- `migration`：从旧 Google Sheets 一次性迁移的历史。

## 数据源

- 摩天轮国内站：全国歌手搜索、场次详情、全场最低挂牌价。
- MoreTickets 国际站：港澳及海外场次、全场最低挂牌价。
- 票牛：按歌手自动发现；同歌手、同城市、日期唯一匹配后采集各票面档位。
- Cityline / 大麦：有官方链接时 best-effort 解析。

票牛自动关联会跳过代拍费、补款、预定金及歧义候选。

## 工作流

### `collect-prices`

- 定时：北京时间约 02:00 / 08:00 / 14:00 / 20:00。
- 可手动运行，支持 `skip_discover=1` 或 `dryrun=1`。
- 成功后提交 `data` 分支并部署 Pages。
- collector 的单场失败会进入 run manifest，但不会拖垮整轮；核心写入或 push 失败才使任务失败。

### `bootstrap-data-branch`

仅首次初始化空 `data` 分支时使用。当前仓库已完成初始化和历史迁移。

### `export-excel-report`

手动输入：

- `artist`：留空表示全部；
- `start` / `end`：可选 `YYYY-MM-DD`。

生成的 `.xlsx` 作为 Artifact 保留 30 天，不提交二进制文件进 Git。

## 本地使用

安装：

```powershell
python -m pip install -r requirements.txt
```

检出数据分支到并列目录：

```powershell
git worktree add ..\ConcertOwl-data data
$env:CONCERTOWL_DATA_DIR = "..\ConcertOwl-data"
```

生成并打开看板：

```powershell
python -m concertowl.view_trends
```

导出 Excel：

```powershell
python -m concertowl.export_excel --artist "薛之谦" --start 2026-07-01
```

本地 dry-run（不会改 `data` 分支）：

```powershell
$env:CONCERTOWL_DRYRUN = "1"
python -m concertowl.bootstrap_sheet
python -m concertowl.discover
python -m concertowl.run_collect
```

## 一次性 Sheets 迁移

生产运行不需要 Google 包。仅迁移旧历史时：

```powershell
python -m pip install -r requirements-migrate.txt
python -m scripts.migrate_from_sheets `
  --sheet-id "..." `
  --credentials "service-account.json" `
  --data-dir "..\ConcertOwl-data"
```

脚本会迁移 Watchlist 和所有 `价_*` 表、去除完全重复行、修复已知旧表头偏移并输出 `meta/migration_report.json`。

## 开发与测试

```powershell
python -m pytest -q
python -m compileall concertowl scripts
```

核心模块：

```text
concertowl/repo_history.py   不可变 JSONL、变化/心跳、run manifest
concertowl/storage.py        Watchlist 等仓库元数据存储
concertowl/discover.py       自动发现全国场次
concertowl/run_collect.py    采价编排与来源健康统计
concertowl/view_trends.py    静态走势页
concertowl/export_excel.py   按需 Excel
scripts/migrate_from_sheets.py
```

## 已知局限

- 平台接口或反爬策略变化时 collector 仍需维护。
- 仓库数据会持续增长；不可变分批文件与“变化 + 日心跳”已把增长压到线性。超过数百 MB 后可按年度打包归档到 Release。
- 挂牌价仅是市场代理指标，不保证实际成交。
