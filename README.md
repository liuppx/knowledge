# knowledge

Knowledge 是知识运营与发布服务。后端在 `knowledge/`，前端工程在 `web/`。

## 本地启动

需要本机已安装：

- Python 3.10+，命令使用 `python3`
- Node.js 与 npm
- PostgreSQL（本机服务或远程实例）

### 1. 准备 PostgreSQL

项目只支持 PostgreSQL。Knowledge 不负责启动数据库，请使用本机 PostgreSQL、系统服务或已有的远程实例。不要依赖 Docker/Compose 才能运行 Knowledge。

数据库准备好后，确认 `.env` 中的连接串可用：

```bash
psql "$DATABASE_URL" -c 'select 1'
```

默认连接串为：

```dotenv
DATABASE_URL=postgresql://knowledge:knowledge@127.0.0.1:5432/knowledge?gssencmode=disable
```

如本机已有 PostgreSQL，请在 `.env` 中将 `DATABASE_URL` 改为其可用连接串。测试使用独立数据库 `knowledge_test`；可通过 `TEST_DATABASE_URL` 覆盖其连接串，该库需要能被测试清空。

### 2. 安装依赖并准备配置

在项目根目录执行：

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
(cd web && npm install)
cp .env.template .env        # 按需修改 DATABASE_URL 等；生产配置见 docs/部署指南.md
```

服务配置的优先级为：进程环境变量 > `.env` > `config/local.toml` > `config/defaults.toml`。本地开发通常只需要 `.env`；部署主机在 `config/local.toml` 中取消注释并填入真实值。

### 3. 本地直接启动

Knowledge 的本地完整联调由一个后端进程和一个后台任务进程组成。它们是同一个产品的内部运行角色，不需要安装或启动两个产品。

先在第一个终端启动后端：

```bash
source .venv/bin/activate
python -m uvicorn knowledge.main:app --reload --host 127.0.0.1 --port 8002
```

再在第二个终端启动后台任务处理：

```bash
cd /path/to/knowledge
source .venv/bin/activate
python -m knowledge.workers.runner
```

后端只调试页面、接口或检索时，可以暂时不启动第二个进程；导入、重建索引、删除等异步任务需要它运行。

数据库迁移使用：

```bash
source .venv/bin/activate
python -m alembic upgrade head
```

运行测试：

```bash
source .venv/bin/activate
python -m pytest -q
```

后端启动后可以访问：

- API: `http://127.0.0.1:8002/`（已构建 `web/dist` 时直接是控制台）
- Health: `http://127.0.0.1:8002/health`
- Swagger UI: `http://127.0.0.1:8002/docs`

如果已有 `.venv` 是旧 Python 创建的，请重建：

```bash
deactivate
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. 启动前端开发服务器

另开一个终端：

```bash
cd web
npm run dev
```

前端默认访问：`http://127.0.0.1:5183/`

前端开发服务器会把所有服务请求代理到后端（默认 `http://127.0.0.1:8002`，可用 `KNOWLEDGE_API_URL` 改写），所以先启动后端。生产环境不运行开发服务器：`cd web && npm run build` 生成 `web/dist` 后由后端提供控制台。

如果 5183 端口被占用：

```bash
npm run dev -- --port 5184
```

### 5. 生产部署

生产部署使用 `scripts/starter.sh` 和 `scripts/package.sh`，不要把它们当成本地开发入口：

```bash
scripts/starter.sh start
scripts/starter.sh status
scripts/starter.sh stop
```

长期运行和扩展后台处理能力建议使用 systemd，参见 `docs/Worker部署与扩缩容建议.md`。

### 6. 创建离线部署包

构建前端并生成不依赖 Docker 的归档包（含 `knowledge/`、`migrations/`、`config/`、`web/dist/`）：

```bash
scripts/package.sh
```

## 常见问题

- `Address already in use`：端口被占用。后端可改 `--port 8003`；前端可用 `npm run dev -- --port 5184`。
- `unsupported operand type(s)` 或 `datetime | None` 类型注解错误：当前 `.venv` 使用了过低的 Python 版本，请用 Python 3.10+ 重建 `.venv`。
- `password authentication failed for user "knowledge"`：确认本机 PostgreSQL 已启动，或在 `.env` 中填写实际可用的 `DATABASE_URL`。

## 更多文档

详细设计与接口文档在 `docs/` 目录。
