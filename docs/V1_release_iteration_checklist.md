# v1 封版与迭代清单

> 适用仓库：`trading_agent_ultra`  
> 基线日期：`2026-03-22`  
> 目标：形成可执行的 v1 封版流程，并给出后续迭代队列。

---

## A. 封版目标（Definition of Release）

v1 封版定义：
1. 宏观、行业、企业三层主链可跑通。
2. Supabase/PostgreSQL 结构化 SoT 稳定可用。
3. 关键数据有快照、delta、run log，可复盘。
4. 宏观 -> 行业联动队列可执行并具备失败保护。
5. 测试通过且主流程脚本可执行。

---

## B. 封版前检查清单（P0 必做）

## B1. 环境与依赖
- [ ] `.env` 配置完成：`APP_ENV`、`SUPABASE_DB_URL`、`SUPABASE_SCHEMA`
- [ ] 虚拟环境可用：`.venv`
- [ ] 依赖安装完成：`pip install -e '.[dev]'`

## B2. 数据库与迁移
- [ ] `alembic current` 显示在 `head`
- [ ] `alembic upgrade head` 可重复执行且无报错
- [ ] schema 为目标 schema（默认 `thesis`）

## B3. 自动化测试
- [ ] `pytest -q` 全绿
- [ ] 关键链路测试通过：
  - `test_linkage_pipeline.py`
  - `test_company_context_orchestrator.py`
  - `test_macro_industry_company_pipeline.py`

## B4. 主流程烟测（手动）
- [ ] 运行 `scripts/run_macro_daily.py`，成功生成 macro snapshot + delta + run_log
- [ ] 运行 `scripts/run_macro_industry_linkage.py`，成功入队 recheck
- [ ] 运行 `scripts/run_industry_recheck_queue.py`，队列状态正确更新（DONE/FAILED）
- [ ] 运行 `scripts/run_company_analysis.py`，成功生成 company_context + analysis_run

## B5. 观测与故障信息
- [ ] 日志中可看到：
  - `macro_industry_linkage_*`
  - `industry_recheck_*`
  - `company_context_build_*`
- [ ] recheck 失败时能在 `industry_recheck_queue.note` 查到错误
- [ ] company_context 失败时能在 `company_analysis_runs` 看到 `FAILED`

## B6. Git 与版本
- [ ] `main` 分支 clean
- [ ] 封版 commit 已推送远端
- [ ] 打 v1 标签（建议：`v1.0.0`）

---

## C. 封版后观察清单（上线后 3-7 天）

## C1. 稳定性
- [ ] 每日流程执行成功率 >= 95%
- [ ] recheck 队列未出现长期积压（`PENDING` 老化）

## C2. 数据质量
- [ ] `macro_master_snapshots` 每日有新增
- [ ] `industry_deltas` 在重检日有合理增量
- [ ] `company_context_snapshots` 与 `company_analysis_runs` 版本引用一致

## C3. 可复盘性
- [ ] 随机抽样 3 个交易日，能完整串联：snapshot -> delta -> run_log

---

## D. 迭代清单（按优先级）

## D1. P0（建议下个迭代完成）
1. 完成 `scripts/run_industry_weekly.py` 真正执行流程（候选生成 -> 批量 refresh -> run 记录）。
2. 为 `industry_weekly_refresh_runs` 接入落库逻辑。
3. 增加“空数据保护”与“重复运行幂等”检查（脚本层）。

## D2. P1（建议 1-2 个迭代内）
1. `company_data_service` 对接真实数据源（公司基础、行情、财务、新闻）。
2. `metrics_tools` 从空结构升级为可复用指标集（tech/valuation/quality/risk）。
3. `concept_tag_extractor` 从 placeholder 升级为 LLM 抽取 + 受控归一化。
4. analyst 输出从 placeholder 升级为结构化结论，并写入 `company_analyst_outputs`。

## D3. P2（可后置）
1. Graph 组装完善：`graphs/*` 从 placeholder 升级为实际 LangGraph workflow。
2. RLS 与更细粒度权限控制（Supabase）。
3. 语义检索层接入（如 pgvector），仅作辅助上下文。

---

## E. 延后决策（当前不阻塞 v1）
1. RLS 启用时机（建议 v1 稳定后）。
2. 向量库选型与部署策略。
3. analyst 明细输出保留周期与归档策略。

---

## F. 执行命令速查

```bash
# 测试
.venv/bin/python -m pytest -q

# 迁移
alembic upgrade head

# 每日主流程（建议顺序）
.venv/bin/python scripts/run_macro_daily.py --date 2026-03-22
.venv/bin/python scripts/run_macro_industry_linkage.py
.venv/bin/python scripts/run_industry_recheck_queue.py
.venv/bin/python scripts/run_company_analysis.py
```

---

## G. 封版结论记录（填写区）
- 封版日期：
- 封版 commit：
- 标签：
- 测试结果：
- 已知风险：
- 下一迭代负责人：
