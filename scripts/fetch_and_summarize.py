"""
fetch_and_summarize.py
RSSからニュース収集 → Gemini APIで日本語要約・示唆抽出
"""

import os, json, hashlib, feedparser
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser
from google import genai

SOURCES = [
    {"name": "CISA",              "tier": "A", "url": "https://www.cisa.gov/cybersecurity-advisories/all.xml",       "category": "公的機関"},
    {"name": "NIST",              "tier": "A", "url": "https://csrc.nist.gov/feeds/all",                             "category": "公的機関"},
    {"name": "Krebs on Security", "tier": "B", "url": "https://krebsonsecurity.com/feed/",                           "category": "専門メディア"},
    {"name": "Dark Reading",      "tier": "B", "url": "https://www.darkreading.com/rss.xml",                         "category": "専門メディア"},
    {"name": "SecurityWeek",      "tier": "B", "url": "https://feeds.feedburner.com/Securityweek",                   "category": "専門メディア"},
    {"name": "The Hacker News",   "tier": "B", "url": "https://feeds.feedburner.com/TheHackersNews",                 "category": "専門メディア"},
    {"name": "Bleeping Computer", "tier": "B", "url": "https://www.bleepingcomputer.com/feed/",                      "category": "専門メディア"},
    {"name": "Wired Security",    "tier": "B", "url": "https://www.wired.com/feed/category/security/latest/rss",     "category": "Techメディア"},
    {"name": "Ars Technica",      "tier": "B", "url": "https://feeds.arstechnica.com/arstechnica/security",          "category": "Techメディア"},
    {"name": "MIT Tech Review",   "tier": "B", "url": "https://www.technologyreview.com/feed/",                      "category": "Techメディア"},
    {"name": "arXiv cs.CR",       "tier": "C", "url": "https://rss.arxiv.org/rss/cs.CR",                            "category": "学術・研究"},
    {"name": "arXiv cs.AI",       "tier": "C", "url": "https://rss.arxiv.org/rss/cs.AI",                            "category": "学術・研究"},
]

AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning", "neural network",
    "large language model", "llm", "gpt", "generative ai", "ai model", "ai system",
    "ai security", "ai threat", "ai attack", "ai defense", "ai vulnerability",
    "adversarial", "prompt injection", "model poisoning", "ai governance",
    "chatgpt", "claude", "gemini", "llama", "foundation model", "openai", "anthropic",
    "cybersecurity", "cyber attack", "ransomware", "malware", "vulnerability",
    "data breach", "zero-day", "exploit", "phishing", "threat intelligence",
]

MAX_ARTICLES = 5
OUTPUT_PATH  = "docs/data/latest.json"
JST          = timezone(timedelta(hours=9))


def fetch_rss(source):
    articles = []
    try:
        feed   = feedparser.parse(source["url"])
        cutoff = datetime.now(JST) - timedelta(hours=36)
        for entry in feed.entries[:20]:
            pub = None
            for field in ["published", "updated", "created"]:
                raw = getattr(entry, field, None)
                if raw:
                    try:
                        pub = dateparser.parse(raw)
                        if pub and pub.tzinfo is None:
                            pub = pub.replace(tzinfo=timezone.utc)
                        break
                    except Exception:
                        pass
            if pub is None:
                pub = datetime.now(timezone.utc)
            if pub.astimezone(JST) < cutoff:
                continue
            title   = getattr(entry, "title", "")
            summary = getattr(entry, "summary", getattr(entry, "description", ""))
            link    = getattr(entry, "link", "")
            combined = (title + " " + summary).lower()
            if not any(kw in combined for kw in AI_KEYWORDS):
                continue
            articles.append({
                "id":          hashlib.md5(link.encode()).hexdigest()[:12],
                "title":       title,
                "summary":     summary[:500],
                "url":         link,
                "source_name": source["name"],
                "source_tier": source["tier"],
                "category":    source["category"],
                "published":   pub.astimezone(JST).isoformat(),
            })
    except Exception as e:
        print(f"  [WARN] {source['name']}: {e}")
    return articles


def deduplicate(articles):
    seen, unique = set(), []
    for a in sorted(articles, key=lambda x: {"A":0,"B":1,"C":2}.get(x["source_tier"], 9)):
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)
    return unique


def summarize_with_gemini(articles):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が未設定です")

    client = genai.Client(api_key=api_key)

    articles_text = "\n\n".join([
        f"[{i+1}] タイトル: {a['title']}\n概要: {a['summary']}\nURL: {a['url']}\nソース: {a['source_name']}"
        for i, a in enumerate(articles)
    ])

    prompt = f"""以下のサイバーセキュリティ×AI分野のニュース記事を日本語で分析してください。
JSONのみを返してください。前置き・説明文・コードブロック記号（```）は不要です。

[
  {{
    "index": 1,
    "title_ja": "日本語タイトル",
    "summary_ja": "3〜4文の日本語要約。背景・内容・影響の順で記述してください",
    "insight": "この記事から得られる重要な示唆や学び。セキュリティ実務者視点で1〜2文",
    "importance": "高 | 中 | 低",
    "tags": ["AI for Security", "Security for AI", "脆弱性", "脅威インテル", "規制・政策", "研究・学術"],
    "keywords": ["キーワード1", "キーワード2", "キーワード3"]
  }}
]

記事一覧:
{articles_text}
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt
        )
        text = response.text.strip()
        # コードブロック除去
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        summaries = json.loads(text.strip())
    except Exception as e:
        print(f"  [ERROR] Gemini API: {e}")
        summaries = [{"index": i+1, "title_ja": a["title"], "summary_ja": a["summary"][:200],
                      "insight": "", "importance": "中", "tags": [a["category"]], "keywords": []}
                     for i, a in enumerate(articles)]

    summary_map = {s["index"]: s for s in summaries}
    enriched = []
    for i, article in enumerate(articles):
        s = summary_map.get(i + 1, {})
        enriched.append({
            **article,
            "title_ja":   s.get("title_ja", article["title"]),
            "summary_ja": s.get("summary_ja", ""),
            "insight":    s.get("insight", ""),
            "importance": s.get("importance", "中"),
            "tags":       s.get("tags", []),
            "keywords":   s.get("keywords", []),
            "views":      0,
        })
    return enriched


def main():
    print(f"[{datetime.now(JST).strftime('%Y-%m-%d %H:%M')} JST] ニュース収集開始")

    all_articles = []
    for source in SOURCES:
        items = fetch_rss(source)
        print(f"  {source['name']}: {len(items)}件")
        all_articles.extend(items)

    unique   = deduplicate(all_articles)
    selected = unique[:MAX_ARTICLES]
    print(f"重複除去後: {len(unique)}件 → 上位{len(selected)}件を選出")

    if not selected:
        print("[WARN] 該当記事なし。スキップ。")
        return

    print("Gemini APIで要約中...")
    enriched = summarize_with_gemini(selected)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    history = []
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                old = json.load(f)
                history = old.get("history", [])
        except Exception:
            pass

    today_str = datetime.now(JST).strftime("%Y-%m-%d")
    history = [h for h in history if h.get("date") != today_str]
    history.insert(0, {"date": today_str, "articles": enriched})
    history = history[:90]

    output = {
        "updated":  datetime.now(JST).isoformat(),
        "today":    today_str,
        "articles": enriched,
        "history":  history,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"完了: {len(enriched)}件保存")


if __name__ == "__main__":
    main()
