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
    {"name": "CISA",                  "tier": "A", "url": "https://www.cisa.gov/cybersecurity-advisories/all.xml",       "category": "公的機関"},
    {"name": "NIST",                  "tier": "A", "url": "https://csrc.nist.gov/feeds/all",                             "category": "公的機関"},
    {"name": "OWASP GenAI",           "tier": "A", "url": "https://genai.owasp.org/feed/",                               "category": "公的機関"},
    {"name": "Google Security Blog",  "tier": "A", "url": "https://security.googleblog.com/feeds/posts/default",         "category": "Techメディア"},
    {"name": "Palo Alto Unit 42",     "tier": "A", "url": "https://unit42.paloaltonetworks.com/feed/",                   "category": "専門メディア"},
    {"name": "Krebs on Security",     "tier": "B", "url": "https://krebsonsecurity.com/feed/",                           "category": "専門メディア"},
    {"name": "Dark Reading",          "tier": "B", "url": "https://www.darkreading.com/rss.xml",                         "category": "専門メディア"},
    {"name": "SecurityWeek",          "tier": "B", "url": "https://feeds.feedburner.com/Securityweek",                   "category": "専門メディア"},
    {"name": "The Hacker News",       "tier": "B", "url": "https://feeds.feedburner.com/TheHackersNews",                 "category": "専門メディア"},
    {"name": "Bleeping Computer",     "tier": "B", "url": "https://www.bleepingcomputer.com/feed/",                      "category": "専門メディア"},
    {"name": "Embrace The Red",       "tier": "B", "url": "https://embracethered.com/blog/index.xml",                    "category": "AI×セキュリティ研究"},
    {"name": "Simon Willison",        "tier": "B", "url": "https://simonwillison.net/atom/everything/",                  "category": "AI研究"},
    {"name": "Wired Security",        "tier": "B", "url": "https://www.wired.com/feed/category/security/latest/rss",     "category": "Techメディア"},
    {"name": "Ars Technica",          "tier": "B", "url": "https://feeds.arstechnica.com/arstechnica/security",          "category": "Techメディア"},
    {"name": "MIT Tech Review",       "tier": "B", "url": "https://www.technologyreview.com/feed/",                      "category": "Techメディア"},
    {"name": "arXiv cs.CR",           "tier": "C", "url": "https://rss.arxiv.org/rss/cs.CR",                            "category": "学術・研究"},
    {"name": "arXiv cs.AI",           "tier": "C", "url": "https://rss.arxiv.org/rss/cs.AI",                            "category": "学術・研究"},
]

# ============================================================
# タグ体系（事前定義・LLMはこのリスト外のタグを生成禁止）
# ============================================================
AFFECTED_LAYERS = [
    "デバイス/エッジ", "ネットワーク", "クラウド/サーバー",
    "アプリ/API", "データ/AI", "ガバナンス/規制",
]

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

# AI関連キーワード（必須・これが含まれる記事を優先）
AI_KEYWORDS = [
    "artificial intelligence","machine learning","deep learning","neural network",
    "large language model","llm","gpt","generative ai","ai model","ai system",
    "ai security","ai threat","ai attack","ai defense","ai vulnerability",
    "adversarial","prompt injection","model poisoning","ai governance","ai risk",
    "chatgpt","claude","gemini","llama","foundation model","openai","anthropic",
    "ai agent","agentic","mcp","model context protocol","ai compliance",
    "ai regulation","ai act","ai framework","ai observability","ai safety",
    "security for ai","ai for security","ai risk management",
]

# セキュリティキーワード（AIが含まれない場合のフォールバック・件数が少ない時のみ使用）
SECURITY_KEYWORDS = [
    "cybersecurity","cyber attack","ransomware","malware",
    "data breach","zero-day","threat intelligence",
]

# フィルター用（両方まとめたもの）
KEYWORDS = AI_KEYWORDS + SECURITY_KEYWORDS

MAX_ARTICLES = 10
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
            combined = (title + " " + summary).lower()
            has_ai = any(kw in combined for kw in AI_KEYWORDS)
            has_sec = any(kw in combined for kw in SECURITY_KEYWORDS)
            if not has_ai and not has_sec:
                continue
            ai_score = 2 if has_ai else 1
            articles.append({
                "id":          hashlib.md5(link.encode()).hexdigest()[:12],
                "title":       title,
                "summary":     summary[:500],
                "url":         link,
                "ai_score":    ai_score,
                "source_name": source["name"],
                "source_tier": source["tier"],
                "published":   pub.astimezone(JST).isoformat(),
            })
    except Exception as e:
        print(f"  [WARN] {source['name']}: {e}")
    return articles


def deduplicate(articles):
    """AI関連記事を優先、同一ソースから最大2件まで"""
    from collections import Counter
    seen, unique = set(), []
    source_count = Counter()
    MAX_PER_SOURCE = 2

    # ソート: AI関連記事優先（ai_score降順）→ Tier（A→B→C）
    sorted_articles = sorted(
        articles,
        key=lambda x: (
            -x.get("ai_score", 1),
            {"A":0,"B":1,"C":2}.get(x.get("source_tier","B"), 9)
        )
    )

    for a in sorted_articles:
        if a["id"] in seen:
            continue
        if source_count[a["source_name"]] >= MAX_PER_SOURCE:
            continue
        seen.add(a["id"])
        source_count[a["source_name"]] += 1
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

    prompt = f"""あなたはサイバーセキュリティ×AI領域に精通したCISOアドバイザーであり、
マッキンゼーのトップコンサルタントの視点も併せ持ち、さらに次世代のサイバーディフェンスセンター（CDC）サービス設計者でもあります。

CDCとは、検知・調査・対応・復旧・監査対応支援・レポーティング・ビジネス影響説明までを統合的に提供するサービスを指します。AIエージェントの普及により、SOCは「AIエージェント監視の一機能」となり、最終的にCDCに統合進化していくと想定されています。

【運営者の問題意識（today_implicationに必ず反映すること）】
- AI for Security: SOC/CDC業務へのAI活用（Tier2調査・アラート判断・ナレッジ検索・レポート作成・初動判断支援）が主な関心。AIは人を置き換えるのではなく、判断根拠・証跡・再現性を高めるものとして捉える
- Security for AI: LLM・AIエージェント・RAG・API連携・プロンプト・外部ツール実行が新たなリスク領域。AIシステム固有のログ・挙動・権限・データ流通を従来SOCの監視対象に追加する必要がある
- CDCへの進化: 単なる監視センターから「検知→分析→対応→改善→経営報告」を統合するCDCへ。AI導入でTier1/2/3の役割分担・夜間対応・エスカレーション基準・証跡管理・品質保証が変わる
- 常に問うべき観点: 攻撃側と防御側のどちらが変化しているか、既存SIEM/SOAR/MDRの限界はどこか、人間の役割はどこに残るか、これは短期的事象か中長期の構造変化か

以下のサイバーセキュリティ×AI分野のニュース記事を日本語で分析してください。
必ずJSONのみを返してください。前置き・説明文・```記号は一切不要です。

【タグ定義】（必ずこのリストから選ぶこと。リスト外のタグは絶対に使用禁止）
{tag_ref}

【AIエージェントリスク6階層モデル（参考）】
①モデル・推論層：LLM/SLMの脆弱性、プロンプトインジェクション、モデル汚染、敵対的攻撃
②ツール・実行層：ツール権限濫用、コード実行、サンドボックス脱出、MCPセキュリティ
③マルチエージェント層：エージェント間通信、合意形成、信頼境界、タスク連鎖
④データ・インフラ層：訓練データ汚染、ベクターDB、RAG、メモリ処理、データ流出
⑤アイデンティティ・権限層：認証認可、権限ギャップ、セッション管理、人間との委任関係
⑥組織・ガバナンス層：規制対応、責任範囲、監査、ポリシー、シャドーAI

【出力形式】
{{
  "articles": [
    {{
      "index": 1,
      "title_ja": "日本語タイトル（簡潔に・記事の本質を捉える）",
      "summary_ja": "3〜4文の日本語要約。背景・内容・影響の順で記述。専門用語は適切に使用",
      "insight": "CISO/経営視点での示唆。以下の観点から選んで2〜3文で記述。一般論・定型句は避け、具体的・行動可能な内容にする。",
      "importance": "高 | 中 | 低",
      "importance_reason": "重要度判断の理由を1文で",
      "tag_main_id": "attack | vuln | ai_sec | ai_risk | policy | incident | biz_tech のいずれか1つ",
      "tag_subs": ["中項目を1〜3つ。必ず上記タグ定義のリスト内から選ぶこと"],
      "affected_layers": ["この記事が最も影響するレイヤーを以下から最大3つ選ぶ: デバイス/エッジ, ネットワーク, クラウド/サーバー, アプリ/API, データ/AI, ガバナンス/規制"],
      "related_keywords": ["記事内容を表す具体的なキーワードを3〜5個（固有名詞・技術用語・組織名など）"]
    }}
  ],
  "today_implication": "★必ず以下の7セクション構造で出力。各セクションは改行で区切る。全体500〜800字。本日の記事に根拠がある事実のみ記述し、記事にないことを事実として書かない。断定しすぎず事実と推論を分ける。\n【今日の結論】記事群を横断した最重要示唆を1〜2文で。何がどう変化しているかを具体的に。\n【攻撃側の変化】攻撃手法・標的・AI悪用・サプライチェーン等の変化。本日記事に根拠があれば記述、なければ「本日は主要な攻撃側変化の言及なし」。\n【防御側の変化】SOC/SIEM/EDR/MDR/CDCの対応動向。本日の記事に根拠がある場合のみ記述。\n【Security for AI】LLM/AIエージェント/RAG/API/権限管理への示唆。関連記事なければ「本日の記事では直接言及なし」。\n【AI for Security】SOC/CDC業務でのAI活用機会または活用時の注意点。関連記事なければ「本日の記事では直接言及なし」。\n【CDC/SOCへの示唆】監視対象・ログ・検知ルール・運用プロセス・人の役割・エスカレーションへの影響。\n【今日の問い】この運営者が今後深掘りすべき問いを1〜2個。疑問文で。\n★「重要です」「注目です」など抽象的な定型句は使わない。SOC/CDC/AIセキュリティ実務に必ず接続する。"
}}

【示唆・学びの観点（記事のタイプに応じて選ぶ）】
- 脆弱性・攻撃系: どのレイヤーで何を対策すべきか、自社の類似資産への影響評価
- AI×セキュリティ系: 自社のAIシステムで同様の攻撃が成立するか、防御策の考え方
- AIリスク系: ガバナンス体制への示唆、リスク管理フレームワークへの組み込み
- 規制・政策系: コンプライアンス対応のスケジュール、先行対応の戦略的価値
- ビジネス・技術動向系: 市場トレンドからの戦略的示唆、投資判断への含意
- インシデント系: 類似事案の予防策、インシデント対応体制の見直しポイント

【重要度の基準】
高: 広範囲に影響・即時対応が必要・業界標準を変える可能性・経営レベルの判断が必要
中: 特定分野に影響・注目すべきトレンド・中期的な対応が必要
低: 参考情報・長期的な動向・個別ケースの報告

【記事一覧】
{articles_text}
"""

    # 503/429エラーに対する指数バックオフリトライ（最大5回）
    import time
    response = None
    last_error = None
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            break
        except Exception as e:
            last_error = e
            err_str = str(e)
            if '503' in err_str or 'UNAVAILABLE' in err_str or '429' in err_str:
                wait = (2 ** attempt) * 5  # 5s, 10s, 20s, 40s, 80s
                print(f"  [RETRY {attempt+1}/5] {err_str[:80]}... wait {wait}s")
                time.sleep(wait)
            else:
                raise

    if response is None:
        print(f"[SKIP] Gemini APIが混雑中のため今回はスキップします。次回の自動実行で再試行されます。")
        print(f"  最終ステータス: 503 UNAVAILABLE")
        import sys
        sys.exit(0)  # エラーではなく正常終了扱い（後続のstepもスキップされる）

    today_implication = ""
    try:
        text = response.text.strip()
        if "```" in text:
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else parts[0]
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text.strip())
        if isinstance(parsed, dict):
            today_implication = parsed.get("today_implication", "")
            summaries = parsed.get("articles", [])
        else:
            summaries = parsed  # リスト形式のフォールバック
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
            "tag_subs": [],
            "affected_layers": [],
            "related_keywords": [],
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

        raw_layers = s.get("affected_layers", [])
        clean_layers = [l for l in raw_layers if l in AFFECTED_LAYERS][:3]

        raw_keywords = s.get("related_keywords", [])
        clean_keywords = [str(k).strip() for k in raw_keywords if str(k).strip()][:5]

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
            "affected_layers":   clean_layers,
            "related_keywords":  clean_keywords,
            "views":             0,
        })
    return enriched, today_implication


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
    enriched, today_implication = summarize_with_gemini(selected)

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
    history.insert(0, {"date": today_str, "articles": enriched, "today_implication": today_implication})
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
