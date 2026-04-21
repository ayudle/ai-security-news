"""
fetch_and_summarize.py v3
RSS収集 → Gemini APIで日本語要約・事前定義タグ付け
"""

import os, json, hashlib, feedparser
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser
from google import genai

# ============================================================
# ソース定義
# ============================================================
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

# ============================================================
# タグ体系（事前定義・LLMはこのリスト外のタグを生成禁止）
# ============================================================
TAG_TAXONOMY = {
    "attack":   {
        "label": "攻撃・脅威",
        "subs": ["ランサムウェア","フィッシング","APT","マルウェア","DDoS",
                 "サプライチェーン攻撃","ソーシャルエンジニアリング","クレデンシャル窃取"]
    },
    "vuln": {
        "label": "脆弱性",
        "subs": ["ゼロデイ","CVE","エクスプロイト","パッチ未適用","設定ミス","認証バイパス"]
    },
    "ai_sec": {
        "label": "AI×セキュリティ",
        "subs": ["プロンプトインジェクション","モデル汚染","敵対的攻撃","LLMセキュリティ",
                 "AIを使った防御","AIを使った攻撃","モデル逆転攻撃"]
    },
    "ai_risk": {
        "label": "AIリスク",
        "subs": ["ハルシネーション","バイアス・差別","プライバシー侵害","誤情報生成",
                 "著作権","安全性評価","アライメント"]
    },
    "policy": {
        "label": "規制・政策",
        "subs": ["EU AI法","NIST","CISA勧告","国内規制","国際連携","コンプライアンス","標準化"]
    },
    "incident": {
        "label": "インシデント",
        "subs": ["データ侵害","サービス停止","情報漏洩","金融被害","個人情報流出"]
    },
    "biz_tech": {
        "label": "ビジネス・技術動向",
        "subs": ["資金調達","M&A","製品リリース","市場トレンド","研究・論文","スタートアップ"]
    },
}

# タグ選択肢をLLMプロンプト用にフラット化
def build_tag_reference():
    lines = []
    for key, val in TAG_TAXONOMY.items():
        subs = "、".join(val["subs"])
        lines.append(f'  大項目: "{val["label"]}" (id: {key}) → 中項目の選択肢: {subs}')
    return "\n".join(lines)

KEYWORDS = [
    "artificial intelligence","machine learning","deep learning","neural network",
    "large language model","llm","gpt","generative ai","ai model","ai system",
    "ai security","ai threat","ai attack","ai defense","ai vulnerability",
    "adversarial","prompt injection","model poisoning","ai governance","ai risk",
    "chatgpt","claude","gemini","llama","foundation model","openai","anthropic",
    "cybersecurity","cyber attack","ransomware","malware","vulnerability",
    "data breach","zero-day","exploit","phishing","threat intelligence",
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
            for field in ["published","updated","created"]:
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
            if not any(kw in (title + " " + summary).lower() for kw in KEYWORDS):
                continue
            articles.append({
                "id":          hashlib.md5(link.encode()).hexdigest()[:12],
                "title":       title,
                "summary":     summary[:500],
                "url":         link,
                "source_name": source["name"],
                "source_tier": source["tier"],
                "published":   pub.astimezone(JST).isoformat(),
            })
    except Exception as e:
        print(f"  [WARN] {source['name']}: {e}")
    return articles


def deduplicate(articles):
    seen, unique = set(), []
    for a in sorted(articles, key=lambda x: {"A":0,"B":1,"C":2}.get(x["source_tier"],9)):
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)
    return unique


def summarize_with_gemini(articles):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が未設定です")

    client = genai.Client(api_key=api_key)
    tag_ref = build_tag_reference()

    articles_text = "\n\n".join([
        f"[{i+1}] タイトル: {a['title']}\n概要: {a['summary']}\nURL: {a['url']}\nソース: {a['source_name']}"
        for i, a in enumerate(articles)
    ])

    prompt = f"""以下のサイバーセキュリティ×AI分野のニュース記事を日本語で分析してください。
必ずJSONのみを返してください。前置き・説明文・```記号は一切不要です。

【タグ定義】（必ずこのリストから選ぶこと。リスト外のタグは絶対に使用禁止）
{tag_ref}

【出力形式】
[
  {{
    "index": 1,
    "title_ja": "日本語タイトル（簡潔に）",
    "summary_ja": "3〜4文の日本語要約。背景・内容・影響の順で記述",
    "insight": "セキュリティ実務者・研究者視点での示唆や学び。1〜2文",
    "importance": "高 | 中 | 低",
    "importance_reason": "重要度をそう判断した理由を1文で",
    "tag_main_id": "attack | vuln | ai_sec | ai_risk | policy | incident | biz_tech のいずれか1つ",
    "tag_subs": ["中項目を1〜3つ。必ず上記タグ定義のリスト内から選ぶこと"]
  }}
]

【重要度の基準】
高: 広範囲に影響・即時対応が必要・業界標準を変える可能性
中: 特定分野に影響・注目すべきトレンド
低: 参考情報・長期的な動向

【記事一覧】
{articles_text}
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        text = response.text.strip()
        if "```" in text:
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else parts[0]
            if text.startswith("json"):
                text = text[4:]
        summaries = json.loads(text.strip())
    except Exception as e:
        print(f"  [ERROR] Gemini API: {e}")
        summaries = [{
            "index": i+1,
            "title_ja": a["title"],
            "summary_ja": a["summary"][:200],
            "insight": "",
            "importance": "中",
            "importance_reason": "",
            "tag_main_id": "attack",
            "tag_subs": []
        } for i, a in enumerate(articles)]

    summary_map = {s["index"]: s for s in summaries}

    # 中項目の検証（リスト外は除去）
    valid_subs = {sub for v in TAG_TAXONOMY.values() for sub in v["subs"]}

    enriched = []
    for i, article in enumerate(articles):
        s = summary_map.get(i + 1, {})
        main_id  = s.get("tag_main_id", "attack")
        if main_id not in TAG_TAXONOMY:
            main_id = "attack"
        raw_subs = s.get("tag_subs", [])
        clean_subs = [t for t in raw_subs if t in valid_subs][:3]

        enriched.append({
            **article,
            "title_ja":          s.get("title_ja", article["title"]),
            "summary_ja":        s.get("summary_ja", ""),
            "insight":           s.get("insight", ""),
            "importance":        s.get("importance", "中"),
            "importance_reason": s.get("importance_reason", ""),
            "tag_main_id":       main_id,
            "tag_main_label":    TAG_TAXONOMY[main_id]["label"],
            "tag_subs":          clean_subs,
            "views":             0,
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

    print("Gemini APIで要約・タグ付け中...")
    enriched = summarize_with_gemini(selected)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    history = []
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                history = json.load(f).get("history", [])
        except Exception:
            pass

    today_str = datetime.now(JST).strftime("%Y-%m-%d")
    history = [h for h in history if h.get("date") != today_str]
    history.insert(0, {"date": today_str, "articles": enriched})
    history = history[:90]

    output = {
        "updated":    datetime.now(JST).isoformat(),
        "today":      today_str,
        "articles":   enriched,
        "history":    history,
        "taxonomy":   TAG_TAXONOMY,
    }
    # 要約が全て英語のままの場合はJSONを更新しない（LLM失敗時の保護）
    japanese_count = sum(1 for a in enriched if a.get("summary_ja") and
                        any(ord(c) > 0x3000 for c in a.get("summary_ja","")))
    if japanese_count == 0 and len(enriched) > 0:
        print("[SKIP] 全記事の要約が英語のままです。LLMエラーの可能性があるためJSONを更新しません。")
        return

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"完了: {len(enriched)}件保存（うち日本語要約: {japanese_count}件）")


if __name__ == "__main__":
    main()
