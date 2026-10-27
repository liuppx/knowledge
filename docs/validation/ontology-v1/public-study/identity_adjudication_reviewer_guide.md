# 身份裁决队列评审者指引（公开演练）

本指引面向被任务负责人指派的**两名非开发者评审者**和一名 adjudicator，用于独立完成
[`identity_adjudication_queue_v1.csv`](identity_adjudication_queue_v1.csv) 的 29 条待裁决记录。

> 这是**公开采购来源**的方法学演练，不是真实用户数据，也不能把演练耗时外推为真实业务成本。
> 字段定义和统计口径以 [`../real-study/README.md`](../real-study/README.md) 为准，本指引只补充操作步骤。

## 角色与独立性

- **Reviewer A / Reviewer B**：各自独立判断每条来源标识能否由权威证据映射到 LEI。两人
  **不得共享候选、结论、证据或耗时**，不得互相讨论任何一条记录，直到各自全部提交。
- **Adjudicator**：只处理 A/B 结论不一致的记录，记录最终结论、证据与处理耗时；不得替某一方补填。
- 三人都使用稳定的**假名 ID**（例如 `rev-a-01`、`rev-b-01`、`adj-01`），不写真实姓名。

## 每条记录的判定步骤

1. 只读队列中已公开的字段：`source_role`、`source_name`、`source_identifier`、
   `source_identifier_type`、`identifier_namespace_status`。**不要**查看他人列，也不要查看系统预判。
2. 按冻结的来源清单和时间范围查权威证据（见下「允许的权威来源」），判断来源 ID + namespace
   能否映射到唯一 LEI。
3. 从以下枚举中选一个 `outcome`：
   - `authoritative_crosswalk_confirmed`：权威来源同时证明来源 ID、namespace 和 LEI；
   - `candidate_requires_adjudication`：找到候选但缺完整权威 crosswalk；
   - `no_crosswalk_found_in_checked_sources`：按冻结来源和时间范围检查后仍无 crosswalk；
   - `ambiguous`：多个可能实体或 crosswalk 相互冲突；
   - `insufficient_evidence`：无法完成必要查询或证据不可访问。
4. 填写本方全部必填列：`{prefix}_id`、`{prefix}_outcome`、`{prefix}_resolution_method`、
   `{prefix}_evidence_uri`、`{prefix}_started_at_utc`、`{prefix}_submitted_at_utc`、
   `{prefix}_duration_seconds`（`prefix` 为 `reviewer_a` 或 `reviewer_b`）。
   - 时间必须是 **UTC** 且以 `Z` 结尾，例如 `2026-10-28T09:12:03Z`；
   - `duration_seconds` 是该条**有效处理秒数**（非负），不含中断；
   - `evidence_uri` 填可审计的权威来源 URL；没有命中也要填实际检查过的来源页。

## 允许的权威来源（冻结）

- **保加利亚 UIC**（`identifier_namespace_status` 已含 `authoritative_ra000065_confirmed_by_registry`
  的记录）：Registry Agency 商业登记 `https://portal.registryagency.bg/CR/api/Deeds/{UIC}`；
  LEI 侧查 GLEIF `RA000065 + UIC`。注意：namespace 被确认**不等于**存在 LEI。
- **美国 UEI**（`usa_recipient`）：SAM.gov / USAspending recipient 档案确认 UEI；LEI 侧查 GLEIF
  `validatedAs` 或官方名称。
- **其他 TED buyer/winner**（`not_exposed_by_ted_search`）：先确认 TED 通知来源与国别登记机关，
  再在 GLEIF 查对应 namespace。TED 扁平字段无法单独证明配对。
- 统一的 GLEIF 入口：<https://www.gleif.org/en/lei-data/gleif-api>。名称相似**不能**替代权威 crosswalk。

## 不一致处理

A/B 都提交后，由负责人或脚本比对 `reviewer_a_outcome` 与 `reviewer_b_outcome`：

- 一致：`disagreement=false`，无需 adjudication；
- 不一致：`disagreement=true`，交 adjudicator 填 `adjudicator_id`、`final_outcome`、
  `final_resolution_method`、`final_evidence_uri`、`adjudicated_at_utc`、`adjudication_duration_seconds`。

## 完成后生成报告

```bash
.venv/bin/python scripts/report_identity_adjudication.py \
  docs/validation/ontology-v1/public-study/identity_adjudication_queue_v1.csv
```

报告给出 raw agreement、Cohen's kappa、分歧率、A/B 平均/中位/P90 耗时，以及每 100 个组织的
合计处理分钟数。关键身份字段的 **Cohen's kappa 目标为 `>= 0.80`**；低于门槛时先按
[实证研究方案](../../../运营本体V1实证研究方案.md)修订标注指南并重标，不要带着低一致率进入系统比较。

## 红线

- 不得把仍为 `pending` 的记录解释成 `no-match`；
- 不得用公开演练耗时外推真实业务工时；
- 不得由 AI 或实现者代填 A/B 任一方的结论——那样就不存在第二位独立评审，kappa 和人工成本都失去意义；
- 不得跨评审者共享候选或结论。
