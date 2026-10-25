# 运营本体 V1 公开数据代理验证

本目录不提交第三方原始合同或公共 API 的完整响应。公开数据仅用于验证研究方法、数据可得性和技术机制，不能替代真实用户需求、真实权限边界或业务维护成本证据。

运行：

```bash
python scripts/validate_public_ontology_data.py \
  --cache-dir /tmp/knowledge-public-validation \
  --output /tmp/ontology-public-validation.json
```

脚本会：

1. 按固定 Git commit 下载 ContractNLI 和 CUAD，并校验 SHA-256；
2. 验证所有人工 Evidence span/answer offset 可以回放到原文；
3. 从 USAspending 读取固定 Award 及其修改交易，验证交易金额能重算当前 Award；
4. 从 TED 读取固定修改通知及前一通知，验证买方、品类、标题和版本关系；
5. 从 GLEIF 读取固定 LEI，验证当前法定名称、历史名称和登记机关 crosswalk；
6. 输出机器可读 JSON，并在任一客观检查失败时返回非零退出码。

完整解释、局限和下一阶段门槛见[公开数据代理验证报告](../../../运营本体V1公开数据代理验证.md)。

## C3 自然语言规划挑战集

[`planner_challenge_v1.json`](planner_challenge_v1.json) 在实现 planner 基线之前冻结，用于检查自然语言问题能否被解析为 C3 的 operation 和稳定对象参数。

冻结文件 SHA-256：`b87251e223472c1f69fd15fa9128c437a700338ad5f0bf5274d8f0ea09032cc1`。

数据集包含 42 个案例：

- 12 个 development 案例；
- 30 个 test 案例；
- 31 个可回答案例，覆盖 C3 的 6 个 operation；
- 11 个必须拒答的不存在 ID、近似 ID、一对多实体和超出工具能力案例。

在任何 planner 实现前冻结以下通过标准：

| 指标 | 门槛 |
| --- | ---: |
| 可回答案例 operation accuracy | `>= 95%` |
| 可回答案例 exact parameter match | `>= 90%` |
| 每个数据来源的 exact parameter match | `>= 80%` |
| 不可回答案例 abstention | `100%` |
| false merge | `0` |
| planner + C3 端到端 exact answer | `>= 90%` |
| 端到端 Evidence traceability | `100%` |

评测时只能向 planner 传入 `query`；不得在运行时读取 `expected_operation`、`expected_params` 或 `expected_resolution`，不得按 case ID 写特例。

这是“先冻结、后实现”的 held-out challenge set，但不是真正的外部隐藏集：题目使用固定公开记录人工编写，并且已提交到仓库。正式结论仍需要由未参与实现的评测者保管隐藏问题。

## GLEIF 实体解析 pair

[`entity_resolution_pairs_v1.json`](entity_resolution_pairs_v1.json) 使用 GLEIF 官方 LEI 记录冻结 22 对组织名称：

冻结文件 SHA-256：`0d1f07953ffa1474365e4ec3365512908534cf02a64781a617f6195dfa9d7d9d`。

- 7 个 `same` 正例：当前法定名称与同一 LEI 记录中的 `PREVIOUS_LEGAL_NAME`；
- 15 个 `different` 困难负例：全文搜索得到的相似名称，但官方 LEI 不同。

金标不依赖本项目的主观判断：同一 LEI 的官方历史名称标为 `same`，不同 LEI 标为 `different`。后者即使属于关联公司、退休计划或信托，也是不得静默合并的不同法律实体。

负例是为压力测试主动选取的 hard negative，不得用它们估计真实世界的同名或近似名称流行率。后续实验将比较字符串相似度自动合并与稳定 LEI/crosswalk 解析，并报告 precision、recall、false merge 和阈值敏感性。

## TED XML 组织提取

[`ted_xml_organization_extract_v1.json`](ted_xml_organization_extract_v1.json) 冻结了 TED Search API 扁平字段无法证明配对的一份通知。提取文件 SHA-256：

```text
9616c1381435d1f2032336208756112c99a6885a581cb7445556fa2ae03aacba
```

官方源 XML：

- notice ID：`9c62249e-6449-490f-93f6-69f79694e225`；
- publication number：`186732-2025`；
- URL：<https://ted.europa.eu/en/notice/186732-2025/xml>；
- SHA-256：`f65386528d46a20f30ca6da69f2df8afcad09d077da0fc2634761932cd0f3f5a`。

冻结文件只保存目标组织的规范化派生字段和 XML locator，不提交第三方完整 XML。评测在本地 XML cache 可用时会重新解析官方文件并与冻结提取逐字段比较；否则仍校验冻结提取本身的 hash，并明确报告源 XML 未在本轮重新读取。

XML 使用显式 `TenderingParty/Tenderer → Organization` 引用恢复 6 个 winner 的 `PartyName + CompanyID + Country`，使当前样本的 TED winner 来源内配对达到 13/13。它没有声明 `CompanyID` 的 `schemeID` 或 `schemeName`；`BGR` 又对应 4 个 GLEIF registration authority，因此该提取不能作为 LEI 自动映射或跨来源实体自动合并的依据。
