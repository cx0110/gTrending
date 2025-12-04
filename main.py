import os
import json
import time
import datetime
import requests
from bs4 import BeautifulSoup

# LangChain 导入 (按需加载，避免未安装时报错)
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

# --- 配置部分 ---
CONFIG = {
    "urls": {
        "General": "https://github.com/trending",
        "Python": "https://github.com/trending/python",
        "Go": "https://github.com/trending/go"
    },
    "history_file": "data/history.json",
    "archive_dir": "archives",
    "readme_file": "README.md",
    "enable_llm": os.getenv("ENABLE_LLM", "false").lower() == "true",
    "openai_api_key": os.getenv("OPENAI_API_KEY"),
    "openai_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
}

# --- 数据结构 ---
# 简单的项目类
class Repo:
    def __init__(self, owner, name, description, lang, stars, url):
        self.owner = owner
        self.name = name
        self.full_name = f"{owner}/{name}"
        self.description = description
        self.lang = lang
        self.stars = stars
        self.url = url
        self.ai_summary = ""
        self.is_new = True # 默认为新项目

    def to_dict(self):
        return {
            "full_name": self.full_name,
            "description": self.description,
            "ai_summary": self.ai_summary,
            "url": self.url
        }

# --- 核心功能 ---

def load_history():
    """加载历史记录，用于去重和避免重复生成摘要"""
    if not os.path.exists(CONFIG["history_file"]):
        return {}
    with open(CONFIG["history_file"], 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return {}

def save_history(history):
    """保存历史记录"""
    os.makedirs(os.path.dirname(CONFIG["history_file"]), exist_ok=True)
    with open(CONFIG["history_file"], 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def scrape_github_trending(url):
    """抓取 GitHub Trending 页面"""
    print(f"正在抓取: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"抓取失败: {resp.status_code}")
            return []
    except Exception as e:
        print(f"请求异常: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    repos = []
    
    for article in soup.select('article.Box-row'):
        try:
            h2 = article.select_one('h2 a')
            if not h2: continue
            
            href = h2['href'] # /owner/repo
            parts = href.strip('/').split('/')
            if len(parts) < 2: continue
            
            owner, name = parts[0], parts[1]
            repo_url = f"https://github.com{href}"
            
            desc_tag = article.select_one('p.col-9')
            description = desc_tag.text.strip() if desc_tag else "无描述"
            
            lang_tag = article.select_one('span[itemprop="programmingLanguage"]')
            lang = lang_tag.text.strip() if lang_tag else "Unknown"
            
            # 获取 Stars (通常是第一个含有链接的 text)
            # 简化处理，不一定非常精确，但通常有效
            stats_div = article.select_one('div.f6.color-fg-muted.mt-2')
            stars = "N/A"
            if stats_div:
                star_link = stats_div.select_one('a[href$="/stargazers"]')
                if star_link:
                    stars = star_link.text.strip()

            repos.append(Repo(owner, name, description, lang, stars, repo_url))
        except Exception as e:
            print(f"解析单个项目出错: {e}")
            continue
            
    return repos

def generate_ai_summary(repo: Repo):
    """使用 LangChain 生成简报"""
    if not LANGCHAIN_AVAILABLE or not CONFIG["enable_llm"] or not CONFIG["openai_api_key"]:
        return "LLM 未启用或未配置 Key。"

    print(f"正在为 {repo.full_name} 生成 AI 简报...")
    
    try:
        llm = ChatOpenAI(
            api_key=CONFIG["openai_api_key"],
            base_url=CONFIG["openai_base_url"],
            model="gpt-3.5-turbo", # 或者 gpt-4
            temperature=0.3
        )

        prompt = ChatPromptTemplate.from_template(
            "你是一个技术专家。请用中文简要总结以下 GitHub 项目的功能和亮点。\n"
            "项目名称: {name}\n"
            "语言: {lang}\n"
            "原始描述: {desc}\n"
            "请用一句话概括核心功能，不要废话。"
        )

        chain = prompt | llm | StrOutputParser()
        summary = chain.invoke({"name": repo.name, "lang": repo.lang, "desc": repo.description})
        return summary
    except Exception as e:
        print(f"AI 生成失败: {e}")
        return "AI 生成失败，请查看原始描述。"

def update_readme_index(archive_files):
    """更新主 README 索引"""
    header = """# 📈 GitHub Trending 每日追踪

这个仓库通过 Github Action 每天自动抓取 GitHub Trending 热点。
包含 **General**, **Python**, **Go** 三个分类。

- **自动去重**: 历史记录中已存在的项目不会重复进行 AI 分析。
- **AI 简报**: 使用 LangChain 生成项目中文摘要（如果在 Action 中启用）。

## 🗂 历史归档 (Archives)

| 日期 (Date) | 链接 (Link) |
|---|---|
"""
    # 按文件名倒序（日期最新的在前）
    archive_files.sort(reverse=True)
    
    content = header
    for f in archive_files:
        if not f.endswith(".md"): continue
        date_str = f.replace(".md", "")
        content += f"| {date_str} | [查看日报](./{CONFIG['archive_dir']}/{f}) |\n"

    with open(CONFIG['readme_file'], 'w', encoding='utf-8') as f:
        f.write(content)

def main():
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    history = load_history()
    
    all_content_md = f"# 🚀 GitHub Trending {today_str}\n\n"
    
    has_new_content = False

    for category, url in CONFIG["urls"].items():
        print(f"\n--- 处理分类: {category} ---")
        repos = scrape_github_trending(url)
        
        category_md = f"## {category} Trending\n\n"
        category_md += "| 项目 | 简介 (AI/Original) | Stars | 状态 |\n"
        category_md += "|---|---|---|---|\n"
        
        count = 0
        for repo in repos:
            # 去重逻辑
            # 如果历史记录里有，我们认为是"旧项目"，不再生成 AI 摘要，但依然可以列在今日榜单里
            # 如果用户希望"完全不保存"重复项目，可以取消下面的注释：
            # if repo.full_name in history: continue 

            is_historied = repo.full_name in history
            repo.is_new = not is_historied
            
            summary = repo.description
            
            if repo.is_new:
                # 是新项目，且开启了 LLM，则生成摘要
                if CONFIG["enable_llm"]:
                    ai_sum = generate_ai_summary(repo)
                    repo.ai_summary = ai_sum
                    summary = f"🤖 **AI**: {ai_sum}"
                    # 记录到历史
                    history[repo.full_name] = repo.to_dict()
                    has_new_content = True
                else:
                    # 没开 AI，记录原始信息到历史防止下次被当做全新的
                    history[repo.full_name] = repo.to_dict()
                    has_new_content = True
            else:
                # 是旧项目，尝试从历史读取 AI 摘要
                cached = history.get(repo.full_name, {})
                if cached.get("ai_summary"):
                    summary = f"🤖 **AI (Cached)**: {cached['ai_summary']}"
            
            status_icon = "🆕" if repo.is_new else "🔁"
            
            # 格式化表格行 (处理 Markdown 破坏字符)
            clean_desc = summary.replace("|", "\\|").replace("\n", " ")
            row = f"| [{repo.owner}/{repo.name}]({repo.url}) | {clean_desc} | {repo.stars} | {status_icon} |\n"
            category_md += row
            count += 1
            
        if count > 0:
            all_content_md += category_md + "\n"
        
        # 礼貌性延迟
        time.sleep(2)

    # 保存每日归档
    os.makedirs(CONFIG["archive_dir"], exist_ok=True)
    daily_file_path = os.path.join(CONFIG["archive_dir"], f"{today_str}.md")
    
    with open(daily_file_path, 'w', encoding='utf-8') as f:
        f.write(all_content_md)
    print(f"已生成日报: {daily_file_path}")

    # 保存历史记录数据库
    save_history(history)

    # 更新总目录
    archives = os.listdir(CONFIG["archive_dir"])
    update_readme_index(archives)

if __name__ == "__main__":
    main()