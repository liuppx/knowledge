# Knowledge 文档

本目录采用“当前事实、未来架构、操作指南、接口契约、历史背景”分层。判断功能是否已经实现时，优先查看 V1、OpenAPI 和代码；V2 只描述尚未完成的目标。

## 架构基线

- [知识库架构 V1](知识库架构V1.md)：当前已经实现的知识库架构和能力边界。
- [知识库架构 V2](知识库架构V2.md)：以 Warehouse 深度集成和面向 Chat 的 CSV/Excel Agent 分析为首要研发重点，并记录后续治理目标。
- [社区产品关系与开发边界](社区产品关系与开发边界.md)：Knowledge 与 Chat、Warehouse、Router、Node、Wallet、Project、Agent 的关系。

社区关系文档的上游来源：

- [liuppx/books - 社区产品关系与开发边界.md](https://github.com/liuppx/books/blob/main/yeying/%E7%A4%BE%E5%8C%BA%E4%BA%A7%E5%93%81%E5%85%B3%E7%B3%BB%E4%B8%8E%E5%BC%80%E5%8F%91%E8%BE%B9%E7%95%8C.md)

## 接口契约

- [knowledge.openapi.yaml](openapi/knowledge.openapi.yaml)：OpenAPI 3.1 权威接口定义。
- [OpenAPI 说明](openapi/README.md)：生成、更新和本地查看方式。
- [API 接入文档](API接入文档.md)：认证、推荐调用顺序和稳定性建议。
- [控制面 API 文档](控制面API文档.md)：控制台和治理场景说明。

## 使用与运维

- [控制台操作手册](控制台操作手册.md)
- [部署指南](部署指南.md)：命令行启动、systemd、生产配置守卫和上线检查。
- [备份与恢复手册](备份与恢复手册.md)：PostgreSQL 备份 / 恢复 / 向量重建与演练清单。
- [Warehouse 凭证使用说明](Warehouse凭证使用说明.md)
- [Warehouse 集成要求](Warehouse集成要求.md)：Knowledge V2 对 Warehouse 的契约、阻塞项和联调探针。
- [Warehouse 鉴权与绑定重构说明](Warehouse鉴权与绑定重构说明.md)
- [Worker 部署与扩缩容建议](Worker部署与扩缩容建议.md)

## 产品与验证

- [开源知识库产品对比与生产路线](开源知识库产品对比与生产路线.md)：当前成熟度、开源产品横向比较和生产前门禁。
- [本体论与运营知识平台调研](本体论与运营知识平台调研.md)：DomainObject、Relation、Assertion、Palantir Ontology 及可借鉴的开源项目。
- [运营本体成功产品借鉴分析](运营本体成功产品借鉴分析.md)：对 Palantir、Wikibase、Reltio、Stardog 和 Neo4j 的成功机制、定位、采购形态与 Knowledge 借鉴边界进行结构化比较。
- [运营本体 V1 构建风险评审](运营本体V1构建风险评审.md)：在进入对象、关系和断言实现前，验证真实决策问题、证据边界与构建门槛。
- [运营本体 V1 实证研究方案](运营本体V1实证研究方案.md)：使用真实原始数据、双人金标、基线/对照/消融、统计和权限测试决定是否进入 Build small。
- [运营本体 V1 公开数据代理验证](运营本体V1公开数据代理验证.md)：用公开合同金标和官方采购、法人数据运行可复现 pilot；C3 与 E 持平，TED XML 与 Registry Agency 可恢复来源内配对并确认 `RA000065`；GLEIF API 全量 BG 扫描及官方 Concatenated File 均未发现 7 个目标 UIC/名称，当前判定为 `Don't build yet`。
- [运营本体 V1 合成演练包](validation/ontology-v1/README.md)：用合同、产品和组织演练对象身份、时态、冲突、Release 与 Evidence 失效评分流程。
- [知识库能力规划与快速上线路线](知识库能力规划与快速上线路线.md)：对标 Obsidian/PandaWiki/WeKnora 的能力借鉴与 v1 快速上线范围。
- [混合检索与真实模型落地设计](混合检索与真实模型落地设计.md)：v1.0 检索管线（关键词+向量+RRF+rerank）、Router 接入、再嵌入迁移与评测门禁。
- [向量索引运维手册](向量索引运维手册.md)：单元级向量索引上线、再索引、切模型维度与故障降级（Weaviate + Postgres）。
- [Web 前端开发说明](../web/README.md)：React SPA 工作台的开发、类型生成（OpenAPI → TS）、测试与部署。
- [部署指南](部署指南.md)：镜像、docker compose、生产配置守卫、上线检查。
- [备份与恢复手册](备份与恢复手册.md)：PostgreSQL 为真相源的备份 / 恢复 / 向量重建与演练清单。
- [产品验证知识库](产品验证知识库.md)
- [Bot 与 Chat 知识库重构 PRD](Bot与Chat知识库重构PRD.md)
- [Agent 运行与上下文资产设计](Agent运行与上下文资产设计.md)
- [CSV 与 Excel 分析 Agent 开发说明](CSV与Excel分析Agent开发说明.md)：M1 当前接口、Worker 行为、限制和下一批实现范围。

## 历史与待办

- [Warehouse 鉴权收口待办](Warehouse鉴权收口待办.md)

历史或待办文档不能覆盖 V1、OpenAPI 和当前代码事实。完成的目标应迁入 V1；尚未实现的架构目标应迁入 V2。
