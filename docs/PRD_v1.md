# Trading Agent Ultra PRD（v1 基线）

## 0. 文档信息
- 文档名称：`Trading Agent Ultra 产品需求文档（PRD）`
- 适用版本：`v1 基线`（当前仓库代码）
- 更新时间：`2026-03-22`
- 面向对象：个人投研系统（A 股为主，中文语料为主）

---

## 1. 产品目标与定位
### 1.1 产品目标
构建一个可持续更新的 A 股投研助手，形成“宏观 -> 行业 -> 企业”三层 Thesis 体系，支撑研究判断与后续组合/配置决策。

### 1.2 产品定位
- 不是一次性报告生成器。
- 是“状态化 thesis 系统”：有版本、有增量、有复盘。
- 以工程可维护性优先：强类型、模块化、可追踪、可迭代。

### 1.3 核心价值
- 用结构化对象管理观点变化（delta），减少重复重写。
- 用上游约束（宏观）修正中游（行业），再注入下游（企业）。
- 让每次分析可追溯：当时为什么判断、后来是否验证。

---

## 2. 范围定义（v1）
### 2.1 v1 目标范围（In Scope）
1. 宏观模块（Master Card + 4 类主题卡）与每日增量更新。
2. 行业模块（申万主对象）与 light/market/full 刷新机制。
3. 宏观 -> 行业联动队列（recheck queue）与执行器。
4. 企业层 `company_context` 组装（含宏观/行业摘要注入）。
5. Supabase PostgreSQL 作为结构化 SoT，Alembic 管理迁移。
6. 共享 DTO/枚举/字段规范统一（contracts）。
7. 基础可观测能力：运行日志、失败记录、重试机制。

### 2.2 v1 明确不做（Out of Scope）
1. 复杂宏观预测引擎、全量指标自动建模。
2. 多 agent 协作系统与复杂事件总线。
3. 全市场全自动覆盖（行业仅优先队列，非全量每日刷新）。
4. 申万二/三级全链路映射增强（当前重点仍在 L1 约束）。
5. 直接仓位建议与自动交易执行。
6. 完整知识图谱与无限扩张概念本体。

---

## 3. 用户与关键使用场景
### 3.1 用户画像
- 用户：你本人（投研主理人）。
- 使用方式：本地 Python 脚本 + 数据库查询 + 后续可扩展 API/UI。

### 3.2 关键场景
1. 每日宏观增量更新，输出是否 `material_change`。
2. 宏观变化后自动排队行业重检（按规则决定 light/market/full）。
3. 在请求企业分析时，自动组装 `company_context`（公司 + 宏观摘要 + 行业摘要）。
4. 复盘某日判断：查看快照、delta、run log、来源引用。

---

## 4. 系统架构（最终方向）

```text
Macro Module
  -> Integration (macro->industry linkage + recheck queue)
  -> Industry Module
  -> Company Context Orchestrator
  -> Company Module (analyst/debate placeholder)
```

### 4.1 依赖方向（强约束）
1. `macro` 不依赖 `industry/company`。
2. `industry` 只消费宏观公开 DTO，不反向改宏观状态。
3. `company` 通过 integration/tool 摘要消费宏观与行业，不直读其内部模型。
4. 跨模块共享只走 `contracts/`，不共享内部 ORM/业务对象。

---

## 5. 模块需求与当前实现状态

## 5.1 宏观模块（`macro/`）
### 5.1.1 功能目标
- 维护 Macro Master Card 与 4 类主题卡。
- 每日增量更新（事件驱动）并生成 delta。
- 输出 A 股风格影响与申万一级行业映射。
- 强制输出 `material_change`。

### 5.1.2 对外服务接口（已实现）
- `get_macro_master_card(as_of_date)`
- `get_macro_constraints_summary(as_of_date)`
- `get_macro_delta(since_version, since_date)`
- `get_macro_industry_mappings(version)`
- `run_daily_incremental_update(as_of_date, events)`

### 5.1.3 数据落库（已实现）
- `macro_master_snapshots`
- `macro_theme_snapshots`
- `macro_deltas`
- `macro_industry_mapping_snapshots`
- `macro_run_logs`

### 5.1.4 当前状态
- 已可运行。
- 事件 retriever 为可注入接口，默认空数据。

---

## 5.2 行业模块（`industry/`）
### 5.2.1 功能目标
- 基于申万 `industry_id` 维护 Thesis Card（支持 L1/L2/L3）。
- 支持 `light / market / full` 三类刷新。
- 支持 on-request refresh 与 weekly candidates（5-8）。

### 5.2.2 对外服务接口（已实现）
- `get_industry_thesis(industry_id, sw_level, as_of_date, auto_refresh)`
- `refresh_industry_thesis(industry_id, mode, sw_level, as_of_date)`
- `get_industry_delta(industry_id, since_version)`
- `get_industry_thesis_summary(industry_id, preferred_levels)`
- `get_weekly_refresh_candidates(limit, week_key, candidate_signals)`

### 5.2.3 数据落库（已实现）
- `industry_thesis_snapshots`
- `industry_thesis_latest`
- `industry_deltas`
- `industry_weekly_refresh_candidates`
- `industry_weekly_refresh_runs`（表已建，run 记录逻辑待增强）

### 5.2.4 当前状态
- 刷新触发器、prioritizer、updater 已有 v1 可运行规则。
- `run_industry_weekly.py` 仍是 skeleton 占位。

---

## 5.3 宏观-行业集成层（`integration/`）
### 5.3.1 功能目标
- 根据宏观 delta + 行业映射，决定行业重检。
- 通过队列异步执行行业刷新，避免强耦合。

### 5.3.2 对外能力（已实现）
- 宏观联动入队：`MacroIndustryLinkageService.enqueue_from_recent_deltas()`
- 重检规则编排：`IndustryRecheckOrchestrator`
- 队列执行器：`IndustryRecheckExecutor.run_pending(limit)`

### 5.3.3 数据落库（已实现）
- `industry_recheck_queue`
  - `PENDING / DONE / FAILED`
  - `note`（记录失败原因或重试尝试次数）
  - `updated_at`

### 5.3.4 稳定性能力（已实现）
- 执行器带重试：`shared/retry.py`
- 队列运行日志：start/done/failed

---

## 5.4 企业层模块（`company/`）
### 5.4.1 功能目标
- 从 `ticker` 构建标准化 `company_context`。
- 预先整合确定性数据、指标、概念标签、宏观/行业摘要。
- 为 analyst/debate 提供统一输入底稿。

### 5.4.2 当前主链（已实现）
`ticker -> company_data_service -> metrics_tools -> concept_tag_extractor -> company_context_assembler -> company_context`

### 5.4.3 对外服务接口（已实现）
- `CompanyService.build_company_context(ts_code, trade_date)`

### 5.4.4 数据落库（已实现）
- `company_context_snapshots`
- `company_analysis_runs`（已接入 SUCCESS/FAILED 记录）
- `company_analyst_outputs`（接口已留）

### 5.4.5 当前状态
- market/fundamental analyst 与 debate node 仍是 placeholder 输出。
- `company_context` 主体结构已稳定可用。

---

## 6. 统一 contracts 与字段规范（`contracts/`）

### 6.1 关键 DTO
1. Macro：`MacroMasterCardDTO` / `MacroConstraintsSummaryDTO` / `MacroDeltaDTO` / `MacroIndustryMappingDTO`
2. Industry：`IndustryThesisCardDTO` / `IndustryThesisSummaryDTO` / `IndustryDeltaDTO`
3. Company：`CompanyContextDTO` / `ComputedMetricsDTO`
4. Integration：`RecheckQueueItemDTO` / `IndustryRecheckDecisionDTO`
5. Shared Value Objects：`SourceRefDTO` / `ConfidenceDTO` / `MaterialChangeDTO` / `DeltaDTO`

### 6.2 统一字段原则
1. `version` 统一为字符串（跨模块引用通过 `*_ref.version`）。
2. `as_of_date` 用 `date`（业务时点）；`created_at/updated_at` 用 UTC `datetime`。
3. `delta` 统一包含：`changed_fields`、`summary`、`reasons`、`impact_scope`、`material_change`。
4. `source_refs` 统一结构：`source_type/title/retrieved_at` 为核心字段。
5. `confidence` 统一为 `score(0~1) + level(low/medium/high)`。
6. `material_change` 统一为结构体：`material_change(bool) + level + reasons[]`。

### 6.3 公共枚举
- `SwLevel`：`L1/L2/L3`
- `MappingDirection`：`POSITIVE/NEGATIVE/NEUTRAL`
- `UpdateMode`：`LIGHT/MARKET/FULL`
- `MacroBiasTag`：8 个固定枚举，最多 3 个且按排序体现主次

---

## 7. 存储与数据边界（Supabase/PostgreSQL）

### 7.1 锁定决策
1. 结构化 SoT：Supabase PostgreSQL。
2. Python 直连：`SQLAlchemy + psycopg`。
3. 迁移：Alembic。
4. v1 安全：服务端 schema + service role，RLS 延后。
5. 向量库仅辅助，不作为 thesis 状态主存储。

### 7.2 存储边界
1. `macro`：快照、delta、映射、run_log。
2. `industry`：最新+历史、delta、weekly candidate。
3. `integration`：recheck queue。
4. `company`：context 快照、analysis run、analyst output。

---

## 8. 运行流程（Runbook）

### 8.1 每日主流程（推荐）
1. 运行宏观更新：`scripts/run_macro_daily.py`
2. 宏观联动入队：`scripts/run_macro_industry_linkage.py`
3. 执行行业重检：`scripts/run_industry_recheck_queue.py`
4. 按需构建企业上下文：`scripts/run_company_analysis.py`

### 8.2 关键脚本
- `run_macro_daily.py`：支持 `--date`、`--events-file`
- `run_macro_industry_linkage.py`：按最新 macro delta 生成重检队列
- `run_industry_recheck_queue.py`：消费队列并刷新行业
- `run_company_analysis.py`：构建并保存 company_context
- `run_industry_weekly.py`：当前为 skeleton

---

## 9. LangGraph 与节点设计
### 9.1 当前状态
- 图组装文件存在：`graphs/*`，目前是稳定占位。
- 核心逻辑优先放在 service/tool/repository，node 层保持薄封装。

### 9.2 已落地节点
- `macro/nodes/daily_macro_update_node.py`
- `company/nodes/build_company_context_node.py`
- `company/nodes/market_analyst_node.py`
- `company/nodes/fundamental_analyst_node.py`
- `company/nodes/debate_node.py`（placeholder）

---

## 10. 质量、可观测与验收
### 10.1 已实现
1. 单元/集成测试：当前仓库 `29` 个测试通过。
2. 关键路径烟测：macro->industry->company pipeline 测试已覆盖。
3. 队列执行失败保护：重试 + FAILED 状态落库。
4. company_context 构建成功/失败 run 记录。

### 10.2 v1 最低验收标准
1. `alembic upgrade head` 成功。
2. `pytest -q` 全部通过。
3. 每日主流程脚本可串联跑通。
4. 表内可查到快照、delta、queue、run_log 记录。

---

## 11. 非功能需求（v1）
1. 代码可维护：模块边界清晰，避免巨型文件。
2. 可调试：关键步骤有 run log，错误可定位。
3. 可追溯：source refs、version refs、delta 可回放。
4. 性能：个人系统场景下优先稳定性而非高吞吐。

---

## 12. 版本规划与迭代方向

### 12.1 v1.0（当前）
- 完成三层结构骨架与 Supabase SoT。
- 完成 macro->industry 联动队列。
- 完成 company_context 主链组装。

### 12.2 v1.1（建议）
1. 补齐 `run_industry_weekly.py` 真正执行流程。
2. 增强 `company_data_service` 真实数据接入。
3. 完善 `metrics_tools` 指标计算。
4. 引入概念标签归一化（受控词表）。

### 12.3 v1.2（建议）
1. analyst 输出从 placeholder 升级为结构化判断。
2. debate 节点升级为可解释冲突整合器。
3. 逐步加入 RLS 与审计字段。

---

## 13. 需求提交与变更流程（以后按此 PRD 提需求）

### 13.1 变更提交原则
1. 每次需求必须指明影响模块：`macro / industry / integration / company / contracts / shared`。
2. 每次需求必须给出边界：`新增`、`改动`、`不改动`。
3. 涉及字段变化必须同步说明 DTO 与 DB 迁移。
4. 需求默认按“最小可用闭环”落地，不一次性大而全。

### 13.2 需求单模板（建议直接复制）

```md
# 需求标题

## 1. 目标
- 这次要解决的问题：
- 预期收益：

## 2. 影响范围
- 影响模块：
- 不应影响模块：

## 3. 输入/输出
- 输入来源：
- 输出对象（DTO/表/接口）：

## 4. 规则与约束
- 业务规则：
- 枚举/字段约束：

## 5. 存储与迁移
- 是否新增表/字段：
- 是否需要 Alembic 迁移：

## 6. 验收标准
- 功能验收：
- 测试验收：
- 回归风险点：

## 7. 非目标（本次不做）
- 
```

### 13.3 优先级定义
- `P0`：阻断主流程/数据一致性问题。
- `P1`：核心能力缺口，建议当前迭代完成。
- `P2`：体验优化或扩展能力，可排后续迭代。

---

## 14. 附录：当前仓库主目录职责
- `macro/`：宏观 thesis 与更新
- `industry/`：行业 thesis 与刷新
- `integration/`：跨模块桥接（宏观联动、context 编排）
- `company/`：企业上下文、analyst 节点
- `contracts/`：共享 DTO 与枚举
- `shared/`：配置、DB、日志、重试
- `scripts/`：可执行入口
- `alembic/`：数据库迁移
- `tests/`：单测与集成测试
