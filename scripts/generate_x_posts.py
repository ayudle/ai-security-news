#!/usr/bin/env python3
"""
generate_x_posts.py
当日記事からX投稿候補を1日3本分生成し docs/data/x_posts_daily.json に保存する。
Phase 1: dry-run only。X API連携・本番投稿は行わない。
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

DATA_PATH = "docs/data/latest.json"
OUT_PATH  = "docs/data/x_posts_daily.json"
BASE_URL  = "https://ayudle.github.io/ai-security-news/article"
JST       = timezone(timedelta(hours=9))

SLOTS = [
    {"slot": "morning", "scheduled_time_jst": "08:30"},
    {"slot": "noon",    "scheduled_time_jst": "12:30"},
    {"slot": "evening", "scheduled_time_jst": "19:00"},
]

# ── スコアリング ───────────────────────────────────────────────────────────
IMPORTANCE_SCORE = {"高": 3, "中": 1, "低": 0}
TIER_SCORE       = {"A": 2, "B": 1, "C": 0}
CDC_CONTEXT_PRIORITY = {
    "Security for AI": 3,
    "AI for Security": 3,
    "SOC運用変化":      2,
    "Identity/ITDR":   2,
    "Exposure管理":    2,
    "MDR/MSSP設計":    2,
    "サービス企画":     1,
    "顧客課題":         1,
    "CISO報告":         1,
}

# ── ハッシュタグ ───────────────────────────────────────────────────────────
PRIMARY_TAG_BY_MAIN = {
    "ai_sec":   ["AIセキュリティ"],
    "ai_risk":  ["AIリスク", "AIガバナンス"],
    "vuln":     ["脆弱性", "サイバーセキュリティ"],
    "attack":   ["サイバー攻撃", "サイバーセキュリティ"],
    "incident": ["セキュリティインシデント", "サイバーセキュリティ"],
    "policy":   ["セキュリティ規制", "サイバーセキュリティ"],
    "biz_tech": ["セキュリティ業界", "サイバーセキュリティ"],
}
HASHTAG_MAP = {
    "プロンプトインジェクション": "プロンプトインジェクション",
    "LLMセキュリティ":           "LLMセキュリティ",
    "モデル汚染":                "モデル汚染",
    "敵対的攻撃":                "敵対的攻撃",
    "AIを使った攻撃":            "AI攻撃",
    "AIを使った防御":            "AI防御",
    "ハルシネーション":           "ハルシネーション",
    "EU AI法":                   "EUAI法",
    "コンプライアンス":           "AIコンプライアンス",
    "標準化":                    "AI標準化",
    "安全性評価":                "AI安全性",
    "アライメント":               "アライメント",
    "プライバシー侵害":           "プライバシー",
    "サプライチェーン攻撃":       "サプライチェーン",
    "モデル逆転攻撃":            "モデル逆転",
    "バイアス・差別":            "AIバイアス",
    "誤情報生成":                "AI誤情報",
    "著作権":                    "AI著作権",
}
CDC_CONTEXT_HASHTAGS = {
    "Security for AI": ["AIセキュリティ", "生成AI"],
    "AI for Security": ["AIセキュリティ", "SOC"],
    "SOC運用変化":     ["SOC", "サイバーセキュリティ"],
    "Identity/ITDR":   ["ITDR", "サイバーセキュリティ"],
    "Exposure管理":    ["CISO", "サイバーセキュリティ"],
    "MDR/MSSP設計":    ["MDR", "MSSP"],
}


# ── スコアリング関数 ───────────────────────────────────────────────────────

def _score(article: dict) -> int:
    imp  = IMPORTANCE_SCORE.get(article.get("importance", ""), 0)
    tier = TIER_SCORE.get(article.get("source_tier", ""), 0)
    cdc  = article.get("cdc_relevance", 0)
    ai   = article.get("ai_score", 0)
    ctx  = max(
        (CDC_CONTEXT_PRIORITY.get(c, 0) for c in article.get("cdc_context", [])),
        default=0,
    )
    return imp * 3 + cdc * 2 + ctx * 2 + tier + ai


def _pub_ts(article: dict) -> float:
    try:
        return datetime.fromisoformat(article.get("published", "")).timestamp()
    except Exception:
        return 0.0


def _sort_key(article: dict) -> tuple:
    return (
        -_score(article),
        {"A": 0, "B": 1, "C": 2}.get(article.get("source_tier", "B"), 9),
        -_pub_ts(article),
        article.get("id", ""),
    )


# ── ハッシュタグ生成 ───────────────────────────────────────────────────────

def build_hashtags(article: dict) -> list[str]:
    main_id = article.get("tag_main_id", "")
    subs    = article.get("tag_subs", []) or []
    cdc_ctx = article.get("cdc_context", []) or []

    candidates: list[str] = []

    def add(tag: str) -> None:
        if tag not in candidates:
            candidates.append(tag)

    # 1. tag_main_id → 主軸タグ
    for tag in PRIMARY_TAG_BY_MAIN.get(main_id, ["サイバーセキュリティ"]):
        add(tag)

    # 2. cdc_context → CDC文脈タグ
    for ctx in cdc_ctx:
        for tag in CDC_CONTEXT_HASHTAGS.get(ctx, []):
            add(tag)

    # 3. tag_subs → サブタグ
    for s in subs:
        if s in HASHTAG_MAP:
            add(HASHTAG_MAP[s])

    return [f"#{t}" for t in candidates[:3]]


# ── 投稿文生成 ────────────────────────────────────────────────────────────

def _truncate(text: str, max_chars: int) -> str:
    """句点単位で短縮し max_chars 以内に収める。"""
    if not text or len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    idx = cut.rfind("。")
    if idx >= max_chars // 2:
        return cut[: idx + 1]
    return cut + "…"


def _insight_text(article: dict) -> str:
    for key in ("insight", "summary_ja", "importance_reason"):
        val = (article.get(key) or "").strip()
        if val:
            return val
    return ""


def _compose(title: str, insight: str, url: str, tags_str: str) -> str:
    return f"【AI×セキュリティ】\n\n{title}\n\n{insight}\n\n{url}\n{tags_str}"


def build_post_text(article: dict, hashtags: list[str]) -> str:
    title     = (article.get("title_ja") or article.get("title") or "").strip()
    url       = f"{BASE_URL}/{article['id']}.html"
    raw       = _insight_text(article)
    tags_full = " ".join(hashtags)
    tags_2    = " ".join(hashtags[:2])

    # 段階的に短縮して 260 文字以内を目指す（最終的に 280 文字以内に強制）
    for insight_len, tags_str, title_len in [
        (70, tags_full, None),   # Step 1: 基本
        (50, tags_full, None),   # Step 2: 示唆文を短縮
        (50, tags_2,    None),   # Step 3: ハッシュタグを2個に
        (50, tags_2,    40),     # Step 4: タイトルも短縮
    ]:
        t = _truncate(title, title_len) if title_len else title
        ins = _truncate(raw, insight_len)
        text = _compose(t, ins, url, tags_str)
        if len(text) <= 260:
            return text

    # 最終フォールバック: 280 文字に強制カット
    text = _compose(
        _truncate(title, 40),
        _truncate(raw, 40),
        url,
        tags_2,
    )
    if len(text) > 280:
        text = text[:277] + "…"
    return text


# ── メイン ────────────────────────────────────────────────────────────────

def main() -> None:
    if not os.path.exists(DATA_PATH):
        print(f"[ERROR] {DATA_PATH} が見つかりません。先に fetch_and_summarize.py を実行してください。")
        sys.exit(1)

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    articles  = data.get("articles", []) or []
    now_jst   = datetime.now(JST)
    date_str  = now_jst.strftime("%Y-%m-%d")
    generated = now_jst.isoformat()

    posts: list[dict] = []

    if not articles:
        print("[WARN] 記事が0件です。posts: [] で出力します。")
    else:
        top3 = sorted(articles, key=_sort_key)[:3]

        for slot_info, article in zip(SLOTS, top3):
            aid       = article["id"]
            hashtags  = build_hashtags(article)
            text      = build_post_text(article, hashtags)
            posts.append({
                "slot":               slot_info["slot"],
                "scheduled_time_jst": slot_info["scheduled_time_jst"],
                "article_id":         aid,
                "article_title":      (article.get("title_ja") or article.get("title", "")).strip(),
                "article_page_url":   f"{BASE_URL}/{aid}.html",
                "source_name":        article.get("source_name", ""),
                "importance":         article.get("importance", ""),
                "cdc_relevance":      article.get("cdc_relevance", 0),
                "score":              _score(article),
                "hashtags":           hashtags,
                "text":               text,
                "char_count":         len(text),
                "status":             "dry_run",
            })

    output = {
        "date":         date_str,
        "generated_at": generated,
        "mode":         "dry_run",
        "posts":        posts,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[OK] {OUT_PATH} 出力完了（{len(posts)}本 / dry_run）")
    print()

    for p in posts:
        bar = "─" * 60
        print(bar)
        print(f"[{p['slot'].upper()}] {p['scheduled_time_jst']} JST | score={p['score']} | {p['char_count']}文字 | {p['source_name']} ({p['importance']})")
        print(bar)
        print(p["text"])
        print()


if __name__ == "__main__":
    main()
