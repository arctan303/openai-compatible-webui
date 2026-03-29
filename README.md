# AI Chat

一个基于 FastAPI + PostgreSQL + Vanilla JS 的聊天系统，支持流式对话、历史同步、模型白名单和管理后台。

## 配置规则

项目现在采用两层配置边界：

- `.env` 只负责启动期配置和首个管理员初始化
- 数据库负责系统运行配置和用户业务配置

### `.env` 中保留的内容

- `DATABASE_URL`
- `SECRET_KEY`
- `BOOTSTRAP_ADMIN_USERNAME`
- `BOOTSTRAP_ADMIN_PASSWORD`
- `BOOTSTRAP_SYSTEM_API_KEY`
- `BOOTSTRAP_SYSTEM_API_BASE`
- `BOOTSTRAP_SYSTEM_MODEL`

其中：

- `DATABASE_URL` 和 `SECRET_KEY` 每次启动都会读取
- `BOOTSTRAP_*` 只在数据库首次初始化时用于写入默认数据

### 数据库中的运行配置

- `system_config` 表：
  - 系统 `api_base`
  - 系统 `api_key`
  - 系统默认模型
- `users` 表：
  - 用户账号密码
  - 用户专用 `api_key`
  - 用户默认模型
  - 用户模型白名单

系统启动后，聊天和模型列表接口统一读取数据库里的 `system_config`，不再依赖 `.env` 中的系统 API 配置。

## 快速启动

1. 复制 `.env.example` 为 `.env`
2. 按需修改数据库连接、`SECRET_KEY` 和 bootstrap 管理员账号
3. 启动：

```bash
docker compose up -d
```

首次启动后，登录后台即可在数据库中维护系统 API 配置和默认模型。
