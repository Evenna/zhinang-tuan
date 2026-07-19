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
- TED 研读资料库：文本、PDF、Office 文档、网页与视频链接导入
- StepFun ASR 视频转写，以及 transcript 分段、主题、观点与金句整理
- 基于视频内容生成学习型 SpeakerCard
- 内置人物、SpeakerCard 与教练角色混合圆桌
- UserMemory、SessionSummary、偏好与事实提取、跨会话召回和阈值式记忆维护
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
- `STEPFUN_API_KEY`（只有自动视频转写需要）
- `STEPFUN_BASE_URL`
- `STEPFUN_ASR_MODEL`
- `FFMPEG_PATH`
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
- `POST /api/roundtable/respond`
- `GET|POST /api/study/sources`
- `POST /api/study/sources/import-file`
- `POST /api/study/sources/import-url`
- `POST /api/study/sources/import-video`
- `POST /api/study/speaker-cards/generate`
- `GET /api/study/speaker-cards`
- `POST /api/study/roundtable/respond`
- `GET /api/memory`
- `GET /api/memory/summaries/{conversation_id}`
- `DELETE /api/memory/{memory_id}`

自动转写视频前，请确保系统能执行 `ffmpeg`。视频页面链接由 `yt-dlp` 提取；直接媒体 URL 也可以使用。已有转写文本时可直接提交 `transcript`，无需配置 ASR。

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
