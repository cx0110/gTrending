# 📈 GitHub Trending 每日追踪

自动抓取 GitHub 官方热榜，由 AI 辅助生成中文摘要。

## 功能特性

### 🔄 双 AI API 负载均衡
- 支持 MiniMax 和 OpenAI 双 API
- 随机选择可用 API，失败自动切换
- 每个请求间隔 1.5 秒，防止 rate limit
- 响应结果标注模型来源：`🤖 [MiniMax-M2.7] 项目简介`

### 🏷 项目过滤规则
抓取时自动过滤低价值项目：
- **每日新增星** < 10：当天关注度低
- **总星数** < 500：可能是新项目或冷门项目
- **无描述项目**：跳过

> 被过滤项目不会调用 AI，不会写入数据库

### 📊 追踪分类
- 🔥 全球热榜 (General)
- 🐹 Go 语言热门
- 🐍 Python 热门
- 🟨 JavaScript/TypeScript 热门
- ☕ Java 热门
- 🦀 Rust 热门
- cpp C/C++ 热门
- 🔷 C# 热门
- 🎯 TypeScript 热门
- 💜 Vue 热门
- ⚛️ React 热门
- 🤖 AI/ML 热门 (中文项目)

### 💾 数据持久化
- SQLite 缓存 AI 摘要，已分析项目不重复调用
- 历史归档按日期存储

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `ENABLE_LLM` | 启用 AI 摘要 | `false` |
| `MINIMAX_API_KEY` | MiniMax API Key | - |
| `MINIMAX_BASE_URL` | MiniMax 端点 | `https://api.minimaxi.com/anthropic` |
| `LLM_MODEL` | MiniMax 模型 | `MiniMax-M2.7` |
| `OPENAI_API_KEY` | OpenAI API Key | - |
| `OPENAI_BASE_URL` | OpenAI 端点 | - |
| `AI_MODEL` | OpenAI 模型 | `gpt-3.5-turbo` |

## 配置文件

```yaml
settings:
  enable_llm: false
  top_list_limit: 10        # 每个分类抓取数量
  ai_model: "llama-3.3-70b-versatile"

  # 过滤规则
  filters:
    min_daily_stars: 10     # 每日新增星阈值
    min_total_stars: 500    # 总星数阈值
    skip_no_description: true

  archive_dir: "archives"
  readme_file: "README.md"
  readme_header: |
    # 📈 GitHub Trending 每日追踪
    自动抓取 GitHub 官方热榜，由 AI 辅助生成中文摘要。
    > 更新时间: {{ update_time }}

collections:
  - title: "🔥 全球热榜 (General)"
    url: "https://github.com/trending"
  # ...更多分类
```

## 更新日志

- **2026-04-08**: 添加双 API 随机负载均衡、模型标注、新增 10 个分类
- **2026-04-08**: 实现项目过滤规则（每日星数、总星数、描述过滤）

---

> 上次更新: {{ update_time }}
