# Knowledge 文档

本目录采用“当前事实、未来架构、操作指南、接口契约、历史背景”分层。判断功能是否已经实现时，优先查看 V1、OpenAPI 和代码；V2 只描述尚未完成的目标。

## 架构基线

- [知识库架构 V1](知识库架构V1.md)：当前已经实现的知识库架构和能力边界。
- [知识库架构 V2](知识库架构V2.md)：尚未实现或尚未完整实现的目标架构。
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
- [Warehouse 凭证使用说明](Warehouse凭证使用说明.md)
- [Warehouse 鉴权与绑定重构说明](Warehouse鉴权与绑定重构说明.md)
- [Worker 部署与扩缩容建议](Worker部署与扩缩容建议.md)

## 产品与验证

- [产品验证知识库](产品验证知识库.md)
- [Bot 与 Chat 知识库重构 PRD](Bot与Chat知识库重构PRD.md)
- [Agent 运行与上下文资产设计](Agent运行与上下文资产设计.md)

## 历史与待办

- [Warehouse 鉴权收口待办](Warehouse鉴权收口待办.md)

历史或待办文档不能覆盖 V1、OpenAPI 和当前代码事实。完成的目标应迁入 V1；尚未实现的架构目标应迁入 V2。
