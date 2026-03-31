# Macro 模块文档（v1：Tavily + Bocha 资讯管线）

## 1. 目标
本版本仅聚焦宏观资讯链路落地：
- 用 `Bocha + Tavily` 做双引擎检索。
- 以“事件”为核心对象（不是文章列表）。
- 先落 `macro_event_history -> macro_event_views`，再驱动 `macro_master/theme snapshots`。

## 2. 分层设计
### 2.1 第一层：常规宏观层
覆盖中国、美国、跨市场主线：
- 货币
- 财政
- 通胀
- 就业
- 增长
- 汇率

### 2.2 第二层：哨兵层
覆盖高冲击主题：
- 地缘政治
- 能源冲击
- 制裁/关税/出口管制
- 金融稳定
- 市场异常波动

## 3. 路由规则
- 中文 + 中国本地：默认 `bocha`
- 英文 + 美国/国际：默认 `tavily`
- 高影响主题（地缘/能源/制裁/金融稳定/汇率等）：强制双搜（`bocha + tavily`）

路由实现：
- 文件：`macro/intel/router.py`
- 配置：`macro/config/macro_intel.yaml -> routing`

## 4. 白名单与来源权重
按 `CN / INTL` 两套来源权重管理：
- CN 例：`gov.cn`, `pbc.gov.cn`, `data.stats.gov.cn`
- INTL 例：`federalreserve.gov`, `treasury.gov`, `reuters.com`

作用：
1. 提升信噪比（域名过滤）
2. 给事件评分中的 `source_weight` 提供依据

配置：`macro/config/macro_intel.yaml -> sources`

## 5. 引擎参数
- Tavily 参数：`search_depth`, `max_results`, `include_raw_content`
- Bocha 参数：`count`, `freshness_days`

配置：`macro/config/macro_intel.yaml -> engines`

环境变量：
- `TAVILY_API_KEY`
- `TAVILY_BASE_URL`
- `BOCHA_API_KEY`
- `BOCHA_BASE_URL`
- `MACRO_INTEL_TIMEOUT_SECONDS`
- `MACRO_INTEL_CONFIG_PATH`

## 6. 处理链路

```text
query specs
-> router (single/dual)
-> tavily/bocha search
-> document dedup (URL/标题相似)
-> event clustering (同主题+时间窗+标题相似)
-> event scoring
-> upgrade 判定
-> MacroEvent 列表
-> MacroUpdater
-> macro_event_history / macro_event_views
-> macro_theme_snapshots / macro_master_snapshots / macro_deltas / mappings
```

核心文件：
- `macro/intel/pipeline.py`
- `macro/intel/clients.py`
- `macro/intel/dedup.py`
- `macro/intel/clustering.py`
- `macro/intel/scoring.py`

## 7. 评分（按事件）
统一按事件评分，不按文章评分。
维度：
1. `source_weight`
2. `event_severity`
3. `market_impact`
4. `freshness`
5. `cross_source_confirm`
6. `transmission_chain`

总分 `0-100`。
阈值在 YAML 可配置（默认 `high=75`, `medium=55`）。

## 8. 升级规则
满足任一即可升级为宏观候选：
- 命中升级关键词（能源、制裁、关税、汇率、流动性等）
- 命中市场联动关键词（oil、treasury yield、dollar、gold 等）
- 或本身属于哨兵层事件

## 9. 去重与归并
### 9.1 文档级去重
- URL 精确去重
- 标题标准化 + 相似度去重

### 9.2 事件级归并
- 同 topic
- 同时间窗（默认 48h）
- 标题相似度达到阈值

输出是 `event cluster`，不是原始文章列表。

## 10. 与现有表的关系
### 10.1 事实/观点层
- `macro_event_history`：事件状态演进（append-only）
- `macro_event_views`：事件级观点（SOURCE/AGENT/MANUAL）

### 10.2 聚合观点层
- `macro_theme_snapshots`
- `macro_master_snapshots`
- `macro_deltas`
- `macro_industry_mapping_snapshots`

并在 snapshot 中保留：
- `evidence_event_ids`
- `evidence_view_ids`

## 11. 运行方式
### 11.1 单次执行
```bash
.venv/bin/python scripts/run_macro_intel_cycle.py --date 2026-03-25
```

### 11.2 通过 daily 脚本启用 intel 模式
```bash
.venv/bin/python scripts/run_macro_daily.py --use-intel --date 2026-03-25
```

### 11.3 调度建议（Asia/Shanghai）
- 08:00 一次
- 20:00 一次

推荐使用安装脚本（会写入本地 crontab）：
```bash
chmod +x scripts/run_macro_intel_cron.sh scripts/setup_macro_cron.sh
./scripts/setup_macro_cron.sh --install
./scripts/setup_macro_cron.sh --show
```

手工 Cron 示例：
```bash
CRON_TZ=Asia/Shanghai
0 8,20 * * * /path/to/trading_agent_ultra/scripts/run_macro_intel_cron.sh
```

## 12. 当前已知限制（v1）
1. Bocha API 响应结构存在供应商差异，当前使用通用解析策略。
2. 事件归并目前为规则法（标题相似 + 时间窗），后续可升级语义聚类。
3. `macro_event_views` 当前默认写入 SOURCE 视角，AGENT/MANUAL 视角预留待扩展。
4. 向量检索未启用，结构化 Postgres 仍是 SoT。

## 13. 定时邮件（Resend）
目标：
- 每次 cron 触发后，发送近 24 小时的宏观事件 + 观点摘要到离线文档维护的邮箱列表。

相关文件：
- `scripts/send_macro_digest_email.py`
- `macro/notifier.py`
- `docs/macro_digest_recipients.md`

环境变量：
- `RESEND_API_KEY`
- `RESEND_BASE_URL`（默认 `https://api.resend.com/emails`）
- `RESEND_FROM_EMAIL`
- `MACRO_DIGEST_RECIPIENTS_DOC_PATH`
- `MACRO_DIGEST_SUBJECT_PREFIX`

手动测试：
```bash
.venv/bin/python scripts/send_macro_digest_email.py --hours 24 --dry-run
.venv/bin/python scripts/send_macro_digest_email.py --hours 24
```

## 14. 验收点
1. `pytest -q` 全绿。
2. `run_macro_intel_cycle.py` 可执行。
3. 当有检索结果时，`macro_event_history` 与 `macro_event_views` 有新增。
4. `macro_master_snapshots`、`macro_deltas`、`mapping` 同步产生。
