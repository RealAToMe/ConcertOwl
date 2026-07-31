# AGENTS.md

## Cursor Cloud specific instructions

ConcertOwl 是一个**零服务器的 Python CLI + GitHub Actions 数据工具**，没有长驻的后端/前端服务。生产采集完全由 `.github/workflows/collect.yml` 定时执行；本地只运行 CLI 模块。标准命令见 `README.md` 的「开发与测试」「本地使用」两节，这里只记录非显而易见的注意事项。

### 运行环境注意
- 用 `python3`（不是 `python`）——本环境没有 `python` 这个别名。
- 依赖已由更新脚本装到**系统 site-packages**（`pip install --break-system-packages -r requirements.txt`）。本环境的 `ensurepip`/`venv` 不可用，所以不用虚拟环境；直接 `python3 -m pytest` 即可。
- `requirements-migrate.txt`（`gspread`/`google-auth`）只在一次性 Google Sheets 迁移时需要，日常开发和测试不用装。

### 测试 / 编译（对应 `test` 工作流）
- `python3 -m pytest -q`（13 个测试，全部离线，秒级完成）。
- `python3 -m compileall concertowl scripts`（捕获语法/导入错误）。

### 采集 vs. 看板（重要）
- `concertowl.discover` 和 `concertowl.run_collect` 会访问外部中国票务站点（摩天轮 / MoreTickets / 票牛）。这些站点在 Cloud 沙箱里通常**不可达**，不要指望它们在本环境采到真实数据；需要跑通逻辑时用 dry-run（见 README）。
- 要**离线演示核心「价格走势看板」**：把 `data` 分支检出为并列 worktree，再对它跑 `view_trends` / `export_excel`：
  ```bash
  git fetch origin data
  git worktree add .data-worktree origin/data   # .data-worktree 已被 .gitignore 忽略
  python3 -m concertowl.view_trends --data-dir .data-worktree --output-dir /tmp/concertowl_site --no-browser
  CONCERTOWL_DATA_DIR=.data-worktree python3 -m concertowl.export_excel --artist "周杰伦"
  ```
  生成的看板是纯静态 HTML+JSON，可用 `python3 -m http.server` 起个静态服务在浏览器里查看。页面的 Chart.js 从 jsdelivr CDN 加载，需要浏览器能访问外网 CDN。

### 存储后端选择（`concertowl/storage.py`）
- 设了 `CONCERTOWL_DATA_DIR` 且 `CONCERTOWL_DRYRUN != "1"` → `RepoStorage`（写 `data` worktree 的 meta/prices/runs）。
- 否则 → 本地 CSV（`CONCERTOWL_LOCAL_DATA_DIR`，默认 `./data`，已被 gitignore）。对真实 `data` worktree 操作时**不要**设 `CONCERTOWL_DRYRUN`。
