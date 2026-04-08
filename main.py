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
        
        items = soup.select('article.Box-row')
        
        for item in items[:limit]:
            try:
                h2_a = item.select_one('h2 a')
                if not h2_a: continue
                
                href = h2_a['href'].strip()
                full_name = href.strip('/')
                repo_url = f"https://github.com{href}"
                
                p_desc = item.select_one('p.col-9')
                description = p_desc.text.strip() if p_desc else "无描述"
                
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

def parse_stars(stars_str):
    """解析星数字符串为数字，如 '1.2k' -> 1200"""
    if not stars_str or stars_str == "N/A":
        return 0
    stars_str = stars_str.strip().replace(',', '')
    if 'k' in stars_str.lower():
        return int(float(stars_str.lower().replace('k', '')) * 1000)
    if 'K' in stars_str:
        return int(float(stars_str.replace('K', '')) * 1000)
    try:
        return int(stars_str)
    except:
        return 0

def should_filter(repo, filters):
    """判断项目是否应被过滤"""
    desc = repo.get('description', '').strip().lower()
    if filters.get('skip_no_description', False):
        if not desc or desc in ['无描述', 'no description', '']:
            return True, "无描述"

    stars = parse_stars(repo.get('stars', '0'))
    min_total = filters.get('min_total_stars', 0)
    if min_total > 0 and stars < min_total:
        return True, f"总星数 {stars} < {min_total}"

    return False, ""

# === 4. AI 摘要生成 (随机选一个 API，失败则换另一个) ===
def generate_ai_summary(clients, repo, model_names):
    import random
    
    name = repo['repo_name']
    desc = repo['description']
    
    prompt = (
        f"项目: {name}\n"
        f"描述: {desc}\n"
        "请用中文一句话概括这个项目的核心功能，不要废话。"
    )

    indices = list(range(len(clients)))
    random.shuffle(indices)
    
    for i in indices:
        client = clients[i]
        model = model_names[i]
        if not client:
            continue
        
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个技术专家。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.3,
                timeout=20
            )
            text = response.choices[0].message.content.strip()
            if text:
                return text, model
        except Exception as e:
            print(f"⚠️ [{model}] 接口错误: {e}")
            continue
    
    return "", ""

# === 5. Markdown 构建 (集成 SQLite + 过滤) ===
def build_section(title, repos, settings, llm_clients, model_names):
    section = f"## {title}\n\n"
    section += "| 排名 | 项目 | Stars | 简介 (AI/Raw) |\n"
    section += "| :--- | :--- | :--- | :--- |\n"

    filters = settings.get('filters', {})
    filtered_count = 0

    for idx, repo in enumerate(repos, 1):
        name = repo['repo_name']
        url = repo['url']
        stars = repo['stars']
        raw_desc = repo['description'].replace('|', '\|').replace('\n', ' ')
        
        final_desc = raw_desc
        model_tag = ""
        
        # 过滤检查
        is_filtered, filter_reason = should_filter(repo, filters)
        
        if is_filtered:
            final_desc = f"⛔ [{filter_reason}] {final_desc}"
        else:
            # AI 逻辑
            if settings['enable_llm']:
                cached_summary = get_cached_summary(name)
                
                if cached_summary:
                    final_desc = f"🤖 {cached_summary}"
                
                elif any(llm_clients):
                    ai_sum, model_used = generate_ai_summary(llm_clients, repo, model_names)
                    if ai_sum:
                        final_desc = f"🤖 [{model_used}] {ai_sum}"
                        save_cached_summary(name, ai_sum)
                    time.sleep(1.5)
        
        if len(final_desc) > 150:
            final_desc = final_desc[:147] + "..."

        section += f"| {idx} | [{name}]({url}) | {stars} | {final_desc} |\n"
    
    return section

# === 6. 归档索引列表 ===
def get_archive_list(archive_dir):
    if not os.path.exists(archive_dir): return []
    files = [f for f in os.listdir(archive_dir) if f.endswith('.md')]
    files.sort(reverse=True)
    
    lines = []
    for f in files:
        date = f.replace('.md', '')
        lines.append(f"| {date} | [查看日报](./{archive_dir}/{f}) |")
    return lines

# === 主程序 ===
def main():
    config = load_config()
    settings = config['settings']
    
    init_db()
    
    llm_clients = [None, None]
    model_names = ["", ""]
    
    if settings['enable_llm']:
        minimax_api_key = os.environ.get("MINIMAX_API_KEY")
        minimax_base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic")
        if minimax_api_key:
            llm_clients[0] = OpenAI(api_key=minimax_api_key, base_url=minimax_base_url)
            model_names[0] = os.getenv("LLM_MODEL", "MiniMax-M2.7")
        
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        openai_base_url = os.environ.get("OPENAI_BASE_URL")
        if openai_api_key:
            llm_clients[1] = OpenAI(api_key=openai_api_key, base_url=openai_base_url)
            model_names[1] = settings.get('ai_model', 'gpt-3.5-turbo')

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    
    report_content = settings['readme_header'].replace("{{ update_time }}", update_time) + "\n\n"

    for item in config['collections']:
        limit = settings.get('top_list_limit', 10)
        repos = scrape_github_trending(item['url'], limit=limit)
        
        if repos:
            section_md = build_section(item['title'], repos, settings, llm_clients, model_names)
            report_content += section_md + "\n"
        
        time.sleep(2)

    archive_dir = settings['archive_dir']
    os.makedirs(archive_dir, exist_ok=True)
    with open(os.path.join(archive_dir, f"{today}.md"), "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"✅ 今日归档已生成: {today}.md")

    archive_list = get_archive_list(archive_dir)
    history_section = "\n## 🗂 历史归档 (Archives)\n\n| 日期 | 链接 |\n| :--- | :--- |\n"
    history_section += "\n".join(archive_list[:14]) 
    
    with open(settings['readme_file'], "w", encoding="utf-8") as f:
        f.write(report_content + history_section)
    print("✅ README 已更新")

if __name__ == "__main__":
    main()
