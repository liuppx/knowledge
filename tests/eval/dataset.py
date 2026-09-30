"""Fixed Q01–Q12 corpus and questions for the retrieval eval.

Questions are verbatim from docs/产品验证知识库.md §3; ``expected`` holds the
"预期主要来源" documents as stable keys. Passages are condensed excerpts of the
11 documents listed in §2 (facts kept faithful to the source docs — worker
scripts, endpoint paths, credential rules, manifest fields), so this fixture
stays deterministic and CI-sized. The full-document human eval described in
§4–§6 runs the same questions against the real imported docs.

Q11 lists 知识库架构V2 as a source, but §2 excludes it from import; expected is
therefore README + 架构V1. Q12 has no gold document by design.
"""

from __future__ import annotations

DOCS: dict[str, dict] = {
    "readme": {
        "file": "README.md",
        "passages": [
            "knowledge 是夜莺社区的知识库控制面服务，负责资产接入、知识生产、发布治理与检索。docs/README.md 是文档入口，"
            "列出当前有效文档；标注为 V2 或待办的文档描述未来目标，不属于当前事实来源。",
            "文档权威性约定：README 与《知识库架构V1》描述当前实现，是事实来源；《知识库架构V2》与《Warehouse鉴权收口待办》"
            "描述未来架构与待办事项，阅读时需要谨慎看待，不应当作已实现能力引用。",
        ],
    },
    "arch_v1": {
        "file": "知识库架构V1.md",
        "passages": [
            "写路径：Source 资产接入（warehouse 同步）→ 文档解析与切片 chunk → Evidence 抽取 → 知识项 revision 生产 → "
            "Release 发布。每一步都保留可追溯的来源引用。",
            "读路径：/service/search 经 grant 与 release 解析权限后，在正式知识项与 Evidence 上执行检索"
            "（formal_first / formal_only / evidence_only），并写入 RetrievalLog 供审计。",
            "架构分层：资产接入、知识生产、发布治理、检索服务四个模块各自独立；V1 以 PostgreSQL 为唯一数据库，"
            "当前架构文档描述的是已实现的事实，V2 文档另行描述未来目标。",
        ],
    },
    "product_boundary": {
        "file": "社区产品关系与开发边界.md",
        "passages": [
            "社区产品关系：knowledge 只做知识库控制面；对话体验属于 Chat，模型渠道管理属于 Router，智能体编排属于 Agent。"
            "knowledge 不重复建设这些能力。",
            "开发边界：其他社区应用通过冻结的 /service/* 契约消费知识，不直接读写 knowledge 数据库。",
        ],
    },
    "agent_run": {
        "file": "Agent运行与上下文资产设计.md",
        "passages": [
            "Agent Run、Context Manifest 和 Artifact Provenance 归属 knowledge。Agent Run 的 manifest 包含核心信息："
            "run_id、发起者钱包地址、所用知识库与 release 版本、input_manifest_json（输入引用摘要）、"
            "context_manifest_json（上下文引用摘要）、产出的 artifact 清单以及运行状态与时间戳。",
            "manifest.json 由 Knowledge 写入并维护，随大文件一起放入 knowledge 自己的 Warehouse app 空间；"
            "Knowledge 数据库记录和 Warehouse manifest 可以相互校验。",
            "Agent Run artifact 是运行产物（生成的表格、报告文件），按 run 归档并带 provenance 可回查；"
            "RetrievalLog 则是检索审计记录，记录每次 /service/search 的查询、命中与 trace。两者职责不同，"
            "运行产物与检索审计不应混为一谈。",
        ],
    },
    "api_access": {
        "file": "API接入文档.md",
        "passages": [
            "API 接入文档：社区应用先通过 Passport 登录换取访问令牌，再以 Bearer token 调用 /service/search、"
            "/service/search/formal、/service/search/evidence 三个检索接口。",
            "接入约定：/service/* 契约已冻结，字段只增不改；消费方应按 openapi/knowledge.openapi.yaml 生成客户端。",
        ],
    },
    "console_manual": {
        "file": "控制台操作手册.md",
        "passages": [
            "控制台操作手册——首次登录后的推荐操作顺序：1) 使用 Passport 登录；2) 连接 warehouse 并配置读凭证；"
            "3) 创建知识库；4) 从 warehouse 选择目录创建 Source 或绑定，触发导入任务；5) 在文档列表确认文件处理状态；"
            "6) 在检索实验室完成一次可验证的检索。",
            "导入任务失败排查：先在控制台「文档列表」查看文件级处理状态（排队 / 处理中 / 失败）与错误信息，"
            "再进入「任务」页查看导入任务状态并重试；若任务长期停留在排队，需要检查 worker 是否在运行。",
            "知识地图与知识项详情页可回查来源文档、Evidence、revision 与发布状态；切换知识库后列表只显示当前知识库数据。",
        ],
    },
    "control_plane_api": {
        "file": "控制面API文档.md",
        "passages": [
            "控制面 API：创建知识库使用 POST /kbs；上传文件先经 GET /warehouse/uploads 与 warehouse 的 uploads 目录"
            "（/apps/knowledge.yeying.pub/uploads）完成；创建导入任务使用 POST /kbs/{kb_id}/tasks/import，"
            "另有 POST /kbs/{kb_id}/tasks/reindex 与 POST /kbs/{kb_id}/tasks/delete。",
            "绑定与来源：POST /kbs/{kb_id}/bindings 绑定 warehouse 目录，POST /kbs/{kb_id}/sources 创建 Source；"
            "基于绑定的任务使用 POST /kbs/{kb_id}/tasks/import-from-bindings。控制面端点面向 owner，"
            "与消费方 /service/* 冻结契约分离。",
        ],
    },
    "openapi_spec": {
        "file": "openapi/knowledge.openapi.yaml",
        "passages": [
            "openapi/knowledge.openapi.yaml 是接口契约真源：paths 列出 POST /kbs（创建知识库）、"
            "GET /warehouse/uploads（上传目录）、POST /kbs/{kb_id}/tasks/import（创建导入任务）以及 /service/search 系列检索接口。",
        ],
    },
    "bot_chat_prd": {
        "file": "Bot与Chat知识库重构PRD.md",
        "passages": [
            "Bot 与 Chat 知识库重构 PRD 目标：让 Bot / Chat 通过统一的 /service/search 契约消费 knowledge 发布的知识，"
            "替换各自的私有检索。",
            "非目标——本阶段不做以下事项：不在 knowledge 内实现对话界面；不做模型渠道管理；不做 Bot 编排与多轮状态机；"
            "不迁移 Chat 历史消息到 knowledge。",
        ],
    },
    "warehouse_auth": {
        "file": "Warehouse鉴权与绑定重构说明.md",
        "passages": [
            "Warehouse 鉴权与绑定重构说明：浏览、上传与绑定使用不同凭证语义，原因是安全边界不同——浏览只需只读授权，"
            "上传需要写授权且应短期有效，绑定则是把用户的 warehouse 授权与知识库目录关联的长期关系。",
            "凭证按最小权限原则分离：读凭证泄露仅影响可见性，写凭证泄露可能篡改语料，因此写凭证不作为通用凭证发放，"
            "仅在上传会话内使用。",
        ],
    },
    "warehouse_credentials": {
        "file": "Warehouse凭证使用说明.md",
        "passages": [
            "Warehouse 凭证使用说明：读凭证用于浏览 warehouse 目录和绑定 Source（只读场景），一把读凭证对应一个绑定源或"
            "一类目录，不要把同一把读凭证复用到无关目录；写凭证用于上传文件到 warehouse（写入场景），单独配置一把 app 级写凭证，"
            "不要把写凭证当通用读凭证来发放。",
            "获取凭证：在控制台选择「连接 warehouse 初始化 uploads 读写凭证（推荐）」，或分别填入读凭证与写凭证；"
            "绑定后即可在创建 Source 时浏览目录。",
        ],
    },
    "worker_deploy": {
        "file": "Worker部署与扩缩容建议.md",
        "passages": [
            "Worker 部署与扩缩容建议：导入 worker 独立部署，以 python -m knowledge.workers.runner 启动，"
            "或使用启动脚本 ./scripts/run_worker.sh 1；worker 与 API 共享 DATABASE_URL 与同一份环境变量。",
            "常驻 1 个 worker，按需扩到 4 个：依次运行 ./scripts/run_worker.sh 2、3、4 增加实例，任务通过 lease 互斥，"
            "不会重复处理；「最多 4 个 worker」是第一阶段的合理上限，而不是硬限制。",
            "worker 故障排查：查看 worker 日志、任务 lease 是否过期（WORKER_RUN_LEASE_TTL_SECONDS）、心跳是否更新；"
            "导入任务长期排队通常是 worker 未运行或并发被占满，如果 4 个 worker 仍然排队严重，优先排查任务本身。",
        ],
    },
}

QUESTIONS: list[dict] = [
    {"id": "Q01", "kind": "单文档事实", "query": "knowledge 中读凭证和写凭证分别用于什么场景？", "expected": ["warehouse_credentials"]},
    {"id": "Q02", "kind": "单文档事实", "query": "如何启动常驻 worker，并在需要时扩容到 4 个？", "expected": ["worker_deploy"]},
    {"id": "Q03", "kind": "单文档事实", "query": "Agent Run 的 manifest 包含哪些核心信息？", "expected": ["agent_run"]},
    {"id": "Q04", "kind": "API 定位", "query": "创建知识库、上传文件和创建导入任务分别使用哪些接口？", "expected": ["openapi_spec", "control_plane_api"]},
    {"id": "Q05", "kind": "用户流程", "query": "从第一次登录到完成一次可验证检索，推荐操作顺序是什么？", "expected": ["console_manual", "warehouse_credentials"]},
    {"id": "Q06", "kind": "架构理解", "query": "knowledge 的写路径和读路径分别经过哪些模块？", "expected": ["arch_v1"]},
    {"id": "Q07", "kind": "产品边界", "query": "Bot / Chat 知识库重构明确不做哪些事情？", "expected": ["bot_chat_prd"]},
    {"id": "Q08", "kind": "权限边界", "query": "为什么 warehouse 浏览、上传和绑定需要使用不同凭证语义？", "expected": ["warehouse_auth", "warehouse_credentials"]},
    {"id": "Q09", "kind": "故障处理", "query": "导入任务失败后，用户应该从哪些页面和状态开始排查？", "expected": ["console_manual", "worker_deploy"]},
    {"id": "Q10", "kind": "跨域关联", "query": "Agent Run artifact 与 RetrievalLog 的职责有什么不同？", "expected": ["agent_run"]},
    {
        "id": "Q11",
        "kind": "权威性",
        "query": "当前哪些文档属于事实来源，哪些内容需要谨慎看待？",
        "expected": ["readme", "arch_v1"],
        "note": "架构V2 按 §2 未导入",
    },
    {
        "id": "Q12",
        "kind": "无答案",
        "query": "knowledge 是否支持自动把内容发布到微信公众号？",
        "expected": [],
        "note": "否定性测试，检索层仅记录命中，由答案层判断无依据",
    },
]
