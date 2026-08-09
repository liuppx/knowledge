# knowledge

Knowledge 是知识运营与发布服务。后端在 `knowledge/`，前端工程在 `web/`。

## 本地启动

需要本机已安装：

- Python 3.10+，命令使用 `python3`
- Node.js 与 npm

### 1. 启动后端

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

### 2. 启动前端

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

### 3. 可选：启动 worker

导入、重建、删除等异步任务需要 worker。另开一个终端，在项目根目录执行：

```bash
source .venv/bin/activate
python -m knowledge.workers.runner
```

## 常见问题

- `Address already in use`：端口被占用。后端可改 `--port 8001`；前端可用 `npm run dev -- --port 5174`。
- `unsupported operand type(s)` 或 `datetime | None` 类型注解错误：当前 `.venv` 使用了过低的 Python 版本，请用 Python 3.10+ 重建 `.venv`。
- 只做本地体验时，不需要复制 `.env.template`。没有 `.env` 时会使用 SQLite、本机 Warehouse S3 endpoint 和 mock model 默认配置。

## 更多文档

详细设计与接口文档在 `docs/` 目录。
