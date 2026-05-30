# HotStream · 前山如画，四季成歌

> 热点到文案，三秒生成。为前山牧场四季牧歌民俗风情园做文旅借势营销。

HotStream 是一款文旅热点借势营销工具。它自动抓取多平台实时热点，通过 DeepSeek 生成可直接发布的中文推文，并支持 B站视频的 Qwen2.5-VL 多模态分析。所有生成内容自动绑定景点画像，确保推文不偏离宣传目标。

---

## 功能总览

### 多源热点抓取
- **今日头条** — 实时热榜，按热度排序
- **知乎** — 实时热榜
- **小红书** — Explore 推荐
- **B站视频** — 热门视频、关键词搜索、分区排行榜（按播放量降序）

### B站视频分析
- 支持分区筛选：出行/旅行、生活、美食、知识、娱乐
- 通过 Qwen2.5-VL（DashScope 兼容 API）分析视频封面与元数据
- 分析结果：内容概述、画面场景、受众情绪、可借势点、风险提示

### AI 文案生成
- 基于 DeepSeek API 生成可直接发布的推文
- 自动注入「前山牧场四季牧歌民俗风情园」景点画像
- 硬性约束：不编造价格/活动/交通/游客评价，不声称视频拍摄地即前山牧场
- 支持自定义全局提示词和本次提示词

### 文案编辑与导出
- **编辑页**：标题、正文块（可拖拽排序）、图片素材区
- **发布预览**：小红书/公众号/通用三种平台预设
- **导出长图**：Canvas 渲染，直接导出社交平台长图

### 数据库持久化
- **用户设置**：DeepSeek / Qwen API Key、全局提示词自动保存
- **草稿管理**：创建、编辑、删除草稿，跨页面传递
- **历史记录**：每次生成自动记录主题、文案、来源

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+, stdlib `http.server` |
| 数据库 | PostgreSQL 17.9 (psycopg2) |
| 前端 | 原生 HTML/CSS/JS（无框架） |
| 部署 | Vercel（serverless）+ Docker（计划中） |
| 测试 | pytest（92 个测试） |
| 包管理 | uv |

---

## 项目结构

```text
HotStream/
├── main.py                          # 入口
├── pyproject.toml                   # uv 项目配置
├── .env                             # 数据库凭据（gitignored）
├── hotstream/                       # 后端包
│   ├── server.py                    # HTTP 路由 + API 构建函数
│   ├── scraper.py                   # 多源热点抓取（头条/知乎/小红书/B站）
│   ├── copywriter.py                # DeepSeek 提示词构建 + 文案生成
│   ├── video_analyzer.py            # Qwen2.5-VL 视频分析
│   ├── scenic_profile.py            # 景点画像加载
│   ├── db.py                        # PostgreSQL 连接 + 三表 CRUD
│   └── image_scraper.py             # 相关图片抓取
├── ui/                              # 前端
│   ├── index.html                   # 首页（抓取 → 生成）
│   └── editor.html                  # 编辑页（编辑 → 预览 → 导出）
├── tests/                           # 测试（92 个）
│   ├── test_db.py                   # 数据库模块 16 个测试
│   ├── test_db_api.py               # 持久化 API 10 个测试
│   ├── test_bilibili_scraper.py     # B站抓取
│   ├── test_bilibili_server.py      # B站服务端
│   ├── test_video_analyzer.py       # Qwen 视频分析
│   ├── test_scenic_profile.py       # 景点画像
│   ├── test_copywriter.py           # 提示词构建
│   ├── test_copy_api.py             # 生成 API
│   ├── test_editor_page.py          # 页面静态检查
│   ├── test_server.py               # 服务端路由
│   ├── test_scraper.py              # 头条抓取
│   ├── test_multi_source_scraper.py # 多源调度
│   ├── test_image_scraper.py        # 图片抓取
│   └── test_image_proxy.py          # 图片代理
├── scenic_profiles/                 # 景点画像
│   └── qianshan-siji-muge/
│       ├── overview.md              # 景点总览
│       ├── advantages.md            # 资源优势
│       ├── nearby-attractions.md    # 周边景点
│       └── writing-rules.md         # 借势写作规则
├── api/                             # Vercel serverless 入口
│   └── index.py
└── vercel.json                      # Vercel 部署配置
```

---

## API 参考

所有响应格式：`{"success": true|false, ...}`

### 热点

```http
GET /api/hot-topics?source=toutiao&limit=20
GET /api/hot-topics?source=bilibili&limit=20&sort=traffic_desc
GET /api/hot-topics?source=bilibili&keyword=草原&category=travel&sort=traffic_desc
```

### 文案

```http
POST /api/generate-copy
Content-Type: application/json

{
  "topic": {...},
  "api_key": "sk-...",
  "global_prompt": "...",
  "temporary_prompt": "...",
  "qwen_analysis": {...}
}
```

### 视频分析

```http
POST /api/analyze-video
Content-Type: application/json

{
  "topic": {"title": "...", "cover": "...", "bvid": "..."},
  "api_key": "sk-..."
}
```

### 提示词

```http
POST /api/prompts
Content-Type: application/json

{"topic": {"title": "..."}}
```

### 持久化

```http
GET  /api/settings         # 加载设置
POST /api/settings         # 保存设置
GET  /api/drafts           # 草稿列表
GET  /api/drafts/<id>      # 单个草稿
POST /api/drafts           # 创建草稿
PUT  /api/drafts/<id>      # 更新草稿
DELETE /api/drafts/<id>    # 删除草稿
GET  /api/history          # 历史记录
POST /api/history          # 记录生成历史
```

---

## 数据库

PostgreSQL 17.9，schema `wangyafei`。

### settings

| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 固定为 1（单行） |
| deepseek_api_key | TEXT | DeepSeek API Key |
| qwen_api_key | TEXT | Qwen2.5-VL API Key |
| global_prompt | TEXT | 全局提示词 |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### drafts

| 列 | 类型 | 说明 |
|---|---|---|
| id | SERIAL PK | |
| title | TEXT | 标题 |
| content_blocks | JSONB | 正文块数组 |
| images | JSONB | 图片 URL 数组 |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### history

| 列 | 类型 | 说明 |
|---|---|---|
| id | SERIAL PK | |
| topic_title | TEXT | 热点标题 |
| copy_text | TEXT | 生成文案 |
| hot_value | TEXT | 热度值 |
| source | TEXT | 来源平台 |
| chars | INTEGER | 文案字数 |
| created_at | TIMESTAMPTZ | |

---

## 快速开始

### 前置要求

- Python >= 3.11
- uv 包管理器
- PostgreSQL 数据库（配置见 `.env`）

### 安装

```bash
cd HotStream
uv sync
```

### 配置

```bash
# 创建 .env（已 gitignored）
cp .env.example .env   # 或手动创建
```

`.env` 内容：

```env
DB_HOST=218.84.152.14
DB_PORT=65006
DB_NAME=wangyafei
DB_USER=wangyafei
DB_PASSWORD=***
DB_SCHEMA=wangyafei
```

### 运行

```bash
uv run python main.py
# → http://127.0.0.1:5173
```

首次启动会自动创建数据库表。

### 测试

```bash
uv run pytest -q
# 92 passed
```

---

## 部署

### Vercel（当前生产）

项目已配置 Vercel serverless 部署：

- 入口：`api/index.py`（Python `BaseHTTPRequestHandler`）
- 配置：`vercel.json`（重写路由 + 静态文件服务）
- 生产地址：<https://hot-stream.vercel.app>
- Git 推送 `main` 分支自动触发部署

### Docker（规划中）

最终交付形式为 Next.js + Docker 容器镜像。当前后端改用 Python stdlib server，后续会迁移到 Next.js API routes，并用 `Dockerfile` 打包：

```dockerfile
FROM node:22-alpine
# ... Next.js standalone build
```

---

## 版本

| 版本 | 提交 | 说明 |
|---|---|---|
| v3.0 | `f748cc7` | 主标题改"前山如画，四季成歌"；B站出行分类修复；编辑/预览高度对齐 |
| 2.0 | `870d458` | 初始版本，多源热点抓取 + DeepSeek 文案生成 |

当前开发分支：`epic/user-system`（对应 worktree `.worktrees/user-system`）

---

## 开发约定

- **TDD**：先写测试，确认红灯，再写最小实现
- **分支管理**：`main` = 生产，`develop` = 开发主线，`epic/<name>` = 大功能 worktree 分支
- **无框架前端**：原生 HTML/CSS/JS，零构建步骤
- **景点画像**：生成文案自动注入 `scenic_profiles/qianshan-siji-muge/` 内容
- **安全**：API keys 和数据库密码仅存在于 `.env`（gitignored），不写入仓库
