# algo-trader

This repo is the orchestration layer (Docker Compose, startup scripts, dev tooling). The trading engine source code lives in the sibling repo `../trading-platform/`.

## CodeGraph

CodeGraph is initialized in `../` (the `trading/` workspace root) — **not** in this directory. When using any codegraph tool, always pass `projectPath: "C:/Users/saket/workspace/trading"`.

**NEVER call `codegraph_explore` or `codegraph_context` directly in the main session.** Spawn an Explore agent instead. Include this in the prompt:

> This project has CodeGraph initialized at `C:/Users/saket/workspace/trading`. Use `codegraph_explore` as your PRIMARY tool, passing `projectPath: "C:/Users/saket/workspace/trading"` on every call.
>
> **Rules:**
> 1. Follow the explore call budget in the `codegraph_explore` tool description.
> 2. Do NOT re-read files that codegraph_explore already returned source code for.
> 3. Only fall back to grep/glob/read for files listed under "Additional relevant files" if you need more detail.

**If `codegraph_status` returns "database is locked"**, delete the stale lock file first:
```powershell
Remove-Item "C:/Users/saket/workspace/trading/.codegraph/codegraph.db.lock" -Force
```
Then retry.

**Lightweight tools** (safe to use directly in the main session — always pass `projectPath`):

| Tool | Use For |
|------|---------|
| `codegraph_search` | Find symbols by name |
| `codegraph_callers` / `codegraph_callees` | Trace call flow |
| `codegraph_impact` | Check what's affected before editing |
| `codegraph_node` | Get a single symbol's details |
| `codegraph_status` | Verify index is up to date |

## Source layout

| Directory | Purpose |
|-----------|---------|
| `../trading-platform/` | Trading engine — pipeline, strategies, registries, broker adapters |
| `../trading-integ-tests/` | Integration tests (strategy backtesting, system e2e) for trading-platform |
| `../trading-dashboard/` | Monitoring dashboard |
| `../quantindicators/` | Indicator library |
| `./` | Dev tooling — `dev.py`, `docker-compose.yml`, startup scripts |
