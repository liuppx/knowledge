# Agent Run 与 Context Asset 设计方案

状态：验证阶段  
版本：v1  
日期：2026-08-01

## 1. 决策

Agent Run、Context Manifest 和 Artifact Provenance 归属 `knowledge`，不作为 `warehouse` 的业务领域模型。

三者职责如下：

```text
chat       -> 任务入口、模型与工具执行、用户交互
knowledge  -> run、context、evidence、artifact metadata、provenance、服务身份
warehouse  -> 文件/对象、路径权限、凭证、配额、checksum、WebDAV/S3、复制
```

`warehouse` 不理解“研究任务”“上下文角色”“最终报告”等业务语义。`knowledge` 保存这些语义，并把大文件和可移植 manifest 写入自己的 Warehouse app 空间。

## 2. 验证目标

第一阶段用社区 Chat 的“多文件研究与报告生成”验证：

1. Chat 能使用现有 `ServicePrincipal` 创建一次 run。
2. run 能记录用户输入、知识检索结果、工具输出和最终 artifact。
3. 能回答一个 artifact 由哪个服务、哪次 run、基于哪些来源生成。
4. artifact 文件可通过 Warehouse WebDAV/S3 访问。
5. Knowledge 数据库记录和 Warehouse manifest 可以相互校验。
6. 撤销 ServicePrincipal 后不能创建或修改 run，但历史记录保留。

## 3. 现有能力复用

直接复用：

- `ServicePrincipal`：调用方身份。
- `ServiceGrant`：调用方可读取的 KB 和 release。
- `RetrievalLog`：一次知识检索的审计记录。
- `SourceAsset / EvidenceUnit`：来源与证据。
- `KnowledgeItemRevision / KBRelease`：正式知识版本。
- `WarehouseAccessCredential`：Knowledge 访问 Warehouse 的后端凭证。
- `WarehouseGateway`：文件上传、读取、列举和目录创建。
- `ImportTask` worker 模式：异步任务实现参考，但不复用其数据模型。

不直接复用：

- `ImportTask` 不能代表 Agent Run。前者是 Knowledge 内部索引任务，后者是外部智能体工作记录。
- `ServiceGrant` 不增加 `artifact:write` 等混合权限。它继续只负责知识库发布内容的读取授权。
- `RetrievalLog` 不升级成 run。一个 run 可以关联多条 retrieval log。

## 4. 核心模型

### 4.1 AgentRun

| 字段 | 说明 |
| --- | --- |
| `id` | Knowledge 生成的稳定字符串 ID，格式 `run_<ULID>` |
| `owner_wallet_address` | 数据所有者 |
| `service_principal_id` | 创建 run 的服务身份 |
| `session_id` | Chat 会话或上游会话标识 |
| `external_id` | 上游幂等标识，如 `<sessionId>:<messageId>` |
| `run_type` | 第一阶段固定使用 `research` |
| `status` | `running/completed/failed/cancelled` |
| `warehouse_run_path` | Warehouse 中 run 根路径 |
| `input_manifest_json` | 输入引用摘要 |
| `context_manifest_json` | 上下文引用摘要 |
| `metadata_json` | 模型、技能、客户端等有限元数据 |
| `error_summary` | 脱敏后的失败摘要 |
| `started_at` | 开始时间 |
| `finished_at` | 终态时间 |
| `created_at/updated_at` | 审计时间 |

约束：

- `(service_principal_id, external_id)` 在 `external_id` 非空时唯一，用于重试幂等。
- `owner_wallet_address` 从 principal 派生，调用方不能指定。
- `service_principal_id` 创建后不可变。
- 终态 run 在 v1 中不可恢复为 `running`。
- 历史 run 不因 principal 或 grant 撤销而删除。

### 4.2 AgentRunArtifact

| 字段 | 说明 |
| --- | --- |
| `id` | 数据库 ID |
| `run_id` | 所属 run |
| `artifact_key` | run 内稳定业务 key |
| `artifact_type` | `report/code/image/data/log/other` |
| `role` | 调用方定义的语义角色 |
| `status` | `draft/final` |
| `warehouse_path` | Warehouse 逻辑路径 |
| `file_name` | 展示名称 |
| `content_type` | MIME type |
| `size` | 字节数 |
| `sha256` | 内容完整性 |
| `generated_by_json` | tool/model/step 等生成信息 |
| `metadata_json` | 有限扩展字段 |
| `created_at/updated_at` | 审计时间 |

约束：

- `(run_id, artifact_key)` 唯一。
- `warehouse_path` 必须位于该 run 的 `artifacts/` 下。
- `final` artifact 在 run 完成后不可覆盖；修订需要新 artifact key 或新 run。
- 二进制内容不进入 Knowledge 数据库。

### 4.3 AgentRunContextReference

第一阶段可以先放在 `context_manifest_json`，验证后再决定是否拆表。每条引用至少包含：

```json
{
  "kind": "warehouse_asset|evidence|knowledge_item|retrieval_log|tool_output",
  "role": "source|summary|citation|tool_result",
  "referenceId": "...",
  "warehousePath": "/apps/knowledge.yeying.pub/...",
  "sha256": "...",
  "recordedAt": "2026-08-01T08:00:00Z"
}
```

关系型外键适用于 Knowledge 内部对象；Warehouse 路径和外部 tool output 使用显式引用。不能把所有类型强行塞进一个数据库外键。

## 5. Warehouse 目录

第一阶段继续遵守 Knowledge 当前 app-only 边界：

```text
/apps/knowledge.yeying.pub/
  uploads/
  library/
  exports/
  runs/
    <run-id>/
      manifest.json
      context/
      artifacts/
      logs/
      tmp/
```

规则：

- Knowledge 使用 owner 已配置的 `read_write` Warehouse 凭证写入。
- run 路径由 Knowledge 服务端生成，不接受调用方绝对路径。
- `manifest.json` 由 Knowledge 写入并维护。
- `tmp/` 不进入最终 manifest，可设置清理策略。
- 用户原始上传仍在 `uploads/`，run input 通过路径和 checksum 引用，不重复复制大文件。
- chunk 和 embedding 继续只保存在 Knowledge/向量后端，不写入 Warehouse。

验证通过后，若 Warehouse 提供 workload/service identity，再评估迁移到 `/services/knowledge`。当前不依赖该能力。

## 6. Manifest

Warehouse 中的 `manifest.json` 是数据库 run 的可移植投影，不是主事务数据库。

```json
{
  "schema": "knowledge.agent-run.v1",
  "runId": "run_...",
  "runType": "research",
  "status": "completed",
  "servicePrincipal": {
    "id": 12,
    "serviceId": "community-chat"
  },
  "sessionId": "chat-session-1",
  "externalId": "chat-session-1:message-42",
  "startedAt": "2026-08-01T08:00:00Z",
  "finishedAt": "2026-08-01T08:05:00Z",
  "inputs": [],
  "context": [],
  "artifacts": [],
  "metadata": {
    "skill": "research"
  }
}
```

写入策略：

1. 数据库事务先更新 run/artifact。
2. 事务提交后生成 manifest 投影并写入 Warehouse。
3. 写入失败时 run 标记 `manifest_sync_status=failed`，进入重试队列。
4. API 返回数据库事实，并明确 manifest 同步状态，不能把双写伪装成原子事务。
5. Worker 可根据数据库重建 manifest。

因此 AgentRun 需要增加：

- `manifest_sync_status=pending|synced|failed`
- `manifest_synced_at`
- `manifest_sync_error`

## 7. 服务身份与授权

Chat 使用现有：

```http
X-Service-Api-Key: svc_...
```

Knowledge 根据 key 解析 `ServicePrincipal`，再派生 owner。调用方不能提交 wallet address。

第一阶段权限规则：

- active principal 可以创建自己名下的 run。
- principal 只能读取、更新自己创建的 run。
- run 引用 KB/release/evidence 时，必须存在有效 `ServiceGrant`。
- principal 被 disabled/revoked 后不能创建或修改 run。
- owner 的 Knowledge JWT 可以审查其全部 run。
- Warehouse 凭证只存在 Knowledge 后端，不返回 Chat。

后续如果需要限制哪些 principal 可以创建 run，再引入独立 `ExecutionGrant`。验证阶段不修改 `ServiceGrant` 的知识读取语义。

## 8. API

服务侧：

```text
POST /service/runs
GET  /service/runs/{run_id}
PUT  /service/runs/{run_id}/context
POST /service/runs/{run_id}/artifacts
POST /service/runs/{run_id}/complete
POST /service/runs/{run_id}/fail
```

所有服务侧接口使用 `X-Service-Api-Key`。

管理侧：

```text
GET /runs
GET /runs/{run_id}
POST /runs/{run_id}/manifest/retry
```

所有管理侧接口使用 `Authorization: Bearer <knowledge_jwt>`，并按 owner 过滤。

第一阶段 artifact API 只登记已经写入 Warehouse 的文件，或者由 Knowledge 接收文件后转存 Warehouse。最终选择以 Chat 的上传链路为准，不能允许调用方登记任意 Warehouse 路径。

## 9. Chat 集成

```text
Chat 开始研究任务
  -> POST /service/runs
  -> Knowledge 返回 runId
  -> Chat 调用 /service/search，携带 runId/traceId
  -> Knowledge 把 RetrievalLog 关联到 run
  -> Chat 上传/登记 artifact
  -> POST /service/runs/{runId}/complete
  -> Knowledge 写 manifest 到 Warehouse
```

Chat 的 `ChatMessage` 只保存可选 `runId`，不保存 manifest 全量内容和 Warehouse 凭证。

普通闲聊不创建 run。第一阶段仅对稳定的研究技能 ID 启用，不能按中文显示名称判断。

## 10. 与 RetrievalLog 的关系

`RetrievalLog` 增加可选 `agent_run_id`：

- 一个 run 可以有多条 retrieval log。
- retrieval log 记录一次检索请求和结果摘要。
- run 记录完整任务生命周期。
- manifest context 可引用 retrieval log ID 和它命中的 evidence/item/release。

这能复用现有审计能力，又不会混淆“一次检索”和“一次任务”。

## 11. 失败与重试

- 创建 run 使用 `external_id` 幂等，网络重试返回原 run。
- context 更新使用 `updated_at` 或版本号做乐观并发控制。
- 完成操作幂等：已经以相同状态完成时返回当前 run。
- `completed` 与 `failed/cancelled` 之间不允许切换。
- Warehouse manifest 写入失败不回滚已经完成的模型任务，改为异步重试。
- artifact 文件写入成功但数据库登记失败时，通过 run 目录扫描进入运维对账，不自动认领未知文件。

## 12. 隐私与安全

- manifest 不写 API key、UCAN、模型密钥、完整系统 prompt。
- 错误只保存脱敏摘要。
- context 默认保存引用和必要摘要，不复制完整聊天历史。
- Warehouse 路径必须通过 `ensure_current_app_path()` 校验。
- artifact 文件名不能参与路径拼接，服务端生成安全 key。
- 每次 artifact 登记验证大小、MIME 和 SHA-256。
- owner 删除或撤销凭证时，Knowledge 保留数据库记录并显示 Warehouse asset unavailable。

## 13. 实施阶段

### M1：数据库闭环

- 新增 `AgentRun`、`AgentRunArtifact`。
- `RetrievalLog` 增加可选 `agent_run_id`。
- 实现 service API 的创建、查询、context 更新和终态。
- 不写 Warehouse manifest，先验证 Chat 调用和权限。

### M2：Warehouse 投影

- 使用现有写凭证创建 `runs/<run-id>`。
- 写 artifact 和 manifest。
- 增加 manifest 同步状态及重试。
- WebDAV/S3 验证文件可读。

### M3：Chat 产品验证

- 仅研究技能接入 runId。
- 关联 service search/retrieval log。
- 展示输入、context、artifact 和状态。
- 完成至少 20 次真实任务。

### M4：标准化验证

- 提供 MCP resource/tool 或独立 SDK。
- 使用非 Chat 客户端完成创建、检索和 artifact 读取。
- 根据验证结果决定是否继续建设通用 Agent Context Service。

## 14. 验收标准

- principal 不能访问其他 principal 的 run。
- 没有有效 KB grant 时不能把该 KB 的证据加入 context。
- 终态 run 不可修改。
- 同一个 external id 重试不生成重复 run。
- artifact 路径始终位于 Knowledge app 的当前 run 下。
- manifest 可以从数据库重建。
- WebDAV/S3 可读取 manifest 和 artifact。
- principal 撤销后历史 run 可审查、新 run 被拒绝。
- Chat 普通聊天和现有 Warehouse 上传/导入流程不回归。
