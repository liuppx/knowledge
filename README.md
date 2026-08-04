# knowledge

钱包知识运营与发布服务，围绕 `warehouse` 作为唯一资产中心构建来源、证据、知识项、发布、服务授权与检索审计能力。

## 当前实现范围

- 钱包 challenge/verify 登录，签发 `knowledge JWT`
- 多知识库 CRUD + 基础统计
- `warehouse` 读凭证 / 写凭证管理
- `knowledge` 代理浏览当前 `Warehouse App` 目录
- `knowledge` 上传文件到 `/apps/<warehouse_app_id>/uploads/`
- 手动导入 / 重建 / 删除的轻量异步任务
- 按知识库绑定源批量创建导入 / 重建 / 删除任务
- 绑定源状态管理（启用/停用、同步状态、最近任务、索引覆盖摘要）
- Source / Asset / Evidence / Candidate / Item / Release / Grant / Search Lab 主链路
- 导入治理：任务明细、重试、未变更跳过
- 运维能力：worker 心跳、数据库租约协调、运行概览、存储健康检查
- 文档解析、Evidence 构建、知识项治理、发布快照、服务授权
- `service search`、`retrieval logs`、`source governance` 与 search lab
- 长期记忆与短期记忆 CRUD（兼容模块，不再作为主产品叙事）
- 产品化前台管理台（仍在向知识运营台收口）

## 目录

- `backend/knowledge`: FastAPI 应用
- `tests`: 后端测试
- `docs/README.md`: 文档入口与版本说明
- `docs/知识库架构V1.md`: 当前已经实现的知识库架构
- `docs/知识库架构V2.md`: 尚未实现或尚未完整实现的目标架构
- `docs/社区产品关系与开发边界.md`: Knowledge 与社区其他系统的关系
- `docs/openapi/knowledge.openapi.yaml`: OpenAPI 3.1 权威接口定义
- `docs/openapi/README.md`: OpenAPI 生成与使用说明
- `docs/API接入文档.md`: 外部服务 API 接入文档
- `docs/控制面API文档.md`: 控制台 / 测试常用控制面接口文档
- `docs/控制台操作手册.md`: 控制台操作手册
- `docs/Warehouse鉴权与绑定重构说明.md`: `warehouse` 鉴权与绑定重构说明
- `docs/Warehouse凭证使用说明.md`: `warehouse` 读写凭证使用说明
- `docs/Warehouse鉴权收口待办.md`: `warehouse` 鉴权收口 TODO
- `docs/Bot与Chat知识库重构PRD.md`: bot/chat 产品重构 PRD
- `docs/Agent运行与上下文资产设计.md`: Agent Run、Context Asset 与 Chat/Warehouse 集成设计

## 本地启动

当前前端控制台由 FastAPI 直接服务：HTML 模板在 `backend/knowledge/templates`，静态资源在
`backend/knowledge/static`。本地开发不需要单独启动 Node / Vite 前端。

推荐使用 Python 3.12（至少需要 Python 3.10，以支持当前代码中的类型注解）。

### 1. 准备后端环境

```bash
cd backend
python3.12 -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt
```

如果本机没有 `python3.12`，可以先确认可用版本：

```bash
python3 --version
```

### 2. 使用本地默认配置启动 API + 控制台

第一次看产品现状时，建议先不要复制 `backend/.env.example`。没有 `.env` 时，项目会使用本地开发默认值：

- SQLite：`backend/knowledge.db`
- mock warehouse：仓库根目录下的 `.mock_warehouse`
- DB 向量存储
- mock embedding / model provider

启动 API 与控制台：

```bash
cd backend
source .venv312/bin/activate
uvicorn knowledge.main:app --reload --host 127.0.0.1 --port 8000
```

启动后打开：

- 控制台: `http://127.0.0.1:8000/`
- OpenAPI YAML: `docs/openapi/knowledge.openapi.yaml`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Health: `http://127.0.0.1:8000/health`

快速验证：

```bash
curl http://127.0.0.1:8000/health
```

期望返回：

```json
{"status":"ok"}
```

### 3. 启动 worker

导入、重建、删除等异步任务需要 worker 消费。另开一个终端：

```bash
cd backend
source .venv312/bin/activate
python -m knowledge.workers.runner
```

API 与 worker 必须使用同一份配置和同一个 `DATABASE_URL`。本地默认 SQLite 模式下，只建议启动 1 个
worker。

### 4. 可选：启用真实依赖

只有在需要连接真实 `warehouse`、PostgreSQL、Weaviate 或模型网关时，才复制并修改 `.env.example`：

```bash
cd backend
cp .env.example .env
```

常见切换项：

- `DATABASE_URL=postgresql://...`
- `WAREHOUSE_GATEWAY_MODE=bound_token`
- `VECTOR_STORE_MODE=weaviate`
- `MODEL_PROVIDER_MODE=openai_compatible`

生产或联调环境的具体凭证、WebDAV 地址、模型网关 Key 不要提交到 Git。

### 5. 常见问题

- 如果启动时报 `unsupported operand type(s)` 或类型注解相关错误，通常是 Python 版本过低；请使用
  Python 3.10+，推荐 Python 3.12。
- 如果 8000 端口被占用，可以改用 `--port 8001`，对应访问 `http://127.0.0.1:8001/`。
- 如果复制了 `.env.example` 但本机没有 PostgreSQL，启动会尝试连接 PostgreSQL；只看本地现状时可以先删除
  `backend/.env`，回到 SQLite/mock 默认配置。

## Worker 调度说明

当前 worker 采用按任务 claim/heartbeat 的调度方式：

- 多个 worker 可共享同一数据库协同消费导入任务
- 同一用户默认最多并发执行 1 个任务，避免单用户大任务挤占全部处理能力
- `sqlite` 环境会自动退回串行处理；生产建议使用 PostgreSQL 以启用更稳的并发处理
- 默认部署建议只常驻 `1` 个 worker，其余实例按需启停
- 独立 worker 的 systemd 部署与扩缩容建议见 `docs/Worker部署与扩缩容建议.md`

## 本地开发默认值

为了方便本地开发，默认配置并不强依赖真实的 `warehouse`、`Weaviate` 或模型网关：

- `warehouse` 默认走 `mock` 模式，本地目录模拟用户资产
- 向量检索默认走 `db` 模式，在数据库中保存向量并做 Python 侧相似度计算
- embedding 默认走 `mock` 模式，使用确定性伪向量

生产环境可切换为：

- `WAREHOUSE_GATEWAY_MODE=bound_token`
- `VECTOR_STORE_MODE=weaviate`
- `MODEL_PROVIDER_MODE=openai_compatible`

当前测试与验证口径：

- 已覆盖 `db` / `weaviate` 在过滤语义上的一致性验证
- 已覆盖 `mock` / `openai_compatible` embedding provider 的调用契约验证
- 当前 `service search` 仍以已发布知识项 / 证据的轻量词面匹配为主，不把语义向量召回作为当前版本保证
- 不把不同向量后端的相似度分值或排序完全一致作为当前版本保证

## 关键环境变量

- `DATABASE_URL`
- `JWT_SECRET`
- `WAREHOUSE_GATEWAY_MODE`
- `WAREHOUSE_BASE_URL`
- `WAREHOUSE_WEBDAV_PREFIX`
- `WAREHOUSE_APP_ID`
- `WAREHOUSE_APPS_PREFIX`
- `WAREHOUSE_MOCK_ROOT`
- `VECTOR_STORE_MODE`
- `WEAVIATE_URL`
- `MODEL_PROVIDER_MODE`
- `MODEL_GATEWAY_BASE_URL`
- `MODEL_GATEWAY_API_KEY`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSIONS`
- `WORKER_TASK_CONCURRENCY`
- `WORKER_MAX_ACTIVE_TASKS_PER_USER`
- `WORKER_TASK_HEARTBEAT_INTERVAL_SECONDS`
- `WORKER_NAME`
- `WORKER_RUN_LEASE_TTL_SECONDS`

## `warehouse` 代理约定

当前代码支持两种资产网关：

1. `mock`：本地目录模拟用户当前 `Knowledge App` 资产空间，便于开发测试
2. `bound_token`：`knowledge` 代理访问上游 `warehouse`，当前主流程使用用户手工导入的 WebDAV `ak/sk` 凭证

当前默认 app-only 配置：

- `WAREHOUSE_APP_ID=knowledge.yeying.pub`
- `WAREHOUSE_APPS_PREFIX=/apps`

当前控制台默认流程为：

1. 用户先登录 `knowledge`
2. 用户手工导入一把写凭证和一把或多把读凭证
3. 浏览 / 预览 / 绑定时显式选择读凭证或写凭证
4. 上传只使用写凭证
5. 导入 / 重建 / 删除任务按显式 `credential_id` 或 binding 绑定的读凭证执行

兼容说明：

- 旧 `/warehouse/auth/*` JWT / UCAN 绑定接口已经从当前仓库删除
- 当前仓库只保留基于读凭证 / 写凭证的 `warehouse` 访问主路径

当前默认线上配置：

- `WAREHOUSE_BASE_URL=https://webdav.yeying.pub`
- `WAREHOUSE_WEBDAV_PREFIX=/dav`

该模式不要求修改 `warehouse` 代码。

## 服务检索主入口

当前主服务接口已切到：

- `POST /service/search`
- `POST /service/search/formal`
- `POST /service/search/evidence`
- `GET /service/grants`
- `GET /service/kbs`
- `GET /service/releases/current`

已下线的旧主叙事接口：

- `POST /kbs/{kb_id}/search`
- `POST /retrieval-context`
- `POST /retrieval/context`
- `POST /bot/retrieval-context`
- `POST /retrieval/*`

## 文档

- 文档入口：`docs/README.md`
- 当前架构：`docs/知识库架构V1.md`
- 目标架构：`docs/知识库架构V2.md`
- 社区系统边界：`docs/社区产品关系与开发边界.md`
- OpenAPI 接口定义：`docs/openapi/knowledge.openapi.yaml`
- 外部服务接入：`docs/API接入文档.md`
- 控制面接口：`docs/控制面API文档.md`
- 控制台操作手册：`docs/控制台操作手册.md`
- `warehouse` 鉴权设计：`docs/Warehouse鉴权与绑定重构说明.md`
- `warehouse` 凭证使用：`docs/Warehouse凭证使用说明.md`
- `warehouse` 收口 TODO：`docs/Warehouse鉴权收口待办.md`
- 产品重构 PRD：`docs/Bot与Chat知识库重构PRD.md`
