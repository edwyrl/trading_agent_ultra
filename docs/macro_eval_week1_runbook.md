# Macro Eval Week 1 Runbook

本手册用于第一周落地「每日人工评审 + 每周调参」闭环。

## 0) 一次性配置（可选）

若希望评估邮件顶部直接出现 Google Form 链接，在 `.env` 增加：
```bash
MACRO_EVAL_GOOGLE_FORM_URL=<你的Google Form链接>
MACRO_EVAL_FORM_ENTRY_DATE=<date字段的entry编号>
MACRO_EVAL_FORM_ENTRY_SAMPLE_ID=<sample_id字段的entry编号>
MACRO_EVAL_FORM_ENTRY_SELECTED=<selected字段的entry编号>
MACRO_EVAL_FORM_ENTRY_TOPIC=<topic字段的entry编号>
MACRO_EVAL_FORM_ENTRY_EVENT_ID=<event_id字段的entry编号>
MACRO_EVAL_FORM_SELECTED_TRUE_VALUE=True
MACRO_EVAL_FORM_SELECTED_FALSE_VALUE=False
```

说明：
- 配好上述 `entry` 后，评估邮件会自动为当天 12 条样本生成 12 个“预填链接”。
- `date` 使用当日 `eval_pack.as_of_date` 自动填充，不需要手工改日期。
- `selected` 的预填值默认是 `True/False`，若你的 Form 选项不同（如 `true/false`），改上面两个值即可。

## 1) 每日执行（Owner：你）

### 上午（可选巡检，约 5 分钟）
```bash
tail -n 80 logs/macro_intel_cron.log
```
检查昨晚 20:00 任务是否成功（`rc=0`）。

### 晚上（主流程，建议 20:05-20:20）
1. 确认当天 `eval_pack` 已生成：
```bash
ls -l logs/macro_eval_pack_latest.json
```

2. 预览评审邮件（建议先 dry-run）：
```bash
PYTHONPATH=. ./.venv/bin/python scripts/send_macro_digest_email.py --eval-mode --dry-run
```

3. 发送评审邮件（若 dry-run 结构正常）：
```bash
PYTHONPATH=. ./.venv/bin/python scripts/send_macro_digest_email.py --eval-mode
```

4. 你收到邮件后，按模板回填每条样本 4 项：
- `该不该报`：`Y/N`
- `重不重要`：`H/M/L`
- `是否重复`：`Y/N`（若 `Y` 填重复 `sample_id`）
- `漏了什么`：可空；若有填 `title + url + 1行原因`
- 若使用 Google Forms（推荐最简字段）：
  - `selected` 使用你 Form 中的固定选项（默认 `True/False`）
  - `should_report` 固定用 `Y/N`
  - `importance` 固定用 `H/M/L`
  - `is_duplicate` 固定用 `Y/N`

## 2) 每日验收标准（快速）

- `eval_pack` 存在且结构正常：
  - `selected_samples` 最多 6 条
  - `non_selected_samples` 最多 6 条
  - 样本字段齐全：`sample_id/event_id/topic/title/url/score/source_domain/selected`
- 评审邮件中入选和未入选两块都能看到。
- 邮件正文含 4 项回填提示。

## 3) 每周执行（建议周日 20:30，Owner：你）

### Step A. 整理一周反馈为 CSV
用下列模板表头（可直接复制）：
- 参考文件：`docs/macro_eval_feedback_template.csv`
- 建议命名：`logs/macro_eval_feedback_YYYYWww.csv`

### Step B. 生成周报（指标 + 调参建议）
```bash
PYTHONPATH=. ./.venv/bin/python scripts/build_macro_eval_weekly_report.py \
  --input-csv logs/macro_eval_feedback_2026W15.csv \
  --week-label 2026-W15 \
  --output-md logs/macro_eval_weekly_report_2026W15.md \
  --output-json logs/macro_eval_weekly_report_2026W15.json
```

### Step C. 按规则执行调参（每周最多 3 项）

1. `FN Proxy > 30%` 或 `Miss Count >= 3`  
动作：对问题集中 topic 执行 `阈值 -3`，或补 1-2 条 query。

2. `Selected Precision < 70%`  
动作：对误报集中 topic 执行 `阈值 +3`，并收紧 source/profile。

3. `Duplicate Rate > 20%`  
动作：`dedup/cluster` 相似度阈值各下调 `0.02~0.03`（提高合并力度）。

4. `Importance Hit Rate < 50%`  
动作：调 `quotas`，提高政策/核心数据 topic 配额，压低噪声 topic 配额。

## 4) 异常处理（第一周）

1. `eval_pack_missing`
- 先跑一次：
```bash
PYTHONPATH=. ./.venv/bin/python scripts/run_macro_intel_cycle.py --date "$(date +%F)"
```
- 再重发 `--eval-mode`。

2. 当天样本少于 12 条
- 属于可接受降级（系统会输出 shortage，非故障）。
- 当周不做紧急处理，周度再看是否长期不足。

3. Tavily/Bocha 偶发 SSL/网络错误
- 先观察是否仅单 query；若主流程成功无需当天改规则。
- 若连续多天影响样本覆盖，再在周会中调整 query/source。

## 5) 第一周最小交付物清单

- 每天至少 1 封评审邮件（建议保留邮件记录）。
- 一份周反馈 CSV。
- 一份周报 Markdown + JSON。
- 一份调参变更清单（最多 3 项，明确修改前后值）。
