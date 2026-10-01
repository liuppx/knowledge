# Knowledge Web（React SPA）

Knowledge 的产品前端：五个工作台（知识库概览 / 资产与导入 / 知识生产 / 检索台 / 发布与授权）+ Warehouse / 分析运行 / 运维。构建产物 `web/dist` 由 FastAPI 直接服务（`/` 与所有深链）。

## 技术栈

- Vite + React 19 + TypeScript（依赖版本钉死，`.npmrc` 设 `save-exact`）
- `react-router-dom`：URL 是知识库上下文的真源，`/kbs/:kbId/{overview,assets,production,search,release}`
- `@tanstack/react-query`：所有 query key 以 `kbId` 为前缀，切库不共享缓存；活动任务存在时按间隔轮询
- `openapi-typescript`：从 `docs/openapi/knowledge.openapi.yaml` 生成 `src/api/schema.d.ts`，前后端类型单一真源
- `vitest` + Testing Library

## 开发

```bash
cd web
npm ci
npm run dev            # http://127.0.0.1:5173，/kbs /auth /warehouse 等前缀代理到 KNOWLEDGE_API_URL（默认 127.0.0.1:8000）
npm run gen:api        # 后端接口变更并重导 OpenAPI 后，重新生成类型
npm run typecheck && npm test && npm run build
```

`npm run check:api` 会重新生成类型并以 `git diff --exit-code` 校验提交物未漂移（CI 阻塞）。改了后端接口的流程：改路由/schema → `python scripts/export_openapi.py` → `npm run gen:api` → 一起提交。

## 目录

```
src/api/        client.ts（Bearer、401 刷新一次、ApiError）、schema.d.ts（生成）、endpoints/*（按工作台的薄封装）、queries/*（react-query hooks）
src/app/        router.tsx、AppShell.tsx（侧栏 + KB 切换器）、kbRoute.tsx（:kbId 校验与记忆）、RequireAuth.tsx
src/ui/         Badge / DataTable / Drawer / ConfirmDialog / Toast / EmptyState 等原语，status.ts 为后端状态枚举 → 色调/文案映射
src/features/   auth、kbs、assets、production、search、release、warehouse、ops、analysis
src/styles/     tokens.css（移植自旧控制台的设计变量）
```

## 会话

登录后 `access_token` / `refresh_token` / 钱包地址存于 `localStorage`（`knowledge:*`）。任何请求 401 时客户端用 refresh token 刷新一次并重试；刷新失败则清除会话并派发 `knowledge:session-expired`，应用跳转 `/login`。上次使用的知识库记录在 `knowledge:last-kb`，访问 `/` 时自动回到该知识库概览。

## 部署

`npm run build` 后把 `web/dist` 放在仓库同级路径（FastAPI 在 `knowledge/main.py` 挂载 `web/dist/assets`，`routes_console.py` 服务 `index.html` 与深链回退）。没有 `web/dist` 时 `/` 返回一个构建提示页，API 不受影响。
