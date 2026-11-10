# Knowledge 文档

本目录是 Knowledge 全部文档的入口。文档按读者任务分目录存放；判断一项能力是否已经实现时，以代码、[OpenAPI](openapi/knowledge.openapi.yaml) 和 [知识库架构 V1](roadmap/知识库架构V1.md) 为准，[知识库架构 V2](roadmap/知识库架构V2.md) 只描述尚未完成的目标。

## 从这里开始

第一次接触本项目，按以下顺序阅读：

1. [核心概念](architecture/核心概念.md)：项目中的领域对象、角色和术语，以及容易混淆的概念。
2. [系统架构](architecture/系统架构.md)：组件、与社区产品的分工、写路径、读路径和 Agent 运行流程。
3. [数据模型](architecture/数据模型.md)：数据库表、关系、约束和状态取值。

之后按要做的事选择下面的目录。

## 目录

| 目录 | 内容 | 什么时候看 |
| --- | --- | --- |
| [architecture/](#architecture架构与设计) | 当前架构、核心概念、数据模型和专题设计 | 理解系统如何组成、为什么这样设计 |
| [roadmap/](#roadmap现状与规划) | 已实现能力清单、目标架构、上线路线和成熟度评估 | 判断某项能力是否已实现、下一步做什么 |
| [integrations/](#integrations接入与集成) | 对外 API 接入，以及与 Warehouse 的集成 | 接入 Knowledge，或处理 Warehouse 相关问题 |
| [guides/](#guides使用与功能说明) | 控制台和功能的使用说明 | 完成一项具体操作 |
| [operations/](#operations部署与运维) | 部署、Worker、备份恢复和向量索引运维 | 发布、运行、扩容、恢复 |
| [openapi/](openapi/README.md) | OpenAPI 3.1 权威接口定义 | 查接口字段、状态和错误语义 |
| [validation/](#validation验证与评测) | 产品验收题集和研究数据 | 运行验收或评测 |
| [ontology/](#ontology运营本体) | 运营本体的调研、研究、验证和实现 | 了解运营本体的决策与边界 |
| [archive/](#archive历史归档) | 已不反映当前实现的历史文档 | 追溯历史背景 |

### architecture：架构与设计

- [核心概念](architecture/核心概念.md)：术语的集中定义处。
- [系统架构](architecture/系统架构.md)：组件、鉴权、数据流、端口落地状态和运行模式。
- [数据模型](architecture/数据模型.md)：表、关系、约束和跨表不变量。
- [社区产品关系与开发边界](architecture/社区产品关系与开发边界.md)：Knowledge 与 Chat、Warehouse、Router、Node、Wallet、Project、Agent 的关系。上游来源：[liuppx/books](https://github.com/liuppx/books/blob/main/yeying/%E7%A4%BE%E5%8C%BA%E4%BA%A7%E5%93%81%E5%85%B3%E7%B3%BB%E4%B8%8E%E5%BC%80%E5%8F%91%E8%BE%B9%E7%95%8C.md)。
- [混合检索与真实模型落地设计](architecture/混合检索与真实模型落地设计.md)：检索管线（关键词 + 向量 + RRF + rerank）、Router 接入、再嵌入迁移与评测门禁。
- [Agent 运行与上下文资产设计](architecture/Agent运行与上下文资产设计.md)：Agent Run、上下文引用、产物与运行清单。

### roadmap：现状与规划

- [知识库架构 V1](roadmap/知识库架构V1.md)：已实现能力清单与已知限制。
- [知识库架构 V2](roadmap/知识库架构V2.md)：目标架构，以 Warehouse 深度集成和 CSV/Excel 分析 Agent 为重点。
- [知识库能力规划与快速上线路线](roadmap/知识库能力规划与快速上线路线.md)：对标产品的能力借鉴与 v1 上线范围。
- [开源知识库产品对比与生产路线](roadmap/开源知识库产品对比与生产路线.md)：成熟度判断、开源产品横向比较和生产前门禁。

### integrations：接入与集成

- [API 接入文档](integrations/API接入文档.md)：外部服务的认证、推荐调用顺序和稳定性建议。
- [控制面 API 文档](integrations/控制面API文档.md)：控制台和治理场景的接口说明。
- [Warehouse 集成收敛方案](integrations/Warehouse集成收敛方案.md)：资产端口、Tool 凭证与集成阶段。
- [Warehouse 集成要求](integrations/Warehouse集成要求.md)：Knowledge 对 Warehouse 的契约要求、阻塞项和联调探针。
- [Warehouse 凭证使用说明](integrations/Warehouse凭证使用说明.md)：读写凭证的导入与使用。
- [Warehouse 鉴权与绑定重构说明](integrations/Warehouse鉴权与绑定重构说明.md)：凭证与绑定模型的重构背景。

### guides：使用与功能说明

- [控制台操作手册](guides/控制台操作手册.md)：控制台各工作台的操作说明。
- [CSV 与 Excel 分析 Agent 开发说明](guides/CSV与Excel分析Agent开发说明.md)：表格分析运行的接口、Worker 行为和限制。
- [Web 前端开发说明](../web/README.md)：React SPA 的开发、类型生成、测试与部署。

### operations：部署与运维

- [部署指南](operations/部署指南.md)：命令行启动、镜像、systemd、生产配置守卫和上线检查。
- [Worker 部署与扩缩容建议](operations/Worker部署与扩缩容建议.md)：Worker 运行与扩容。
- [备份与恢复手册](operations/备份与恢复手册.md)：PostgreSQL 备份、恢复、向量重建与演练清单。
- [向量索引运维手册](operations/向量索引运维手册.md)：单元级向量索引的上线、再索引、切换模型与故障降级。

### validation：验证与评测

- [产品验证知识库](validation/产品验证知识库.md)：用项目自身文档验证完整产品链路的题集（Q01–Q12）与验收标准；`scripts/product_acceptance.py` 和检索评测依赖它。
- [运营本体 V1 合成演练包](validation/ontology-v1/README.md)：对象身份、时态、冲突、Release 与 Evidence 失效的评分流程和研究数据。

### ontology：运营本体

运营本体当前判定为 `Don't build yet`；受控原型和生产身份切片已实现但默认关闭，不代表产品价值已验证。建议按以下顺序阅读：

1. [本体论与运营知识平台调研](ontology/本体论与运营知识平台调研.md)：DomainObject、Relation、Assertion 与可借鉴的开源项目。
2. [运营本体成功产品借鉴分析](ontology/运营本体成功产品借鉴分析.md)：Palantir、Wikibase、Reltio、Stardog、Neo4j 的成功机制与借鉴边界。
3. [运营本体 V1 构建风险评审](ontology/运营本体V1构建风险评审.md)：进入实现前的决策问题、证据边界与构建门槛。
4. [运营本体 V1 实证研究方案](ontology/运营本体V1实证研究方案.md)：预注册假设、指标和硬门槛。
5. [运营本体 V1 公开数据代理验证](ontology/运营本体V1公开数据代理验证.md)：公开数据 pilot 与结论。
6. [运营本体 V1 最终建设决策](ontology/运营本体V1最终建设决策.md)：当前决策、证据和升级门槛。
7. [运营本体 V1 受控身份原型](ontology/运营本体V1受控原型.md)：非生产、内存态原型。
8. [运营本体 V1 生产身份与证据切片](ontology/运营本体V1生产身份切片.md)：持久化 API、owner-only 授权和部署边界。

### archive：历史归档

以下文档描述的接口或计划已被替代，仅供追溯背景，不能作为当前实现依据：

- [Bot 与 Chat 知识库重构 PRD](archive/Bot与Chat知识库重构PRD.md)
- [模块化复用与前端工程化规划](archive/模块化复用与前端工程化规划.md)
- [Warehouse 鉴权收口待办](archive/Warehouse鉴权收口待办.md)

## 维护约定

- 新文档放进与其读者任务对应的目录，并在本页登记。
- 术语在[核心概念](architecture/核心概念.md)中定义，其他文档链接回去，不复制定义。
- 能力实现后迁入 [V1](roadmap/知识库架构V1.md)，未实现的目标留在 [V2](roadmap/知识库架构V2.md)；不再反映当前实现的文档移入 `archive/` 并注明原因。
- 移动或重命名文档时，同时更新仓库内链接、代码中引用的路径，以及其他社区仓库指向本仓库的链接。
