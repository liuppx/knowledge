# knowledge OpenAPI

`knowledge.openapi.yaml` 是 knowledge HTTP API 的权威接口契约，由 FastAPI 应用实际注册的路由和 Pydantic schema 自动生成。

## 文件

- `knowledge.openapi.yaml`：OpenAPI 3.1 接口定义。
- `../../API接入文档.md`：服务接入顺序、认证方式和使用建议。
- `../../控制面API文档.md`：控制台与治理场景说明。

## 更新规范

后端增加、删除或修改接口后，在仓库根目录执行：

```bash
backend/.venv312/bin/python backend/scripts/export_openapi.py
```

提交接口代码时，应同时提交更新后的 `docs/openapi/knowledge.openapi.yaml`。

不要手工编辑生成文件。接口字段、请求体和响应结构应在 FastAPI 路由或 Pydantic schema 中修改，然后重新导出。

## 本地查看

启动 knowledge API 后，可以使用 FastAPI 自带页面查看当前运行版本：

- Swagger UI：`http://127.0.0.1:8000/docs`
- ReDoc：`http://127.0.0.1:8000/redoc`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`

仓库中的 YAML 用于代码审查、SDK 生成、接口测试和外部系统集成；运行时 `/openapi.json` 用于确认当前服务实际加载的接口版本。
