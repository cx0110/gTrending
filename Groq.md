这份指南将详细说明如何将你的 Python 项目（GitHub Trending / OSSInsight）配置为使用 **Groq**。

Groq 是目前最推荐的替代方案，因为它**兼容 OpenAI SDK**（意味着你几乎不用改代码），**速度极快**（LPU 芯片），且目前**完全免费**。

-----

# 🚀 Groq 接入配置指南

本指南适用于任何基于 `openai` Python 库开发，但希望切换到 Groq 免费模型的项目。

## 第一步：获取 API Key 🔑

1.  **注册账号**

      * 访问 Groq 控制台：[https://console.groq.com/keys](https://console.groq.com/keys)
      * 使用 Google 或 GitHub 账号直接登录。

2.  **创建密钥**

      * 点击页面中间的 **"Create API Key"** 按钮。
      * 给 Key 起个名字（例如 `Github-Trending-Bot`）。
      * **立即复制** 生成的字符串（以 `gsk_` 开头）。
      * *注意：这个 Key 只显示一次，丢失后需重新生成。*

-----

## 第二步：配置 GitHub Actions (云端运行) ☁️

为了让你的自动脚本在 GitHub 上运行时能调用 Groq，需要设置仓库的 Secrets。

1.  进入你的 GitHub 仓库页面。
2.  点击顶部导航栏的 **Settings (设置)**。
3.  在左侧侧边栏找到 **Secrets and variables** -\> 点击 **Actions**。
4.  在 **Repository secrets** 区域，添加以下两个密钥：

| Secret Name (名称) | Secret Value (值) | 说明 |
| :--- | :--- | :--- |
| `OPENAI_API_KEY` | `gsk_xxxx...` | 填入你在第一步获取的 Groq Key |
| `OPENAI_BASE_URL` | `https://api.groq.com/openai/v1` | **关键！** 告诉代码去连 Groq 而不是 OpenAI |

5.  在 **Repository variables** (就在 Secrets 旁边) 或 Secrets 中添加开关：

| Name | Value | 说明 |
| :--- | :--- | :--- |
| `ENABLE_LLM` | `true` | 开启 AI 功能 |

-----

## 第三步：修改项目配置 (`config.yaml`) ⚙️

你需要告诉你的程序使用哪个 Groq 模型。Groq 不支持 `gpt-3.5` 或 `gpt-4` 这样的名字，必须使用它自有的模型名。

打开你的 `config.yaml`，修改 `settings` 部分：

```yaml
settings:
  enable_llm: false  # 本地调试可设为 true，GitHub 上由环境变量控制
  
  # === 关键修改 ===
  # Groq 的模型名称 (推荐 Llama 3.3 或 3.1，中文能力强且免费)
  ai_model: "llama-3.3-70b-versatile"
  
  # 其他配置保持不变
  top_list_limit: 10
  history_file: "data/history.db"
  # ...
```

**✅ 推荐模型列表 (截至 2025 年):**

  * **推荐**: `llama-3.3-70b-versatile` (性能最强，媲美 GPT-4，处理中文极佳)
  * 备选: `llama-3.1-8b-instant` (速度最快，适合简单任务)
  * 备选: `mixtral-8x7b-32768` (Mistral 的模型，逻辑性不错)

-----

## 第四步：代码适配检查 (Python) 🐍

确保你的 `main.py` 正确读取了环境变量和配置。如果你使用的是我之前提供的最新代码，这部分**已经适配好了**。

核心逻辑回顾（无需修改，仅供理解）：

```python
# 初始化时，优先读取环境变量中的 BASE_URL
# 如果 GitHub Secrets 配置了 OPENAI_BASE_URL，这里会自动生效
if settings['enable_llm']:
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL") # 这里会读到 api.groq.com...
    
    if api_key:
        # OpenAI SDK 允许指向自定义 Base URL
        llm_client = OpenAI(api_key=api_key, base_url=base_url)

# 调用时，传入 config.yaml 中指定的模型名
response = client.chat.completions.create(
    model=settings.get('ai_model', 'llama-3.3-70b-versatile'), # 必须用 Groq 的模型名
    # ...
)
```

-----

## 第五步：本地测试 (可选) 💻

如果你想在把代码推送到 GitHub 之前在本地电脑上测试：

**Mac / Linux:**

```bash
export OPENAI_API_KEY="gsk_你的密钥..."
export OPENAI_BASE_URL="https://api.groq.com/openai/v1"
export ENABLE_LLM="true"

python main.py
```

**Windows (PowerShell):**

```powershell
$env:OPENAI_API_KEY="gsk_你的密钥..."
$env:OPENAI_BASE_URL="https://api.groq.com/openai/v1"
$env:ENABLE_LLM="true"

python main.py
```

-----

## 常见问题 FAQ ❓

**Q1: Groq 有速率限制吗？**
A: 有，但对于每天运行一次的脚本来说，限额非常宽裕。

  * `llama-3.3-70b`: 每分钟限制 30 次请求 (RPM)。
  * 你的脚本如果不加 `time.sleep` 可能会触发限制。建议在代码循环中保留 `time.sleep(2)`。

**Q2: 报错 `model not found` 是怎么回事？**
A: 这通常是因为你还在用 `gpt-3.5-turbo` 这个名字。Groq 无法识别 OpenAI 的模型名。请确保 `config.yaml` 里的 `ai_model` 字段填的是 `llama-3.3-70b-versatile`。

**Q3: 生成的中文摘要有点奇怪？**
A: Llama 3 的中文能力很强，但偶尔会蹦出英文。可以在 `prompt` 中加强指令，例如：“请务必使用**中文**回答”。

按照这个文档配置，你的自动抓取机器人就可以实现 **0 成本 + 高速 AI 分析** 了！
