# HotStream 开发进度说明（pleasereadme）

> 本文档详述 **HotStream** 项目截至当前的开发进度、架构、功能清单、版本演进、部署形态与待办。
> 最后更新对应提交：**`f0d7850`**（分支 `feat/user-login-nextjs`）。测试状态：**406 passed**。

---

## 1. 项目简介

**HotStream** 是给「**前山牧场四季牧歌民俗风情园**」做**文旅借势营销**的工具。核心链路：

> 抓取全网热点 → （可选）分析视频内容 → DeepSeek 结合「景点画像 + 知识库」生成推文 → 所见即所得编辑器排版 → 导出长图发布。

定位：运营人员每天**借势热点**快速产出契合景区调性的营销文案与配图。

---

## 2. 技术架构

里程碑式从「单文件 Python 站」演进为「**Next.js 前端 + Python 无状态后端 + PostgreSQL**」三层：

```
浏览器 ──同源──> Next.js 15 (web/, 端口 3000)
                  ├─ 鉴权/会话、用户管理、登录页、设置/预设/知识库页（React/SSR）
                  ├─ /api/auth /api/users /api/settings /api/drafts /api/history
                  │    /api/presets /api/knowledge          （Next 自有，按 user_id 隔离，pg 直连）
                  ├─ /api/hot-topics /api/curated-topics /api/generate-copy
                  │    /api/analyze-video /api/ai-assist /api/custom-source
                  │    /api/proxy-image /api/prompts ...      （Next 鉴权后代理 → Python，服务端注入 Key）
                  └─ 受鉴权地返回旧版静态页 web/legacy/{index,editor}.html
                                   │ PYTHON_API_BASE=http://127.0.0.1:5173
                                   ▼
                  Python http.server (hotstream/, 端口 5173) — 无状态抓取/AI 服务，不连库
                                   │
PostgreSQL 17 (schema=wangyafei) <── 仅 Next.js 连接
```

**技术选型**：Next.js 15 App Router + TS（`output:standalone`）；会话用 DB 不透明 token 表；密码 `crypto.scrypt`；`pg` 直连（search_path 锁定）；`zod` 校验。**刻意零重型依赖**（不用 Prisma/bcrypt/JWT）。
**AI**：DeepSeek（OpenAI 兼容）出文案；Qwen-VL（DashScope `qwen-vl-max`）读封面图/图片。
**前端编辑器**：纯原生 + 内置 `marked`/`turndown`/`html2canvas`（`web/public/vendor/`），无构建依赖。

---

## 3. 后端模块（`hotstream/`）

| 模块 | 职责 |
|---|---|
| `server.py` | http.server 主入口；所有 `/api/*` 的 builder（hot-topics / curated / generate-copy / analyze-video / ai-assist / custom-source / settings/drafts/history…）+ 热点 TTL 缓存 |
| `scraper.py` | 多源抓取（头条/知乎/小红书/B站/抖音）+ 8 类关键词分类筛选 + 类别 tag 派生 |
| `copywriter.py` | DeepSeek 文案生成、AI 帮写、精选热点智选、视频全貌还原、提示词体系（默认提示词/代理灵魂/Markdown/政治脱敏指令） |
| `video_analyzer.py` | Qwen-VL 分析视频**封面图**+标题/简介/流量（非真实视频帧）；图片分析（AI帮写改写用） |
| `web_search.py` | 百度/头条/知乎并发联网检索（供「视频内容还原」拼凑碎片，best-effort） |
| `political_filter.py` | 政治脱敏词库（~180 无歧义政治词）+ 涉政热点过滤 |
| `image_scraper.py` | 相关配图抓取、自定义链接元信息抓取 |
| `scenic_profile.py` | 景点画像（注入生成提示，约束"不编造未确认事实"） |
| `db.py` | （旧版单租户持久化的 SQL 形态参考；现持久化已由 Next 接管） |

**API 路由（`web/app/api/`）**：`auth` `users` `settings` `drafts` `history` `presets` `knowledge` `prompts` `prompt-defaults` `hot-topics` `curated-topics` `generate-copy` `analyze-video` `ai-assist` `custom-source` `proxy-image`。

---

## 4. 当前功能清单（按领域）

### 用户系统（里程碑 1）
- 多用户登录、DB 会话、管理员建号/停用/改角色/重置密码（邀请制，不开放注册）。
- **每用户数据隔离**：API Key、代理灵魂、默认提示词、草稿、历史，按 `user_id` 互不可见。
- API Key 服务端注入、掩码读取，绝不下发明文到浏览器。

### 数据源与热点
- **5 个源**：今日头条、知乎、小红书、B站、抖音；外加**自定义链接**（粘贴 URL → 抓元信息/检测视频）。
- **统一分类筛选**（8 类：出行/美食/乡村·三农/文化·民俗/生活/娱乐/知识/科技）+ **可配置条数**（1–100，默认 30）。
- **类别 tag**：每条热点显示类别小标签，并作为生成的切入角度参考。
- **精选热点**：聚合五源 → DeepSeek 按「知识库 + 景点画像」精选最契合借势的热点，标注来源+理由。
- **热点 TTL 缓存**：进程内 60s（`HOT_TOPICS_CACHE_TTL` 可调），线程安全+深拷贝隔离，减源站请求。
- **政治脱敏开关**：开启后所有源（含精选）涉政热点不刷出，生成/AI帮写全程不涉政。

### 视频分析（诚实边界：分析的是**封面图+元信息**，非真实视频帧）
- B站/抖音/自定义视频可「分析视频」：Qwen-VL 看封面 → 概况。
- **视频内容推断**：概况 → 并发联网检索（百度/头条/知乎）→ DeepSeek 综合还原"视频大概在讲什么"（标注为*推断*）→ **可编辑文本**，用户改写后逐字进生成。
- 视频类精选条目支持**可选**分析（不强制，避免死锁）。

### 文案生成与编辑器
- DeepSeek 生成 **Markdown** 推文（景点画像 + 知识库 + 视频分析 + 本次提示词 + 代理灵魂）。
- **所见即所得编辑器**（`editor.html`）：标题级别/粗斜体/下划线/颜色/字体、格式刷、最近 5 色、拖拽移动图片、分页符、撤销/恢复（Ctrl+Z/Y，30 步）、html2canvas **导出长图**（按分页符切多张）。
- **AI 帮写**：扩写/缩写/改写/补充；改写可基于所选图片（Qwen 分析）；流式进度（NDJSON）；预览后接受（原 vs AI 对比）；风格取当前代理灵魂；**已纳入政治脱敏**。

### 提示词体系
- **代理灵魂**多预设（默认/可爱/庄重/活泼，可增删选用）= system 人设。
- **默认提示词**多预设（仿草稿页管理）= 每次生成的任务模板起点。
- **知识库**（全局共享，启用项注入；当前为**全量注入 + 8000 字封顶**，非 RAG）。

---

## 5. 版本演进时间线（自 git 历史）

| 阶段 | 提交/版本 | 内容 |
|---|---|---|
| 初始 | `b6a6036`→`870d458` | 2.0：初版抓取+生成 |
| 3.x | `f748cc7` `5be3369` `57a4dff` | 3.0：PostgreSQL 持久化（settings/drafts/history）；3.1 |
| **里程碑1** | `dcb9387` | **v3.3：多用户登录 + Next.js 迁移 + UI 改版 + 草稿/设置改造** |
| 4.0 | `cb679ea` | 知识库 + 白天模式/登录背景 + 提示词体系重构（代理灵魂/默认提示词）+ 首页化简 |
| 4.1–4.3 | `8902878` `32f0738` `4f4e07a` `30efb58` | 默认提示词多预设；抖音源+「设置」改名+齿轮；统一分类筛选+可配置条数+自定义链接；条数实抓优化 |
| 编辑器 | `4642e5f` `b1431e5` `0d43850` | Markdown + WYSIWYG；两栏+分页符+格式刷；代理灵魂多预设 + 撤销恢复 |
| AI帮写 | `2e00fce` `0d67e6b` | 扩/缩/改写（含图片分析）；流式进度+预览接受+补充模式 |
| 精选热点 | `59a1c6c` `2aceb02` `46ecad2` | 精选热点；修复 B站/抖音 精选视频门控死锁；视频类精选可选分析 |
| 视频/缓存 | `476d10b` | 视频内容推断（联网检索+DeepSeek还原+可编辑）+ 热点 TTL 缓存 |
| 政治脱敏 | `2dfe547` | 政治脱敏开关（词库过滤 + 文案/AI帮写不涉政） |
| **当前** | **`f0d7850`** | **热点类别 tag 显示 + 结合生成** |

---

## 6. 部署形态

| 目标 | 说明 |
|---|---|
| **wangy**（原生，验收/开发） | `/home/wangy/getpaper/HotStream`；原生 `next start -p 3000` + `python main.py :5173`。改 `.py` 重启 python；改 `web/`（含 legacy HTML / 路由）需 `npm run build` + 重启 node。**访问完整应用走 `:3000`（不是 `:5173`，后者只是无登录的裸后端）**。 |
| **甲方 docker**（预览） | 本机 `docker compose up -d --build`（web + scraper 两容器）；经 `cloudflared` 快速隧道暴露给甲方（trycloudflare URL 临时、重启会变）。 |
| **git** | 仓库在 wangy（SSH remote）；流程：本机改码 → rsync 到 wangy → 在 wangy `git commit && push`。分支 `feat/user-login-nextjs`。共享同一 PostgreSQL，迁移幂等跑一次两处生效。 |

---

## 7. 测试

- **406 passed**（pytest）。覆盖：抓取/分类/分页、多源、视频分析与推断、AI帮写、精选热点、TTL 缓存、政治脱敏（含词库实测零误杀漏判）、类别 tag、编辑器静态契约、用户/设置/草稿/历史隔离等。
- 关键功能多以 **Playwright 真机 E2E** + 多 agent 对抗式审查（Workflow）核实后才上线。

---

## 8. 已知限制与待办（Roadmap）

**已知限制（诚实标注）**
- **小红书**匿名 explore 已不再下发笔记数据（需登录态+签名 homefeed API），匿名抓取返回 0 条——代码已修正不再产出错链，但拿不到数据。
- **视频"分析"**是封面图+元信息推断，**非真实视频帧理解**（真分帧太烧 token，刻意取舍）。
- **政治脱敏词库保守**（剔除裸"外交部/制裁/战争/新疆/西藏/县长推介"等以免误杀文旅），边缘政治内容可能漏判；生成侧有强提示兜底。
- **知识库非 RAG**：当前全量注入 + 8000 字封顶截断；文档过多会被截断 → 精选可能漏选。

**待办 / 规划**
1. **知识库自动摘要 + RAG**（甲方已提出顾虑）：**筛选用蒸馏全局摘要（防漏选）+ 生成用 RAG 按需召回（保准确）**；KB 变大时落地，可先做"自动摘要"提前解决精选漏选。
2. 政治脱敏审查留的 3 个 minor 加固（generate 路由字段白名单、自定义链接词库硬过滤、政治约束作独立高优 system 消息）。
3. cloudflared 快速隧道 → **命名隧道 + 域名 + systemd 自启**（地址永久固定）。
4. （里程碑 3）把 Python 抓取/AI 逻辑移植到 TS，收敛为单一 Next.js 镜像，去掉 Python 服务。

---

## 9. 本地开发速记

```bash
# 后端（无状态抓取/AI）
PORT=5173 uv run python main.py
# 前端（完整应用，连后端 + DB）
cd web && npm run build && PORT=3000 npx next start -p 3000
# 浏览器开 http://localhost:3000，用自己的账号登录
# 测试
uv run pytest -q
```

> 注：`web/.env.local`（DB/ADMIN/COOKIE_SECURE/PYTHON_API_BASE）与根 `.env`（python DB）为本地密钥，已 gitignore，不入库。
