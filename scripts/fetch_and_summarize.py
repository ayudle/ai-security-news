"""
fetch_and_summarize.py
RSSフィードからニュースを収集し、Gemini APIで日本語要約してJSONに保存する
"""

import os
import json
import hashlib
import feedparser
import requests
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser
import google.generativeai as genai

# ============================================================
# 信頼できるソース設定（収益化・引用に耐えうる厳選リスト）
# ============================================================
SOURCES = [
    # ティアA: 政府・公的機関（著作権フリー・引用自由）
    {"name": "CISA",        "tier": "A", "url": "https://www.cisa.gov/news.xml",                         "category": "公的機関"},
    {"name": "NIST",        "tier": "A", "url": "https://www.nist.gov/news-events/cybersecurity/rss.xml","category": "公的機関"},
    {"name": "ENISA",       "tier": "A", "url": "https://www.enisa.europa.eu/news/enisa-news/RSS",       "category": "公的機関"},

    # ティアA: 大手報道機関（商用引用ガイドライン明確）
    {"name": "Reuters Tech",  "tier": "A", "url": "https://feeds.reuters.com/reuters/technologyNews",    "category": "大手メディア"},
    {"name": "BBC Technology","tier": "A", "url": "http://feeds.bbci.co.uk/news/technology/rss.xml",     "category": "大手メディア"},

    # ティアB: セキュリティ専門メディア
    {"name": "Krebs on Security", "tier": "B", "url": "https://krebsonsecurity.com/feed/",               "category": "専門メディア"},
    {"name": "Dark Reading",      "tier": "B", "url": "https://www.darkreading.com/rss.xml",             "category": "専門メディア"},
    {"name": "SecurityWeek",      "tier": "B", "url": "https://feeds.feedburner.com/Securityweek",       "category": "専門メディア"},
    {"name": "The Hacker News",   "tier": "B", "url": "https://feeds.feedburner.com/TheHackersNews",     "category": "専門メディア"},
    {"name": "Bleeping Computer", "tier": "B", "url": "https://www.bleepingcomputer.com/feed/",          "category": "専門メディア"},

    # ティアB: Tech専門メディア
    {"name": "Wired Security", "tier": "B", "url": "https://www.wired.com/feed/category/security/latest/rss", "category": "Techメディア"},
    {"name": "Ars Technica",   "tier": "B", "url": "https://feeds.arstechnica.com/arstechnica/security", "category": "Techメディア"},

    # ティアC: 学術・研究（CC BYライセンス）
    {"name": "arXiv cs.CR", "tier": "C", "url": "https://rss.arxiv.org/rss/cs.CR",                       "category": "学術・研究"},
]

# AIキーワード（どちらか含む記事のみ選別）
AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning", "neural network",
    "large language model", "LLM", "GPT", "generative AI", "AI model",
    "AI security", "AI threat", "AI attack", "AI defense", "AI vulnerability",
    "adversarial", "prompt injection", "model poisoning", "AI governance",
    "ChatGPT", "Claude", "Gemini", "Llama", "foundation model",
]

MAX_ARTICLES_PER_RUN = 8   # 1日あたりの最大記事数（Gemini API制限を考慮）
OUTPUT_PATH = "docs/data/latest.json"
JST = timezone(timedelta(hours=9))


def fetch_rss(source: dict) -> list[dict]:
    """RSSフィードを取得してarticleリストを返す"""
    articles = []
    try:
        feed = feedparser.parse(source["url"])
        cutoff = datetime.now(JST) - timedelta(hours=36)  # 36時間以内

        for entry in feed.entries[:20]:
            # 日付パース
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

            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", getattr(entry, "description", ""))
            link = getattr(entry, "link", "")

            # AIキーワードフィルター（タイトル+サマリで判定）
            combined = (title + " " + summary).lower()
            if not any(kw.lower() in combined for kw in AI_KEYWORDS):
                continue

            articles.append({
                "id": hashlib.md5(link.encode()).hexdigest()[:12],
                "title": title,
                "summary": summary[:500],
                "url": link,
                "source_name": source["name"],
                "source_tier": source["tier"],
                "category": source["category"],
                "published": pub.astimezone(JST).isoformat(),
            })
    except Exception as e:
        print(f"[WARN] {source['name']}: {e}")
    return articles


def deduplicate(articles: list[dict]) -> list[dict]:
    """URLの重複を除去し、ティアA優先でソート"""
    seen_ids = set()
    unique = []
    tier_order = {"A": 0, "B": 1, "C": 2}
    for a in sorted(articles, key=lambda x: tier_order.get(x["source_tier"], 9)):
        if a["id"] not in seen_ids:
            seen_ids.add(a["id"])
            unique.append(a)
    return unique


def summarize_with_gemini(articles: list[dict]) -> list[dict]:
    """Gemini APIで各記事を日本語要約する（バッチ処理でAPI呼び出しを最小化）"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    # 全記事をまとめて1回のAPIコールで処理（コスト最小化）
    articles_text = "\n\n".join([
        f"[{i+1}] タイトル: {a['title']}\n概要: {a['summary']}\nURL: {a['url']}\nソース: {a['source_name']}（{a['category']}）"
        for i, a in enumerate(articles)
    ])

    prompt = f"""以下のサイバーセキュリティ×AI分野の英語ニュース記事を日本語で要約してください。

各記事について以下のJSON形式で回答してください。前置きや説明文は不要です。JSONのみ出力してください。

[
  {{
    "index": 1,
    "title_ja": "日本語タイトル",
    "summary_ja": "3〜4文の日本語要約。背景・内容・影響の順で記述",
    "importance": "高 | 中 | 低",
    "tags": ["AI for Security", "Security for AI", "脆弱性", "脅威インテル", "規制・政策", "研究・学術"]
  }}
]

記事一覧:
{articles_text}
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # コードブロック除去
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        summaries = json.loads(text)
    except Exception as e:
        print(f"[ERROR] Gemini API: {e}")
        summaries = [{"index": i+1, "title_ja": a["title"], "summary_ja": a["summary"][:200],
                      "importance": "中", "tags": [a["category"]]} for i, a in enumerate(articles)]

    # 元データにマージ
    summary_map = {s["index"]: s for s in summaries}
    enriched = []
    for i, article in enumerate(articles):
        s = summary_map.get(i + 1, {})
        enriched.append({
            **article,
            "title_ja":    s.get("title_ja", article["title"]),
            "summary_ja":  s.get("summary_ja", ""),
            "importance":  s.get("importance", "中"),
            "tags":        s.get("tags", []),
        })
    return enriched


def main():
    print(f"[{datetime.now(JST).strftime('%Y-%m-%d %H:%M')} JST] ニュース収集開始")

    # 全ソースからRSS収集
    all_articles = []
    for source in SOURCES:
        items = fetch_rss(source)
        print(f"  {source['name']}: {len(items)}件")
        all_articles.extend(items)

    # 重複除去
    unique = deduplicate(all_articles)
    print(f"重複除去後: {len(unique)}件")

    # 上限に絞る（ティアA優先で選出済み）
    selected = unique[:MAX_ARTICLES_PER_RUN]
    print(f"選出: {len(selected)}件 → Gemini APIで要約")

    if not selected:
        print("[WARN] 該当記事なし。スキップ。")
        return

    # Geminiで要約
    enriched = summarize_with_gemini(selected)

    # 既存データ読み込み（履歴保持）
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    history = []
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                old = json.load(f)
                history = old.get("history", [])
        except Exception:
            pass

    # 本日分を先頭に追加（過去30日分を保持）
    today_str = datetime.now(JST).strftime("%Y-%m-%d")
    history = [h for h in history if h.get("date") != today_str]
    history.insert(0, {"date": today_str, "articles": enriched})
    history = history[:30]

    output = {
        "updated": datetime.now(JST).isoformat(),
        "today": today_str,
        "articles": enriched,
        "history": history,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"保存完了: {OUTPUT_PATH}")
    print(f"本日の記事: {len(enriched)}件")


if __name__ == "__main__":
    main()
