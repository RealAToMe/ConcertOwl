# ConcertOwl

零预算的演唱会票价走势采集与购票决策助手。GitHub Actions 每 6 小时自动发现关注歌手的全国场次，采集官方与二手挂牌价，并把历史写入仓库独立的 [`data`](https://github.com/RealAToMe/ConcertOwl/tree/data) 分支。

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

## 功能总览

| 功能 | 工作方式 | 在哪里看 / 操作 |
|------|----------|-----------------|
| 歌手名单 | `config/artists.yml` 中 `active: true` 的歌手全国采集 | [`config/artists.yml`](config/artists.yml) |
| 城市偏好 | 只用于以后分析加权，不限制采集城市 | [`config/cities.yml`](config/cities.yml) |
| 自动发现场次 | 摩天轮国内/国际搜索后写入 Watchlist | `data` 分支 `meta/Watchlist.csv` |
| 票牛自动关联 | 同歌手、同城市、日期区间唯一命中才绑定 | Watchlist 的 `piaoniu_url` |
| 全场最低价 | 摩天轮 / MoreTickets 每场写一条 overall 序列 | Pages 或 JSONL |
| 官方面值分档 | 票牛按演出日期、票面档位记录最低挂牌价 | Pages 的多条分档曲线 |
| 变化过滤 | 价格或状态变化立即写入；完全相同不重复保存 | `meta/latest.json` |
| 每日心跳 | 当天首次确认“价格未变”仍写一条记录 | JSONL 的 `record_kind=heartbeat` |
| 运行健康记录 | 每轮记录尝试场次、返回量、空结果和错误数 | `runs/.../<run_id>.json` |
| 价格走势看板 | 从 JSONL 自动生成静态网页并部署 | [GitHub Pages](https://realatome.github.io/ConcertOwl/) |
| Excel 报告 | 按歌手和日期范围按需生成，不长期提交二进制 | Actions 的 `export-excel-report` |
| 自动测试 | main push 和 PR 自动执行测试与语法编译 | Actions 的 `test` |
| 历史迁移 | 旧 Google Sheets 已一次性迁入 JSONL | `meta/migration_report.json` |

## 直接查看

- [每场价格走势（GitHub Pages）](https://realatome.github.io/ConcertOwl/)
- [原始数据分支](https://github.com/RealAToMe/ConcertOwl/tree/data)
- Actions → `export-excel-report`：按歌手和日期范围生成 Excel，运行完成后下载 Artifact。

看板可按歌手和场次切换，显示：

- 摩天轮 / MoreTickets 的全场最低挂牌价；
- 票牛各官方面值档位的最低挂牌价；
- 首价、最新价、涨跌幅和观测时点；
- 最近采集是否成功、各来源返回量。

网页本身不写数据，只读取每轮采集后生成的静态 JSON，因此不会引入新的数据库或在线表格依赖。

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
- 修改并推送核心代码到 `main` 时也会运行一次。
- 可手动运行，支持 `skip_discover=1` 或 `dryrun=1`。
- 成功后提交 `data` 分支并部署 Pages。
- collector 的单场失败会进入 run manifest，但不会拖垮整轮；核心写入或 push 失败才使任务失败。

完整执行顺序：

1. checkout `main` 中的应用代码；
2. 把 `data` 分支 checkout 到独立 worktree；
3. 安装 Python 依赖；
4. 搜索关注歌手的新场次；
5. 合并 Watchlist，并保留人工 URL；
6. 对每场调用适用的 collector；
7. 用 `meta/latest.json` 判断初始值、变化、心跳或未变；
8. 写入本轮不可变 JSONL 和 run manifest；
9. 生成最新 HTML/JSON 看板；
10. 由 `github-actions[bot]` 提交并 push `data`；
11. 上传并部署 GitHub Pages。

手动运行参数：

- `dryrun=0`：正常采集、提交数据并部署（默认）；
- `dryrun=1`：只做临时调试，不提交 `data`，也不部署 Pages；
- `skip_discover=0`：先发现新场次再采价（默认）；
- `skip_discover=1`：跳过发现，直接采已有 Watchlist。

### `bootstrap-data-branch`

仅首次初始化空 `data` 分支时使用。当前仓库已完成初始化和历史迁移。

### `export-excel-report`

手动输入：

- `artist`：留空表示全部；
- `start` / `end`：可选 `YYYY-MM-DD`。

生成的 `.xlsx` 作为 Artifact 保留 30 天，不提交二进制文件进 Git。

使用方法：

1. 打开仓库的 **Actions**；
2. 左侧选择 **export-excel-report**；
3. 点击 **Run workflow**；
4. 可填写歌手、开始日期和结束日期；
5. 等运行显示绿色 Success；
6. 打开该次运行，在页面底部 **Artifacts** 下载 Excel。

### `test`

- push 到 `main` 或创建 PR 时自动运行；
- 执行全部 pytest；
- 编译 `concertowl/` 与 `scripts/`，捕获语法和导入错误；
- 测试失败不会写 `data` 分支。

## GitHub 通知与失败状态

GitHub 的通知是**按单次 workflow run 发送**的。一轮失败后，即使后续已经修复并重跑成功，旧运行仍然保持红色，旧的 failed 邮件/通知也不会被撤回，所以可能晚一点才收到。

判断当前系统是否正常时，不要只看一封通知，应检查：

1. 通知中的运行时间和 run 编号；
2. Actions 首页最上方的最新 `collect-prices`；
3. [价格看板](https://realatome.github.io/ConcertOwl/)里的“最近采集”；
4. `data/runs/.../<run_id>.json` 的 `status`。

状态含义：

- GitHub Actions **Success**：采价、数据 push、Pages 部署均完成；
- manifest `status=success`：collector 没有抛出错误；
- manifest `status=partial`：个别来源/场次失败，但其他数据已安全保存，workflow 可以继续成功；
- GitHub Actions **Failed**：查看红色步骤；若失败发生在 Pages，前面的数据 commit 可能已经成功；
- `records_written=0`：不一定失败，可能只是本轮所有价格都没变化。

本仓库迁移时的首次 Pages 运行曾因尚未启用 Pages 而在 `Configure Pages` 步骤失败；之后已启用并重跑成功。该旧 failed 记录和通知会保留，这是 GitHub 的正常行为，不代表当前任务仍然失败。

最近状态可从以下入口确认：

- [全部 Actions](https://github.com/RealAToMe/ConcertOwl/actions)
- [collect-prices](https://github.com/RealAToMe/ConcertOwl/actions/workflows/collect.yml)
- [test](https://github.com/RealAToMe/ConcertOwl/actions/workflows/test.yml)
- [export-excel-report](https://github.com/RealAToMe/ConcertOwl/actions/workflows/export-report.yml)

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

本地对真实 `data` worktree 运行时不要设置 `CONCERTOWL_DRYRUN`。正常情况下无需在个人电脑运行采价，GitHub Actions 会自动完成。

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

## 运维约定

- 不要手工修改 `prices/`、`runs/` 或 `meta/latest.json`；它们由程序维护。
- 如需补 Watchlist 的人工 URL，可编辑 `meta/Watchlist.csv`，但应避开正在运行的采集任务，并保留完整表头。
- `data` 分支是唯一生产历史；`main/data/*.csv` 只是被忽略的本地 dry-run 文件。
- Google Sheets Secrets 已不再使用，可以从仓库 Secrets 删除。
- Excel 是派生产物，应通过 Artifact 下载，不要提交进 Git。
- 数据量达到数百 MB 后，按年份归档旧 JSONL 到 GitHub Release，同时保留 latest 与近期数据。
