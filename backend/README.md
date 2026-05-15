# 智囊团后端

FastAPI 后端，负责人物库读取、推荐、检索、对话生成与数据导入。

## 目录结构

```text
backend/
├── app/
│   ├── api/          # 路由入口
│   ├── core/         # 配置、Prompt
│   ├── db/           # SQLAlchemy 模型与数据库会话
│   ├── schemas/      # Pydantic 请求/响应模型
│   ├── services/     # 推荐、检索、LLM、导入逻辑
│   ├── tasks/        # 命令行任务
│   └── main.py       # FastAPI 启动入口
├── data/             # 本地 SQLite 数据库目录
├── requirements.txt
└── .env.example
```

## 功能概览

- 人物列表与人物详情接口
- 基于人物画像的 Prompt 组装
- 按人物检索知识片段的轻量 RAG
- DeepSeek 聊天接口集成
- 单人智囊回答与多人群体智囊回答
- 从 `data/people_dataset_v1.json` 导入数据库

## 快速启动

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

启动后默认地址：

- `http://127.0.0.1:8000`
- 文档：`http://127.0.0.1:8000/docs`

## 环境变量

参考文件：

- `backend/.env.example`

关键变量：

- `APP_NAME`
- `DEBUG`
- `CORS_ORIGINS`
- `DATABASE_URL`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`
- `DEEPSEEK_API_KEY`
- `MAX_CONTEXT_CHUNKS`
- `RECOMMENDATION_TOP_K`

说明：

- `DEEPSEEK_API_KEY` 为空时，聊天类接口无法正常调用模型
- `DATABASE_URL` 默认指向本地 SQLite：`backend/data/app.db`

## 常用命令

### 启动服务

```bash
uvicorn app.main:app --reload --port 8000
```

### 强制重建并导入人物库

```bash
python -m app.tasks.import_people_data --force-rebuild
```

## API 概览

### 基础接口

- `GET /api/health`
- `GET /api/people`
- `GET /api/people/{slug}`

### 推荐与对话

- `POST /api/recommend`
- `POST /api/chat/respond`
- `POST /api/chat/group`

## 关键实现位置

推荐逻辑：

- `backend/app/services/recommend.py`

聊天逻辑：

- `backend/app/services/chat.py`
- `backend/app/services/llm.py`

检索逻辑：

- `backend/app/services/retrieval.py`

配置：

- `backend/app/core/config.py`
- `backend/app/core/prompts.py`

数据库：

- `backend/app/db/models.py`
- `backend/app/db/session.py`

## 与前端联调

前端本地静态服务通常运行在：

- `http://127.0.0.1:8125`
- `http://127.0.0.1:8126`

当前默认 CORS 已兼容上述端口。

如需前后端联调，根目录再启动一个静态服务器：

```bash
cd ..
python3 -m http.server 8126
```

然后访问：

- `http://127.0.0.1:8126/?mode=api`
