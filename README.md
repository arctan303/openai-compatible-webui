# openai-compatible-webui

一个轻量、简约、可自部署的 OpenAI 接口兼容聊天页面，支持用户管理、模型映射、历史会话和 Docker/SQLite 双模式部署。

## 功能概览

- 兼容 OpenAI API 格式的聊天接口
- 支持普通用户与管理员账户
- 支持系统模型配置、模型展示名称映射
- 支持历史会话保存、搜索与直链打开
- 支持 Markdown、代码高亮与数学公式渲染
- 支持 SQLite 与 PostgreSQL 两种存储模式

## 聊天页面预览

主页 / 聊天页面示意：

![主页预览图](./images/home.png)

## 管理后台

管理员可用于：

- 配置系统 API Base / API Key / 默认模型
- 获取系统模型并设置前端展示名称
- 管理用户、模型白名单与管理员权限

后台页面示意：

![后台管理页面](./images/admin.png)

## 技术栈

- FastAPI
- Jinja2
- httpx
- SlowAPI
- SQLite / PostgreSQL
- Vanilla JavaScript

## 运行要求

根据你的使用方式，准备以下环境之一。

### 方式一：PostgreSQL + Docker

推荐用于正式部署。

需要：

- Docker
- Docker Compose

### 方式二：SQLite 文件模式

推荐用于本地调试或轻量运行。

需要：

- Python 3.11 或更高版本

## 快速开始

### Windows 安装脚本

仓库内提供了 Windows PowerShell 安装脚本：

```powershell
.\install.ps1
```

脚本会提示你选择存储模式：

1. `PostgreSQL with Docker`
2. `SQLite file mode`

脚本会自动写入 `.env`。
如果你选择 PostgreSQL 模式，并且本机已安装 Docker，脚本还可以直接启动服务。

## 部署方式一：PostgreSQL + Docker

这是推荐的正式部署方式。

### 1. 配置 `.env`

你可以手动复制：

```powershell
Copy-Item .env.example .env
```

或直接运行：

```powershell
.\install.ps1
```

`.env` 中与 Docker / PostgreSQL 相关的重要配置如下：

```env
DATABASE_URL=postgresql://ai_chat:change-me@postgres:5432/ai_chat
APP_PORT=8000
POSTGRES_DB=ai_chat
POSTGRES_USER=ai_chat
POSTGRES_PASSWORD=change-me
POSTGRES_PORT=5432
```

### 2. 启动服务

```powershell
docker compose up -d --build
```

默认会启动两个服务：

- `app`
- `postgres`

编排文件见 [docker-compose.yml](./docker-compose.yml)。

### 3. 首次登录

首次启动后，系统会自动初始化数据库表结构，并按 `.env` 中的 bootstrap 配置创建默认管理员。

默认管理员配置来自：

```env
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=admin123
```

启动后访问：

```text
http://127.0.0.1:8000/
```

## 部署方式二：SQLite 文件模式

如果你不想单独运行数据库服务，可以使用 SQLite 文件模式。

`.env` 中配置如下：

```env
DATABASE_URL=sqlite:///data/chat.db
```

数据库文件默认位置：

- [data/chat.db](./data/chat.db)

### 本地运行

建议先创建虚拟环境并安装依赖：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

然后启动：

```powershell
py -3.13 main.py
```

## 配置规则

系统把配置分成两类。

### 1. 启动期配置

这类配置放在 `.env` 中：

- `DATABASE_URL`
- `SECRET_KEY`
- `BOOTSTRAP_ADMIN_USERNAME`
- `BOOTSTRAP_ADMIN_PASSWORD`
- `BOOTSTRAP_SYSTEM_API_BASE`
- `BOOTSTRAP_SYSTEM_API_KEY`
- `BOOTSTRAP_SYSTEM_MODEL`

### 2. 运行期配置

这类配置主要存到数据库中：

- 系统 API Base
- 系统 API Key
- 系统默认模型
- 模型展示名称映射
- 用户模型配置

也就是说：

- `.env` 负责启动和首次初始化
- 数据库负责运行中的业务配置

## `.env.example` 说明

示例配置文件见：

- [.env.example](./.env.example)

其中包含：

- SQLite 模式示例
- PostgreSQL 模式示例
- Docker 端口配置
- 默认管理员 bootstrap 配置

## 部署注意事项

正式部署前，建议先检查安全相关配置，例如 `SECRET_KEY`、管理员密码、API Key，以及 `.env` 与本地数据库文件的管理方式。

## 常用命令

### Docker 启动

```powershell
docker compose up -d --build
```

### Docker 停止

```powershell
docker compose down
```

### Docker 连同数据库卷一起清理

```powershell
docker compose down -v
```
