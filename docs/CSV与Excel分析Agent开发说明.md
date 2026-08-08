# CSV 与 Excel 分析 Agent 开发说明

> 状态：Knowledge V2 M1 进行中
>
> 日期：2026-08-05
>
> 架构来源：[知识库架构 V2](知识库架构V2.md)

## 1. 当前实现

服务调用方创建：

```http
POST /service/runs
X-Service-Api-Key: svc_...
Content-Type: application/json

{
  "session_id": "chat-session-1",
  "external_id": "chat-session-1:message-1",
  "run_type": "spreadsheet_analysis",
  "inputs": [
    {
      "kind": "warehouse_asset",
      "warehousePath": "/apps/knowledge.yeying.pub/uploads/sales.csv",
      "sha256": "...",
      "size": 1024,
      "contentType": "text/csv"
    }
  ],
  "intent": "检查字段结构和空值",
  "constraints": {
    "analysis_plan": {
      "group_by": ["region"],
      "aggregations": [
        {"column": "amount", "op": "sum", "alias": "total_amount"}
      ],
      "sort": [{"column": "total_amount", "direction": "desc"}],
      "limit": 1000
    },
    "output_formats": ["markdown", "csv", "xlsx", "png"]
  }
}
```

Run 初始状态为 `queued`。常驻 Worker 领取后依次执行：

```text
resolve -> profile -> publish -> completed
```

当前生成：

- `profile.json`：格式、行列数、字段类型、空值和少量样本。
- `analysis-plan.json`：经过白名单校验的版本化分析计划。
- `result.csv`：计划产生数据结果时生成，包含公式注入防护。
- `result.xlsx`：带冻结表头、筛选和基本列宽的 Excel 结果，聚合字段保持数值类型。
- `chart.png`：分组数值聚合的基础柱状图，固定为 1000×600，最多展示 20 项。
- `summary.md`：面向 Chat 展示的字段概览。
- `manifest.json`：Run、输入和 Artifact 的 Warehouse 投影。

查询接口：

```text
GET /service/runs/{run_id}
GET /service/runs/{run_id}/inputs
GET /service/runs/{run_id}/steps
GET /service/runs/{run_id}/events?after=<sequence>
GET /service/runs/{run_id}/artifacts
```

`events` 当前是 JSON 增量查询。SSE 和 `Last-Event-ID` 续传属于 M2，Chat 当前应轮询并携带最后收到的 sequence。

## 2. 自然语言计划生成

当调用方没有提供 `constraints.analysis_plan` 且配置了 Router 时，Knowledge 使用 OpenAI 兼容接口把 `intent` 转换为相同的白名单计划：

```dotenv
MODEL_PROVIDER_MODE=openai_compatible
MODEL_GATEWAY_BASE_URL=https://router.example/v1
MODEL_GATEWAY_API_KEY=...
ANALYSIS_PLANNER_MODEL=gpt-4o-mini
ANALYSIS_PLANNER_TIMEOUT_SECONDS=30
```

Knowledge 只向 Router 发送：

- 用户分析意图；
- 文件格式和行数；
- 字段名、推断类型、空值数和非空数。

不会发送 profile 中的样本值、完整行或 Warehouse 凭证。请求使用 `response_format=json_object`、`temperature=0`，返回计划仍需通过本地白名单和真实列名校验。

`analysis-plan.json.generatedBy` 记录 provider、模型、response ID、token usage 和 prompt version。Router 未配置、请求失败、JSON 非法或计划引用未知字段时，自动降级为 `profile_only`，并记录 `fallbackReason`；不会尝试执行模型文本。

## 3. M1 限制

- 输入路径必须位于 Knowledge 当前 Warehouse app scope；Chat app 跨空间访问等待 Warehouse delegated token。
- 单文件压缩前最大 50 MiB，最多 profile 100,000 行、256 列。
- CSV 支持 UTF-8/UTF-8 BOM 和 GB18030，探测 `,`、Tab、`;`、`|` 分隔符。
- XLSX 使用只读 ZIP/XML profile，不重新计算公式，不执行宏；展开后内容上限 200 MiB。
- 已支持选列、过滤、排序、分组以及 `count/sum/avg/min/max` 聚合；暂不支持 Join、窗口函数和多序列/自定义图表。
- `output_formats` 支持 `markdown/csv/xlsx/png`；未指定时默认生成 CSV、XLSX，并在适用时生成 PNG。
- Worker 当前读取完整对象；Range、DuckDB/PyArrow 流式处理属于 M2。

## 4. 运行 Worker

```bash
scripts/run_worker.sh 1
```

Worker 同时处理原有知识导入任务和排队的 spreadsheet analysis Run。开发和测试环境使用 SQLite 时并发固定为 1。

## 5. 错误语义

- 输入不是 CSV/XLSX：创建 Run 返回 `400`。
- 输入 SHA-256 与读取内容不同：Run 进入 `failed`，防止路径覆盖导致输入替换。
- 文件超过 M1 限制、编码无法识别、XLSX 损坏或包含宏：Run 进入 `failed`。
- Warehouse 临时读取错误会标记为可重试事件；自动 retry/attempt 属于 M2。

失败原因只写入脱敏摘要，不能包含 Warehouse 密钥或完整文件内容。

## 6. 下一开发批次

1. 基于 DuckDB/PyArrow 替换 M1 内存执行器。
2. Chat 服务端代理、Run 状态 UI 和产物下载。
3. SSE、取消检查、retry/attempt 和大文件流式处理。
