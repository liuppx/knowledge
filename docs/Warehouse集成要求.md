# Warehouse 集成要求

> 状态：Knowledge V2 M0 契约与联调清单
>
> 日期：2026-08-05
>
> 架构来源：[知识库架构 V2](知识库架构V2.md)

## 1. 目的

本文用于 Knowledge 与 Warehouse 联合研发，记录 Knowledge 分析 CSV/Excel 和持续同步所依赖的数据面契约。它不把 Warehouse 内部实现描述成已经公开的能力，也不替代 Warehouse 自己的 OpenAPI。

## 2. 已确认的 Warehouse 基线

| 能力 | 代码基线 | 当前判断 |
| --- | --- | --- |
| 对象元数据 | `/api/v1/public/assets/object` | 已公开，返回 path、size、ETag、checksum、content type 和 modified time |
| 内容读写 | `/api/v1/public/assets/object/content` | 已公开 `HEAD/GET/PUT` |
| Range | 内容接口使用 HTTP 内容服务 | 需要契约探针确认 `206`、`Content-Range` 和边界行为 |
| SHA-256 | 响应字段和 `X-Warehouse-Checksum-SHA256` | 已有基础，需验证大对象 HEAD 是否会扫描全文 |
| 上传会话 | `/api/v1/public/uploads/sessions*` | 已公开基础路由，原子 finalize 和幂等语义仍需联合确认 |
| 路径权限 | UCAN app scope、S3 credential root path/permissions | 已有基础，缺少单 Run 临时委托契约 |
| mutation outbox | Warehouse replication 内部表和服务 | 不是外部订阅 API，Knowledge 当前不能消费 |

## 3. M0 阻塞项

| 编号 | 阻塞项 | Warehouse 需要输出 | Knowledge 依赖原因 |
| --- | --- | --- | --- |
| WH-P0-01 | 缺少明确不可变版本标识 | `versionId` 或等价的版本/修订语义；说明 ETag 跨节点和覆盖后的行为 | Run 必须冻结输入，路径不能代表版本 |
| WH-P0-02 | 元数据读取成本不明确 | HEAD/metadata 的时间复杂度、checksum 来源和 500 MB 文件压测结果 | 分析前不能为读取元数据扫描完整对象 |
| WH-P0-03 | 条件读取契约未冻结 | `Range`、`If-Match`、`412`、多节点一致性和错误体 | 防止分析过程中静默读到被替换文件 |
| WH-P0-04 | 产物原子提交契约未冻结 | upload session initiate/part/complete/abort OpenAPI，完成前可见性和 checksum 规则 | 大型结果文件不能以半成品暴露 |
| WH-P0-05 | 幂等语义缺失 | PUT/finalize 的 `Idempotency-Key` 作用域、保留时间和冲突响应 | Worker 网络重试不能重复产物或错误覆盖 |
| WH-P0-06 | 单 Run 授权缺失 | 短期、单路径、读写分离的 delegated token/capability | Worker 不应持有用户或 Knowledge 长期凭证 |
| WH-P0-07 | 错误模型未统一 | 版本化错误 schema 和稳定错误码 | Knowledge 需要判断可重试、用户错误和配额错误 |
| WH-P0-08 | 调用关联不足 | `X-Request-ID`/correlation ID 的接收、返回和日志规则 | Warehouse 操作必须关联 AgentRun/Step |

上述项目中，WH-P0-01、02、03、04、06 是生产 M1 的上线阻塞项。开发环境可以用 `path + etag + sha256` 和 Knowledge 现有 owner credential 过渡，但不得作为最终安全模型。

## 4. P1 需求

### 4.1 外部资产变更流

Warehouse 需要在 replication outbox 之外提供面向外部服务的稳定事件契约：

```json
{
  "schema": "warehouse.asset-change.v1",
  "eventId": "evt_...",
  "cursor": "000000012345",
  "ownerId": "...",
  "operation": "created|updated|moved|deleted",
  "path": "/apps/knowledge.yeying.pub/uploads/source.csv",
  "sourcePath": null,
  "versionId": "ver_...",
  "etag": "...",
  "sha256": "...",
  "occurredAt": "2026-08-05T08:00:00Z"
}
```

必须说明 cursor 单调范围、至少一次投递、重复事件、断点 replay、retention、move 的源目标语义以及删除后版本元数据的保留时间。

### 4.2 服务端资产操作

- 同一 owner/授权范围内 server-side copy/move。
- 写入前配额预检。
- 单对象、单 part、part 数和临时空间上限查询。
- OpenAPI 和事件 schema 的兼容版本策略。

## 5. 契约探针

Knowledge 提供只依赖 Warehouse 公开 HTTP API 的探针：

```bash
python scripts/verify_warehouse_contract.py \
  --base-url http://127.0.0.1:6065 \
  --asset-path /apps/knowledge.yeying.pub/contract-fixtures/10mb.csv \
  --username "$WAREHOUSE_USERNAME" \
  --password "$WAREHOUSE_PASSWORD" \
  --output ../artifacts/warehouse-contract-10mb.json
```

写入验证必须显式提供一次性测试路径：

```bash
python scripts/verify_warehouse_contract.py \
  --base-url http://127.0.0.1:6065 \
  --asset-path /apps/knowledge.yeying.pub/contract-fixtures/500mb.csv \
  --write-path /apps/knowledge.yeying.pub/contract-fixtures/probe-output.txt \
  --bearer-token "$WAREHOUSE_TOKEN"
```

默认不写 Warehouse。探针验证：

- metadata 必需字段；
- HEAD identity headers；
- 64 字节 Range 是否严格返回 `206`；
- 错误 ETag 的 `If-Match` 是否返回 `412`；
- 声明 SHA-256 与实际内容是否一致；
- 可选的 checksum PUT。

探针不会自动删除写入对象，测试路径必须由联调方明确提供并按 Warehouse 流程清理。

## 6. M0 通过标准

1. 10 MB CSV、500 MB CSV、多 sheet/公式/隐藏行 XLSX 各有一份探针报告。
2. Range 和 checksum 正确；HEAD 不扫描完整对象，500 MB P95 达到双方约定值。
3. Warehouse 为所有 M1 上线阻塞项提供 OpenAPI 或已排期的接口设计。
4. Knowledge 和 Chat 冻结 `spreadsheet_analysis` Run 输入、事件与产物 schema。
5. 任何暂时降级方案都记录期限和替换条件，不把过渡凭证方案写成生产结论。
