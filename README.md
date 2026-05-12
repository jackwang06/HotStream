# HotStream

热点话题抓取项目。当前阶段只做最小产品原型，不堆功能。

## 当前原型只保留 2 个核心功能

1. 抓取今日头条、小红书、知乎实时热点
2. 基于选中的热点生成文案

说明：今日头条、知乎已接入热点接口；小红书当前使用公开 Explore 页面的推荐高互动笔记作为热点来源；文案生成已接入 DeepSeek，生成后可在页面直接下载 TXT。

## 启动项目

在项目根目录运行：

```bash
uv run python main.py
```

然后打开：

```text
http://127.0.0.1:5173
```

页面会在进入时自动抓取默认来源热点，并且每 60 秒刷新一次。也可以在下拉框切换今日头条、小红书、知乎，或点击刷新按钮手动刷新。

## DeepSeek 配置

项目会自动读取根目录 `.env` 文件：

```text
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_MODEL=deepseek-chat
```

`.env` 已加入 `.gitignore`，不要提交到代码仓库。

## API

```text
GET /api/hot-topics?source=toutiao&limit=20
GET /api/hot-topics?source=xiaohongshu&limit=20
GET /api/hot-topics?source=zhihu&limit=20
GET /api/toutiao-hot?limit=20  # 兼容旧接口
POST /api/generate-copy
```

返回字段：

- success: 是否成功
- source: 数据源名称
- source_key: 数据源标识，支持 toutiao / xiaohongshu / zhihu
- updated_at: 更新时间
- topics: 热点列表
  - rank: 排名
  - title: 标题
  - url: 原始链接
  - hot_value: 热度值/赞数
  - label: 标签/摘要
  - source: 来源

## 测试

```bash
uv run pytest -q
```
