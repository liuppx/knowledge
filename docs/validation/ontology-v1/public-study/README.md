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

## 保加利亚商业登记提取

[`bulgarian_commercial_register_extract_v1.json`](bulgarian_commercial_register_extract_v1.json) 使用 Registry Agency 的公开 Commercial Register API 对上述 7 个 CompanyID 做权威 namespace 验证。提取文件 SHA-256：

```text
48bfcd98d596b32392757480a67b9f09dd5a5499f63935886cf48658677927fd
```

GLEIF `RA000065` 的官方机构是 Registry Agency (Ministry of Justice)，其网站重定向到 `portal.registryagency.bg`。固定记录调用 `/CR/api/Deeds/{UIC}`，7/7 的返回 UIC 与 TED CompanyID 精确一致，法定全名规范化后也与 TED Organization 名称一致。因此，这 7 个 ID 可以确认属于 `RA000065` Commercial Register namespace。

冻结提取只保留 UIC、法定名称、法律形式原码、deed status 原码、官方记录 URL 和 authority ID；完整响应可能含个人或联系信息，不提交仓库。状态和法律形式代码只保留原值，不在本研究中主观解释。

确认 namespace 后，GLEIF 对 7 个 `RA000065 + UIC` 仍未返回权威 LEI 记录。这是“未观察到 LEI 映射”，不能表述成这些组织永久不存在 LEI，也不能用唯一名称候选替代权威 crosswalk。

评测还会枚举 GLEIF API 当前 `entity.legalAddress.country=BG` 的完整分页结果，而不是只依赖 7 次精确 ID 查询。最近快照共 6,222 条记录、32 页；7 个 UIC 的 `validatedAs` 命中和规范化法定名称/别名命中均为 0。该扫描仍不构成独立 Golden Copy 交付证据：GLEIF [官方 API 说明](https://www.gleif.org/en/lei-data/gleif-api)明确 API 数据基于 Golden Copy，且扫描摘要会记录 `publishDate` 与 hash，供快照漂移审查。为补独立交付通道，本研究另对官方 Concatenated File 做了全量扫描，详见下节。

### GLEIF Concatenated File 独立复核

[`bulgarian_gleif_concatenated_scan_v1.json`](bulgarian_gleif_concatenated_scan_v1.json) 是对 GLEIF 官方 Concatenated LEI-CDF 3.1 交付的最小扫描摘要；原始 ZIP 不提交仓库。下载地址：<https://leidata.gleif.org/api/v1/concatenated-files/lei2/get/42569/zip>。

- ZIP SHA-256：`23c03705b3f93dd9869af2c9366f1bc191640ac1fd0759e615ff768fc2d09af6`；文件成员：`20261025-gleif-concatenated-file-lei2.xml`；
- XML `ContentDate`：`2026-10-25T09:00:01Z`；头部 `RecordCount` 与实际流式扫描均为 `3,473,152`；
- `LegalAddress/Country=BG`：`6,222`；`RegistrationAuthorityID=RA000065`：`5,698`；
- 7 个 UIC 的 `RegistrationAuthorityEntityID` 命中为 `0`，7 个登记名称在 `LegalName` 或 `OtherEntityName` 中的规范化命中也为 `0`；
- 扫描摘要 SHA-256：`e87800e89cfbbb5d4bd85930cf4254bf3775436d14009fafa5f3c9e4fc6dc9dc`；摘要文件 SHA-256：`48e0745e05bbb8e55c0bac1b3df393dd94fb2d8ab9e163b95b95e43c5f66bf39`。

可复现命令（需要先下载对应 ZIP）：

```bash
python scripts/validate_gleif_bulgarian_concat.py \
  --archive /path/to/20261025-gleif-concatenated-file-lei2.zip \
  --output /tmp/bulgarian_gleif_concatenated_scan.json
```

这完成了“当前日期官方 Concatenated 交付中未观察到目标 LEI”的复核，但不证明组织永久没有 LEI；后续仍需记录人工裁决成本，并在数据更新后重新运行漂移门禁。

## 身份 crosswalk 工具辅助参考件（非独立评审）

[`identity_crosswalk_reference_v1.json`](identity_crosswalk_reference_v1.json) 由
`scripts/research_identity_crosswalk_probe.py` 对 29 条队列做**单次**公开 GLEIF API 查询生成，
用于提供一个可审计的参考下界。它**不是**两名评审者的独立裁决，**不得**写入队列的 `reviewer_*` 列，
也不得外推真实业务工时。

复现：

```bash
.venv/bin/python scripts/research_identity_crosswalk_probe.py \
  docs/validation/ontology-v1/public-study/identity_adjudication_queue_v1.csv \
  docs/validation/ontology-v1/public-study/identity_crosswalk_reference_v1.json
```

最近一次运行的分类（0 条 authoritative、4 条 candidate、25 条 no-match）要点：

- 对 7 个保加利亚 `RA000065 + UIC`，GLEIF 的 `registeredAs` 过滤均无命中，与官方 Concatenated 全量扫描一致；
- 6 个美国 UEI 中只有 3 个按名称得到单一 candidate（Hamilton Sundstrand、Vertex Aerospace、Boeing），
  且 **UEI 不是 GLEIF 的键**，名称命中不能等同权威 crosswalk；
- Boeing 的名称查询同时返回公司本体与两个关联 Master Trust，正是不得静默合并的 false-merge 陷阱；
- 关键实现注意：GLEIF 的 `filter[entity.legalName]` **不是精确匹配**，无命中时会返回整个集合（total 可达数万），
  因此脚本按 `meta.pagination.total` 而非页内记录数判定，避免把“未过滤”误判成“多候选”。

结论：即便对知名美国主承包商，公开数据也得不到 authoritative 的 UEI→LEI crosswalk，只有需裁决的名称候选。
这支持“用稳定 ID/权威 crosswalk 而非名称阈值自动合并”，但真实一致率与人工成本仍须由两名评审者独立产出。
