# AI Chat ✦

一个简约、强大且具有云端漫游功能的 AI 聊天系统。基于 FastAPI + PostgreSQL + Vanilla JS 构建。

## 核心特性
- **云端同步**：聊天记录实时持久化到 PostgreSQL，支持多设备无缝漫游。
- **智能标题**：AI 自动根据对话内容生成精准的小标题。
- **多模态支持**：支持图片上传、文件解析及代码高亮。
- **全量 Docker 化**：支持一键部署，包括数据库自托管。

## 🚀 快速部署 (Docker)

确保你的机器上已安装 `Docker` 和 `Docker Compose`。

1. **获取代码**
   ```bash
   git clone git@github.com:arctan303/chat.arctan.top.git
   cd chat.arctan.top
   ```

2. **配置环境变量**
   创建 `.env` 文件：
   ```bash
   DATABASE_URL=postgresql://ai_chat:ai_chat@db:5432/ai_chat
   SECRET_KEY=你的随机字符串
   ```

3. **一键启动**
   ```bash
   docker compose up -d
   ```
   启动后，访问 `http://localhost:8000` 即可开始聊天。默认管理员：`admin` / `admin123`。

## 🛠 本地开发

1. 安装依赖：`pip install -r requirements.txt`
2. 运行后端：`python main.py`

## 许可证
MIT License
