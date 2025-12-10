import os
import yaml
import time
import requests
import datetime
import sqlite3
from bs4 import BeautifulSoup
from openai import OpenAI

# === 1. 配置加载 ===
def load_config():
    if not os.path.exists("config.yaml"):
        print("❌ 错误: 找不到 config.yaml")
        exit(1)
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # 环境变量覆盖 (支持 GitHub Actions)
    env_enable_llm = os.environ.get("ENABLE_LLM")
    if env_enable_llm is not None:
        config['settings']['enable_llm'] = (env_enable_llm.lower() == 'true')
    return config

# === 2. 数据库管理 (SQLite) ===
DB_PATH = "data/history.db"

def init_db():
    """初始化数据库表"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_history (
                name TEXT PRIMARY KEY,
                summary TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON project_history (name)")

def get_cached_summary(name):
    """从数据库查询摘要"""
    if not os.path.exists(DB_PATH):
        return None
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT summary FROM project_history WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row[0] if row else None

def save_cached_summary(name, summary):
    """保存摘要到数据库"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as conn:
        # 使用 REPLACE INTO，如果存在则更新，不存在则插入
        conn.execute("""
            REPLACE INTO project_history (name, summary, updated_at) 
            VALUES (?, ?, ?)
        """, (name, summary, today))

# === 3. 爬虫逻辑 (BeautifulSoup) ===
def scrape_github_trending(url, limit=10):
    """
    抓取 GitHub Trending 页面并解析
    """
    print(f"📡 正在抓取: {url} ...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200:
            print(f"❌ 请求失败: {resp.status_code}")
            return []
            
        soup = BeautifulSoup(resp.text, 'html.parser')
        repos = []
        
        # 遍历文章列表 (GitHub 目前使用 article.Box-row)
        items = soup.select('article.Box-row')
        
        for item in items[:limit]: # 这里直接做截断
            try:
                # 1. 获取项目名和链接
                h2_a = item.select_one('h2 a')
                if not h2_a: continue
                
                href = h2_a['href'].strip() # /owner/repo
                full_name = href.strip('/') # owner/repo
                repo_url = f"https://github.com{href}"
                
                # 2. 获取描述
                p_desc = item.select_one('p.col-9')
                description = p_desc.text.strip() if p_desc else "无描述"
                
                # 3. 获取 Stars (粗略获取当日新增或总星数)
                stars_elem = item.select_one('a[href$="/stargazers"]')
                stars = stars_elem.text.strip() if stars_elem else "N/A"
                
                repos.append({
                    "repo_name": full_name,
                    "url": repo_url,
                    "description": description,
                    "stars": stars
                })
            except Exception as e:
                print(f"⚠️ 解析单个项目出错: {e}")
                continue
                
        return repos

    except Exception as e:
        print(f"❌ 爬虫异常: {e}")
        return []

# === 4. AI 摘要生成 ===
def generate_ai_summary(client, repo, model_name):
    if not client: return ""
    
    name = repo['repo_name']
    desc = repo['description']
    
    prompt = (
        f"项目: {name}\n"
        f"描述: {desc}\n"
        "请用中文一句话概括这个项目的核心功能，不要废话。"
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "你是一个技术专家。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ AI 接口错误: {e}")
        return ""

# === 5. Markdown 构建 (集成 SQLite) ===
def build_section(title, repos, settings, llm_client):
    section = f"## {title}\n\n"
    section += "| 排名 | 项目 | Stars | 简介 (AI/Raw) |\n"
    section += "| :--- | :--- | :--- | :--- |\n"

    for idx, repo in enumerate(repos, 1):
        name = repo['repo_name']
        url = repo['url']
        stars = repo['stars']
        raw_desc = repo['description'].replace('|', '\|').replace('\n', ' ')
        
        final_desc = raw_desc
        
        # AI 逻辑
        if settings['enable_llm']:
            # 1. 尝试从 SQLite 查缓存
            cached_summary = get_cached_summary(name)
            
            if cached_summary:
                final_desc = f"🤖 {cached_summary}"
            
            # 2. 如果没缓存，且有 Client，则生成并保存
            elif llm_client:
                ai_sum = generate_ai_summary(llm_client, repo, settings.get('ai_model', 'gpt-3.5-turbo'))
                if ai_sum:
                    final_desc = f"🤖 {ai_sum}"
                    # 写入 SQLite
                    save_cached_summary(name, ai_sum)
        
        # 截断长文本
        if len(final_desc) > 150:
            final_desc = final_desc[:147] + "..."

        section += f"| {idx} | [{name}]({url}) | {stars} | {final_desc} |\n"
    
    return section

# === 6. 归档索引列表 ===
def get_archive_list(archive_dir):
    if not os.path.exists(archive_dir): return []
    files = [f for f in os.listdir(archive_dir) if f.endswith('.md')]
    files.sort(reverse=True) # 日期倒序
    
    lines = []
    for f in files:
        date = f.replace('.md', '')
        lines.append(f"| {date} | [查看日报](./{archive_dir}/{f}) |")
    return lines

# === 主程序 ===
def main():
    config = load_config()
    settings = config['settings']
    
    # 初始化数据库
    init_db()
    
    # 初始化 AI 客户端
    llm_client = None
    if settings['enable_llm']:
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL")
        if api_key:
            llm_client = OpenAI(api_key=api_key, base_url=base_url)

    # 准备内容
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    
    report_content = settings['readme_header'].replace("{{ update_time }}", update_time) + "\n\n"

    # 遍历任务
    for item in config['collections']:
        limit = settings.get('top_list_limit', 10)
        repos = scrape_github_trending(item['url'], limit=limit)
        
        if repos:
            section_md = build_section(item['title'], repos, settings, llm_client)
            report_content += section_md + "\n"
        
        time.sleep(2) # 防封 IP 延迟

    # 保存今日归档
    archive_dir = settings['archive_dir']
    os.makedirs(archive_dir, exist_ok=True)
    with open(os.path.join(archive_dir, f"{today}.md"), "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"✅ 今日归档已生成: {today}.md")

    # 更新 README (头部 + 归档列表)
    archive_list = get_archive_list(archive_dir)
    history_section = "\n## 🗂 历史归档 (Archives)\n\n| 日期 | 链接 |\n| :--- | :--- |\n"
    # 仅显示最近 14 条
    history_section += "\n".join(archive_list[:14]) 
    
    with open(settings['readme_file'], "w", encoding="utf-8") as f:
        f.write(report_content + history_section)
    print("✅ README 已更新")

if __name__ == "__main__":
    main()
