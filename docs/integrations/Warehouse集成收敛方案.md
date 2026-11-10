# Warehouse 集成收敛方案

状态：阶段一完成；阶段二 Tool credential 绑定与资产运行时接线已实现并通过自动化验证
日期：2026-11-08

## 决策

Knowledge 通过稳定的资产端口访问文件；Warehouse adapter 封装上游协议和授权凭证。Knowledge 拥有 Source、SourceAsset、Evidence、AgentRun、Artifact 元数据及 provenance；Warehouse 拥有对象内容、对象版本、资产权限、配额、checksum 和存储审计。

Knowledge 的用户 JWT / Service Principal 决定调用方可使用哪些 Knowledge 业务资源。Warehouse 最终裁决对象权限。Chat 不接触 Warehouse 凭证，Worker 只应获得执行当前 Run 所需的最小、短期资产授权。

## 目标端口

```text
SourceConnectorPort
  list_assets(root) -> SourceAssetRef[]
  read_asset(asset_ref) -> bytes/stream

AssetStorePort
  read(access_context, asset_ref) -> bytes/stream
  write(access_context, target, content, options) -> AssetReference
  stat(access_context, asset_ref) -> AssetReference
```

来源发现与资产持久化是两个端口。Warehouse 可以同时适配二者；local file、GitHub 等 connector 不需要实现 Warehouse 的对象写入。业务服务不导入 S3/WebDAV 客户端，也不处理供应商原始错误体。

`AssetReference` 的核心字段为 `provider`、`object_id`、`version_id`、`etag`、`sha256`、`size`、`content_type` 和 `modified_at`。路径仅用于定位；Run 输入必须尽可能冻结到不可变版本。未支持版本读取时，ETag/checksum 只能作为过渡校验，不能宣称具有不可变快照语义。

资产端口返回稳定错误码：`not_found`、`permission_denied`、`conflict`、`version_conflict`、`quota_or_rate_limited`、`too_large`、`integrity_error`、`unavailable`、`invalid_request` 和 `upstream_error`。重试策略由 Knowledge 按错误码决定。

## 当前兼容实现

阶段一已引入 `AssetReference`、`AssetAccessContext`、`AssetStorePort`、`AssetStoreError` 和 `LegacyWarehouseAssetStore`。兼容 adapter 仍委托现有 S3/WebDAV `WarehouseGateway`；它没有提供不可变版本、Range、低成本 stat 或大对象上传会话，且不支持条件写入。

Knowledge 的 Agent Run Artifact、manifest、表格输入读取、Evidence 构建、文档导入和分析产物下载已通过资产端口执行。访问凭证仍由 `WarehouseAccessService` 按现有模式解析；现阶段上下文携带的是兼容凭证，后续替换为 Tool credential 或委托授权。

浏览和目录枚举仍由现有来源/资产管理路径直接调用 Warehouse gateway。Warehouse source connector 尚未完整实现为通用 `SourceConnectorPort` adapter。

已核对 `/Users/liuxin2/Workspace/opensource/warehouse/docs/应用集成/资产Tool契约.md` 与其 OpenAPI：HTTP Tool 调用入口为 `POST /api/v1/public/tools/warehouse/call`，凭证管理由用户登录 JWT 完成，资产调用使用 Bearer JWT 或短期 scoped Tool credential。当前 `warehouse.object.read` 内容上限为 5 MiB，`warehouse.object.put` 写入上限也是 5 MiB；Tool 还没有对外提供大对象上传会话。因此它能先承接 metadata、小对象读写和 manifest，但不能直接替代 Knowledge 当前更大表格输入所依赖的存储读取能力。Tool credential 的用户归属与 Knowledge 钱包身份映射也必须在迁移 AK/SK 前明确。

## 迁移阶段

### 阶段一：端口与兼容 adapter

- 建立统一资产引用、访问上下文和稳定错误码。
- 把 Run、Evidence 和导入服务的二进制读写移到资产端口。
- 保持现有数据模型和用户流程，验证行为兼容。

### 阶段二：Warehouse Tool adapter 与用户凭证接线（已实现，待验证）

- 已根据 Warehouse 已发布的 HTTP Tool schema 实现 metadata、list、read、put 和条件写入，代码位于 `knowledge/adapters/warehouse_tool.py`。
- HTTP 请求使用 `POST /api/v1/public/tools/warehouse/call`，Tool 名分别为 `warehouse.object.stat/list/read/put`；adapter 不直接调用底层 assets API。
- 由 Warehouse 校验用户/服务身份、路径、动作和有效期；Knowledge 不在 Tool adapter 中复制权限判定。
- adapter 已覆盖 metadata、只读和不超过 5 MiB 的小对象写入；验证 `truncated`、SHA-256 并映射稳定错误码。保留旧 adapter 处理现有大文件工作负载，直至 Warehouse 提供受控的大对象读写能力。
- 身份核对结论：Knowledge 登录流程与 Warehouse 前端均使用 `@yeying-community/web3-bs` 的 Wallet Identity 登录。两个服务签发各自的 JWT，因此 Knowledge JWT 不能直接用于 Warehouse API；前端用同一钱包身份登录 Warehouse，并把 Warehouse JWT 临时交给 Knowledge 后端。后端先核对 `/user/info` 返回的钱包地址，再创建/轮换凭证。
- Warehouse 页已提供连接/续期/撤销流程。服务端只为当前 Knowledge 用户创建 `knowledge-agent-runs` 凭证，限制 `asset:read`、`asset:write` 和当前 app root，30 天过期；一次性 secret 加密存入独立表，不返回给浏览器、不落日志。断开会向 Warehouse 撤销并清除本地密文。
- 已处理部分失败边界：Warehouse 已先行撤销凭证时，Knowledge 仍会清除本地密文；远端创建/轮换成功而 Knowledge 数据库提交失败时，会尽力撤销远端凭证，并尝试清理本地旧密文。
- Agent Run、Evidence、导入和分析产物通过自适应 adapter 使用已绑定的 Tool credential。Tool 限制内优先走 HTTP Tool；超过 5 MiB 的读写仅回退到该钱包已解析的旧 AK/SK 凭证，以维持既有大文件能力。Warehouse 仍对 Tool 调用执行最终 scope/path 检查。
- 旧 adapter 接到 `if_match` 会明确报 `invalid_request`，不假装提供条件写入；其底层 S3/WebDAV PUT 仍保持原有覆盖语义。
- 自动化验证覆盖了 Tool 凭证创建、钱包不匹配拒绝、撤销和数据库写入失败补偿、Tool 小对象适配、旧存储兼容与 OpenAPI 快照。测试通过不替代部署环境中的钱包登录和真实 Warehouse 端到端探针。

### 阶段三：来源接入与 Run 输入冻结

- 让 Warehouse 来源实现 `SourceConnectorPort`，把浏览、扫描与内容读取统一到来源端口。
- 引入稳定 `AssetReference` 序列化，Run 创建时冻结版本、ETag、checksum 和大小。
- 输入读取使用条件版本或 ETag；对象变化时返回明确冲突。

### 阶段四：凭证退出与大对象能力

- 迁移既有 AK/SK 用户到短时、可撤销、限路径/动作的 Tool credential 或 Run 委托授权。
- Tool schema 支持 Range/stream、原子分片上传、幂等键、checksum 校验、请求关联及稳定错误码后，再开放大对象分析。
- 停用旧的 WebDAV/S3 直连和长期 AK/SK 保存路径。

## 验收门槛

1. 业务服务不直接调用 `WarehouseGateway` 的内容读写方法。
2. 所有上游失败被映射到稳定错误码，且不会把凭证或敏感响应写入日志。
3. Run 的输入引用可追溯；版本能力缺失时，API 与 manifest 明确呈现过渡语义。
4. Warehouse Tool 权限由 Warehouse 最终校验，Worker 不持有长期跨 Run 凭证。
5. 条件读取、Range、原子上传和幂等语义通过真实 Warehouse 契约探针后，才启用对应生产能力。
6. DB 与对象写入部分失败可观测、可重试、可对账；Warehouse manifest 始终是 Knowledge Run 状态的投影。
