# 苏格拉底请回答 `zhinang-tuan`

一个以“历史/文学/商业/艺术/科学人物作为顾问”的对话式网页项目。

当前仓库默认走完整链路：前端接 FastAPI，由 MiniMax 根据问题推荐人物并生成回答。`?mode=adjust` 仍可用于人物调图工作台。

## 项目结构

```text
zhinang-tuan/
├── index.html                    # 单文件前端主页面（首页 + 洗牌 + 卡牌结果页）
├── assets/
│   ├── character_cutouts/        # 首页与卡牌使用的人物抠图素材
│   ├── portraits/                # 早期人像素材
│   ├── portraits-cut/            # 早期抠图结果
│   └── portraits-v3-cut/         # 分门类的人物素材原始目录
├── backend/
│   ├── app/                      # FastAPI 主体：接口、服务、数据库、Schema
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md                 # 后端单独说明
├── data/
│   ├── people_dataset_v1.json    # 人物主数据集
│   ├── people_dataset_cache.json # 数据处理缓存
│   ├── import/
│   │   └── people_import_structure.json
│   └── schemas/
│       └── persona_profile.schema.json
├── scripts/
│   └── build_people_dataset.py   # 数据整理脚本
└── .gitignore
```

## 当前工作模式

### 1. 调图工作台

人物卡牌和圆桌头像的可视化调图仍可用：

- `http://127.0.0.1:8126/?mode=adjust`

### 2. 完整版（前后端联动）

适合这些场景：

- 测真实推荐结果
- 测人物回答生成
- 验证 MiniMax 接口与后端逻辑

前端：

```bash
cd /Users/bytedance/Downloads/ui1/zhinang-tuan
python3 -m http.server 8126
```

后端：

```bash
cd /Users/bytedance/Downloads/ui1/zhinang-tuan/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

打开：

- `http://127.0.0.1:8126/`

说明：

- 前端会请求 `http://127.0.0.1:8000/api`
- CORS 已为 `8125` / `8126` 本地静态服务端口预留

## 前端说明

前端目前集中在一个文件：

- `index.html`

这个文件包含：

- 首页黑底海报式布局
- 输入框与发送逻辑
- 预览模式 / API 模式切换
- 洗牌 loading 动画
- 卡牌正面海报布局
- 卡牌散开 / 翻面 / 翻回 / 背面滚动
- 首页人物与签名的固定布局参数

与页面调试相关的关键常量：

- `DEFAULT_APP_MODE`
- `PREVIEW_CARD_MODE`
- `HOME_FIGURE_ADJUSTMENTS`
- `HOME_SIGNATURE_ADJUSTMENTS`
- `DEFAULT_BACK_QUOTE_ADJUSTMENT`

## 后端说明

后端位于：

- `backend/app`

主要分层：

- `api/routers/`：接口入口
- `services/`：推荐、检索、聊天等业务逻辑
- `db/`：数据库连接与模型
- `schemas/`：请求/响应结构
- `core/`：配置与 Prompt 组装
- `tasks/`：数据导入命令

常用接口：

- `GET /api/health`
- `GET /api/people`
- `GET /api/people/{slug}`
- `POST /api/recommend`
- `POST /api/chat/respond`
- `POST /api/chat/group`
- `POST /api/agent/open` / `POST /api/agent/ask` / `POST /api/agent/close`

## MR 眼镜智能体（DeepSeek）

悬浮球由 MR 端自己做。后端只负责：点一下开机、问答、再点一下关机。

本地对照页（网页悬浮球，逻辑和眼镜侧一样）：

- `http://127.0.0.1:8000/agent`

MR 端按这个顺序接：

1. 点击悬浮球启动：`POST /api/agent/open`
2. 用户说话/打字后提问：`POST /api/agent/ask`，body 为 `{ "session_id", "question" }`
3. 需要边生成边播报时改用：`POST /api/agent/ask/stream`
4. 再点悬浮球关闭：`POST /api/agent/close`，body 为 `{ "session_id" }`

改人设只动这一处：

- `backend/app/core/agent_prompt.py`

DeepSeek 的 key 写在本地 `backend/.env` 的 `DEEPSEEK_API_KEY`，不要提交到 git。

## 数据与素材说明

### 数据

- `data/people_dataset_v1.json`
  - 当前人物库的主数据源
- `data/schemas/persona_profile.schema.json`
  - 人物画像 JSON Schema
- `data/import/people_import_structure.json`
  - 人物导入结构定义

### 素材

- `assets/character_cutouts/`
  - 当前页面实际使用的人物抠图
- `assets/portraits-v3-cut/`
  - 分门类保留的人物原始整理素材

## 开发建议

### 改首页与卡牌 UI

优先改：

- `index.html`

### 改推荐与聊天逻辑

优先改：

- `backend/app/services/recommend.py`
- `backend/app/services/chat.py`
- `backend/app/core/prompts.py`

### 改人物库与导入

优先改：

- `data/people_dataset_v1.json`
- `data/import/people_import_structure.json`
- `backend/app/services/importer.py`
- `backend/app/tasks/import_people_data.py`

## 仓库整理约定

为了保持仓库干净，以下内容不进入版本库：

- 本地调试日志：`.dbg/`
- 临时调试文档：`debug-card-flip-bug.md`
- 抠图预览产物：`assets/_cutout_previews/`
- 人物备份图：`assets/character_cutouts/*-backup.png`
- 本地数据库文件：`backend/data/*.db*`

## 推荐启动顺序

### 只看页面

```bash
cd /Users/bytedance/Downloads/ui1/zhinang-tuan
python3 -m http.server 8126
```

打开：

- `http://127.0.0.1:8126/`

### 看完整链路

先启动后端，再启动静态前端：

```bash
cd /Users/bytedance/Downloads/ui1/zhinang-tuan/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

```bash
cd /Users/bytedance/Downloads/ui1/zhinang-tuan
python3 -m http.server 8126
```

打开：

- `http://127.0.0.1:8126/`

## Published English UI preview

- Website: https://evenna.github.io/zhinang-tuan/app/
- User stories: https://evenna.github.io/zhinang-tuan/app/?view=stories

The GitHub Pages preview includes the English advisor catalog, sample card deck,
interactive story community, animated statistics, and the one-screen desktop layout.
It uses public profile snapshots and illustrative stories. Live AI replies still
require the FastAPI backend and server-side API credentials; secrets are never exported.
Existing project materials at `/docs/index.html` are preserved.

Rebuild the preview from the local catalog after editing the app:

```bash
backend/.venv/bin/python -m pip install -r scripts/preview-requirements.txt
backend/.venv/bin/python scripts/build_public_preview.py
```

The export writes `docs/app/` and creates optimized WebP copies of illustrations.
