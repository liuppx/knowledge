# knowledge

Knowledge 是知识运营与发布服务。后端在 `knowledge/`，前端工程在 `web/`。

## 本地启动

需要本机已安装：

- Python 3.10+，命令使用 `python3`
- Node.js 与 npm
- Docker Desktop（用于 PostgreSQL）

### 1. 启动 PostgreSQL

项目只支持 PostgreSQL。先在项目根目录启动数据库：

```bash
docker compose up -d postgres
```

默认连接串为：

```dotenv
DATABASE_URL=postgresql://knowledge:knowledge@127.0.0.1:5432/knowledge?gssencmode=disable
```

如本机已有 PostgreSQL，请在 `.env` 中将 `DATABASE_URL` 改为其可用连接串。测试使用独立数据库 `knowledge_test`；可通过 `TEST_DATABASE_URL` 覆盖其连接串。

`compose.yaml` 会在首次创建数据卷时同时初始化 `knowledge_test`。已有 PostgreSQL 实例需要自行创建该数据库，或设置 `TEST_DATABASE_URL` 指向一个可由测试清空的 PostgreSQL 数据库。

### 2. 启动后端

在项目根目录执行：

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn knowledge.main:app --reload --host 127.0.0.1 --port 8000
```

后端启动后可以访问：

- API: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

如果已有 `.venv` 是旧 Python 创建的，请重建：

```bash
deactivate
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 启动前端

另开一个终端：

```bash
cd web
npm install
npm run dev
```

前端默认访问：`http://127.0.0.1:5173/`

前端开发服务器会把 `/api`、`/health`、`/kbs`、`/service` 代理到 `http://127.0.0.1:8000`，所以请先启动后端。

如果 5173 端口被占用：

```bash
npm run dev -- --port 5174
```

### 4. 可选：启动 worker

导入、重建、删除等异步任务需要 worker。另开一个终端，在项目根目录执行：

```bash
source .venv/bin/activate
python -m knowledge.workers.runner
```

## 常见问题

- `Address already in use`：端口被占用。后端可改 `--port 8001`；前端可用 `npm run dev -- --port 5174`。
- `unsupported operand type(s)` 或 `datetime | None` 类型注解错误：当前 `.venv` 使用了过低的 Python 版本，请用 Python 3.10+ 重建 `.venv`。
- `password authentication failed for user "knowledge"`：确认 PostgreSQL 已按上面的 Compose 配置启动，或在 `.env` 中填写实际可用的 `DATABASE_URL`。

## 更多文档

详细设计与接口文档在 `docs/` 目录。
