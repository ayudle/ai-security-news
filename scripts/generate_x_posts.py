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
# cdc_context ごとに優先タグを最大3つ定義（先頭が最優先）
CDC_CONTEXT_HASHTAGS: dict[str, list[str]] = {
    "Security for AI": ["AIセキュリティ", "生成AI", "LLMセキュリティ"],
    "AI for Security": ["SOC", "MDR", "サイバーセキュリティ"],
    "SOC運用変化":     ["SOC", "MDR", "サイバーセキュリティ"],
    "Identity/ITDR":   ["ITDR", "ID管理", "サイバーセキュリティ"],
    "Exposure管理":    ["CISO", "脆弱性", "サイバーセキュリティ"],
    "MDR/MSSP設計":    ["MDR", "MSSP", "サイバーセキュリティ"],
    "CISO報告":        ["CISO", "サイバーセキュリティ"],
}

# 記事タイプ別フォールバック示唆文（自然な句点終わり）
FALLBACK_SENTENCES: dict[str, str] = {
    "ai_sec":   "AIシステムのセキュリティ評価と継続的な監視が求められます。",
    "ai_risk":  "AI活用に伴うリスク管理体制の整備が重要です。",
    "vuln":     "脆弱性への迅速な対応と継続的なパッチ管理が必要です。",
    "attack":   "攻撃手法の把握と防御策の見直しが求められます。",
    "incident": "インシデント対応プロセスの確認と見直しが必要です。",
    "policy":   "規制動向を踏まえたセキュリティポリシーの更新が求められます。",
    "biz_tech": "業界動向を踏まえたセキュリティ戦略の検討が重要です。",
}
FALLBACK_DEFAULT = "セキュリティ対策の見直しと最新動向の確認が重要です。"

# 文末として不自然な文字（助詞・助動詞語幹など）
_BAD_ENDING = frozenset("すしをにはがでとのなたらりれるく")


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
    """
    ハッシュタグを最大3個生成する。
    優先順位:
      1. 最初にマッチした cdc_context の先頭タグ（主文脈を示す1個）
      2. tag_subs 由来の具体タグ（記事内容に近い）
      3. cdc_context の2番目以降のタグで補完
      4. tag_main_id 由来で補完
    """
    main_id = article.get("tag_main_id", "")
    subs    = article.get("tag_subs", []) or []
    cdc_ctx = article.get("cdc_context", []) or []

    candidates: list[str] = []

    def add(tag: str) -> None:
        if tag not in candidates:
            candidates.append(tag)

    # 1. 最初にマッチした cdc_context の先頭タグ（1個）
    for ctx in cdc_ctx:
        tags = CDC_CONTEXT_HASHTAGS.get(ctx, [])
        if tags:
            add(tags[0])
            break

    # 2. tag_subs 由来の具体タグ
    for s in subs:
        if len(candidates) >= 3:
            break
        if s in HASHTAG_MAP:
            add(HASHTAG_MAP[s])

    # 3. cdc_context の残りタグで補完
    if len(candidates) < 3:
        for ctx in cdc_ctx:
            for tag in CDC_CONTEXT_HASHTAGS.get(ctx, []):
                add(tag)
                if len(candidates) >= 3:
                    break
            if len(candidates) >= 3:
                break

    # 4. tag_main_id 由来で補完
    if len(candidates) < 3:
        for tag in PRIMARY_TAG_BY_MAIN.get(main_id, ["サイバーセキュリティ"]):
            add(tag)
            if len(candidates) >= 3:
                break

    return [f"#{t}" for t in candidates[:3]]


# ── 投稿文生成 ────────────────────────────────────────────────────────────

def _is_natural_ending(text: str) -> bool:
    """投稿文として自然に終わっているか確認する。"""
    if not text:
        return False
    return text[-1] not in _BAD_ENDING


def _first_sentence(text: str) -> str:
    """テキストの最初の文（句点まで）を返す。句点がなければ全文。"""
    idx = text.find("。")
    return text[:idx + 1] if idx >= 0 else text


def _natural_cut(text: str, max_chars: int) -> str:
    """
    max_chars 以内で自然な位置で切る。
    句点 > 読点 > 末尾不自然文字を除去 の順で試みる。
    """
    if not text:
        return ""
    if len(text) <= max_chars:
        return text

    window = text[:max_chars]

    # 1. 句点で切る（最も自然）
    idx = window.rfind("。")
    if idx >= max_chars // 2:
        return window[:idx + 1]

    # 2. 読点で切り「…」を付ける
    idx = window.rfind("、")
    if idx >= max_chars // 2:
        return window[:idx] + "…"

    # 3. 末尾の不自然な文字を除いて「…」を付ける
    stripped = window.rstrip("".join(_BAD_ENDING))
    if stripped and len(stripped) >= max_chars // 2:
        return stripped + "…"

    # 4. 強制カット（最終手段）
    return window[: max(max_chars - 1, 1)] + "…"


def _extract_insight(article: dict, budget: int) -> str:
    """
    投稿用の示唆文を budget 文字以内で抽出する。
    優先順位:
      1. insight の最初の1文（句点まで）→ budget以内かつ自然な終わりなら即採用
      2. insight を自然に短縮
      3. summary_ja の最初の1文
      4. summary_ja を自然に短縮
      5. importance_reason
      6. 記事タイプ別汎用文
    """
    main_id = article.get("tag_main_id", "")
    fallback_candidate: str | None = None

    for key in ("insight", "summary_ja", "importance_reason"):
        raw = (article.get(key) or "").strip()
        if not raw:
            continue

        # 最初の1文を試みる（句点で終わる最も自然な形）
        first = _first_sentence(raw)
        if len(first) <= budget and _is_natural_ending(first):
            return first

        # 自然な短縮を試みる
        cut = _natural_cut(raw, budget)
        if _is_natural_ending(cut):
            return cut

        # 自然な終わりにならなかった場合は次のキーで再試行、最初の候補だけ保持
        if fallback_candidate is None:
            fallback_candidate = cut

    # 記事タイプ別汎用文
    fallback = FALLBACK_SENTENCES.get(main_id, FALLBACK_DEFAULT)
    if len(fallback) <= budget:
        return fallback

    # 汎用文も長ければ最初の文を返す（句点で終わるため自然）
    return _first_sentence(fallback)


def build_post_text(article: dict, hashtags: list[str]) -> str:
    """280文字以内（260文字目標）の投稿文を生成する。"""
    title = (article.get("title_ja") or article.get("title") or "").strip()
    url   = f"{BASE_URL}/{article['id']}.html"

    # テンプレートのオーバーヘッド（示唆文以外の固定部分）
    # 「【AI×セキュリティ】\n\n」+ title + 「\n\n」+ insight + 「\n\n」+ url + 「\n」+ tags
    def _overhead(title_str: str, tags_str: str) -> int:
        return (
            len("【AI×セキュリティ】\n\n")
            + len(title_str)
            + len("\n\n")   # after title
            + len("\n\n")   # after insight
            + len(url)
            + len("\n")
            + len(tags_str)
        )

    def _compose(title_str: str, insight: str, tags_str: str) -> str:
        return f"【AI×セキュリティ】\n\n{title_str}\n\n{insight}\n\n{url}\n{tags_str}"

    TARGET  = 260
    MINIMUM = 280

    tags_full = " ".join(hashtags)
    tags_2    = " ".join(hashtags[:2])

    # Step 1: フルタイトル + 3タグ
    budget = TARGET - _overhead(title, tags_full)
    if budget >= 10:
        insight = _extract_insight(article, budget)
        text = _compose(title, insight, tags_full)
        if len(text) <= TARGET:
            return text

    # Step 2: フルタイトル + 2タグ
    budget = TARGET - _overhead(title, tags_2)
    if budget >= 10:
        insight = _extract_insight(article, budget)
        text = _compose(title, insight, tags_2)
        if len(text) <= TARGET:
            return text

    # Step 3: タイトルを35文字に短縮 + 2タグ
    short_title = _natural_cut(title, 35)
    budget = TARGET - _overhead(short_title, tags_2)
    if budget >= 10:
        insight = _extract_insight(article, budget)
        text = _compose(short_title, insight, tags_2)
        if len(text) <= MINIMUM:
            return text

    # 最終フォールバック: 強制カット
    insight = _extract_insight(article, 30)
    text = _compose(short_title, insight, tags_2)
    return text[:277] + "…" if len(text) > MINIMUM else text


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
            aid      = article["id"]
            hashtags = build_hashtags(article)
            text     = build_post_text(article, hashtags)
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
