# 数据库迁移（Alembic）

Knowledge 使用 Alembic 管理 PostgreSQL schema。**生产/部署环境不再使用 `Base.metadata.create_all`**；schema 的唯一演进方式是迁移。

## 运行

配置读取 `DATABASE_URL`（见 `.env`），迁移目录为 `migrations/`。

```bash
# 升级到最新（部署时执行；API 启动时也会自动执行一次）
alembic upgrade head

# 查看当前版本与历史
alembic current
alembic history

# 回退一步
alembic downgrade -1
```

API 进程启动时（`knowledge/main.py` 的 lifespan → `ensure_database_schema`）会自动把 schema 带到最新：

- 空库：执行迁移创建全部表。
- 已被 Alembic 管理的库：应用未执行的迁移。
- Alembic 之前用 `create_all` 建的老库（无 `alembic_version` 表）：自动 `stamp head` 收编，不会因表已存在而失败。

因此单实例部署无需额外步骤，从旧版本平滑升级也无需手工 stamp。**多实例或 API/Worker 分离部署时，建议在启动前由部署流程显式执行一次 `alembic upgrade head`**，避免并发实例同时迁移。

## 新增/修改模型后生成迁移

模型定义在 `knowledge/models/entities.py`，是 schema 的唯一真源。修改后：

```bash
# 对照模型自动生成迁移（需要一个可连接的数据库）
alembic revision --autogenerate -m "描述本次变更"
# 审阅生成的 migrations/versions/*.py，确认 upgrade/downgrade 正确后提交
```

生成后务必人工审阅：autogenerate 不能可靠检测列重命名、部分约束和数据迁移，这些需要手写。

## 与测试的关系

测试为速度直接用 `Base.metadata.create_all` 建表（见 `tests/conftest.py`），随后 `alembic stamp head` 标记为最新，使 API 启动的 `upgrade head` 成为空操作。因此模型与迁移必须保持一致——可用 `alembic check` 检测漂移（应输出 `No new upgrade operations detected`）。

## 历史遗留

`knowledge/db/schema.py` 的 `ensure_runtime_schema` 是 Alembic 之前用于给已建表补列/索引的兼容层。这些列与索引现已全部在模型和初始迁移中定义，新部署不依赖它；保留仅为过渡期测试路径使用。
