# AI Chat

一个基于 FastAPI 的聊天系统，支持两种数据库模式：

- 本地开发：SQLite，零依赖，按需启动
- 生产部署：PostgreSQL

## 本地开发

本地默认直接使用 SQLite 文件，不需要常驻 PostgreSQL。

1. 安装 Python 3.11
2. 创建虚拟环境并安装依赖
3. 复制 `.env.example` 为 `.env`
4. 启动：

```bash
python main.py
```

默认数据库文件为 `data/chat.db`。不用时直接关闭进程即可，没有额外数据库服务需要常驻。

## 生产部署

生产环境继续使用 PostgreSQL，只需要把 `DATABASE_URL` 配成：

```env
DATABASE_URL=postgresql://ai_chat:your_password@localhost:5432/ai_chat
```

其余规则不变：

- `.env` 只负责启动期配置和首次初始化
- 数据库负责系统运行配置和用户业务配置

## `.env` 中保留的内容

- `DATABASE_URL`
- `SECRET_KEY`
- `BOOTSTRAP_ADMIN_USERNAME`
- `BOOTSTRAP_ADMIN_PASSWORD`
- `BOOTSTRAP_SYSTEM_API_KEY`
- `BOOTSTRAP_SYSTEM_API_BASE`
- `BOOTSTRAP_SYSTEM_MODEL`

## 运行期数据库配置

- `system_config` 表：
  - 系统 `api_base`
  - 系统 `api_key`
  - 系统默认模型
- `users` 表：
  - 用户账号密码
  - 用户专用 `api_key`
  - 用户默认模型
  - 用户模型白名单
