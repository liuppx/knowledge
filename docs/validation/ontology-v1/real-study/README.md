# 运营本体 V1 真实研究模板

本目录只保存空模板和字段说明，不保存真实合同、客户、员工、商业金额或其他敏感数据。

使用顺序：

1. 在受控环境中复制模板；
2. 完成原始数据授权和脱敏；
3. 填写 `data_inventory.csv`；
4. 冻结 `competency_questions.csv` 的 development/test split；
5. 两名标注者分别填写对象身份和断言金标；
6. 使用 `adjudication_log.csv` 记录分歧；
7. 运行各实验组并写入 `experiment_results.csv`；
8. 根据[实证研究方案](../../../运营本体V1实证研究方案.md)计算指标和作出决策。

真实数据文件和填充后的敏感模板不得提交到公开仓库。

## 公开身份裁决演练

[`../public-study/identity_adjudication_queue_v1.csv`](../public-study/identity_adjudication_queue_v1.csv) 是由 29 个公开采购来源组织组成的待裁决队列，不是真实用户数据或已完成人工标签。所有 29 项的 `status` 初始化为 `pending`；候选 LEI 和系统映射类别不放入队列，减少评审锚定。

两名评审者应独立判断来源标识能否由权威证据映射到 LEI，并分别使用以下 outcome：

- `authoritative_crosswalk_confirmed`：权威来源同时证明来源 ID、namespace 和 LEI；
- `candidate_requires_adjudication`：找到候选，但缺少完整权威 crosswalk；
- `no_crosswalk_found_in_checked_sources`：记录已按冻结来源清单和时间范围检查，仍无 crosswalk；
- `ambiguous`：多个可能实体或 crosswalk 相互冲突；
- `insufficient_evidence`：无法完成必要查询或证据不可访问。

每项填写 reviewer pseudonymous ID、UTC 开始/提交时间、有效处理秒数、决定方法和可审计来源 URI。评审者之间不共享候选或结论；不一致项交由 adjudicator 并记录最终证据与处理秒数。报告原始一致率、Cohen's kappa、分歧率、平均/中位/P90 处理时间，并换算每 100 个组织的人工处理时长。不得把 `pending` 解释成 no-match，也不得根据公开演练结果外推真实业务工时。

完成或部分填写队列后，用仓库虚拟环境生成报告：

```bash
.venv/bin/python scripts/report_identity_adjudication.py \
  docs/validation/ontology-v1/public-study/identity_adjudication_queue_v1.csv

.venv/bin/python scripts/report_identity_adjudication.py \
  docs/validation/ontology-v1/public-study/identity_adjudication_queue_v1.csv \
  --format json --output /tmp/identity-adjudication-report.json
```

报告仅把字段齐全、结果属于上述枚举、UTC 时间合法且耗时为非负数的记录纳入统计。部分记录列入 data-quality issues 并使命令返回非零；仍为 `pending` 且没有填写评审字段的记录只计入待办，不作 no-match 推断。Cohen's kappa 按名义类别计算，分母只使用两名评审均完成的配对记录。
