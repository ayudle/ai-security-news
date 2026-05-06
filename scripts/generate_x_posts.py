#!/usr/bin/env python3
"""
generate_x_posts.py
当日記事からX投稿候補を生成し docs/data/ に保存する。
Phase 1-2: dry-run only。X API連携・本番投稿は行わない。

使い方:
  python generate_x_posts.py              # --all と同じ
  python generate_x_posts.py --all        # 3スロット分まとめて生成
  python generate_x_posts.py --slot morning  # morning の1本だけ生成
  python generate_x_posts.py --dry-run    # 将来の拡張用フラグ（現在は常にdry-run）
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta

DATA_PATH    = "docs/data/latest.json"
OUT_ALL      = "docs/data/x_posts_daily.json"
OUT_SLOT_TPL = "docs/data/x_post_{slot}.json"
HISTORY_PATH = "docs/data/x_post_history.json"
BASE_URL     = "https://ayudle.github.io/ai-security-news/article"
JST          = timezone(timedelta(hours=9))

SLOTS = [
    {"slot": "morning", "scheduled_time_jst": "08:30"},
    {"slot": "noon",    "scheduled_time_jst": "12:30"},
    {"slot": "evening", "scheduled_time_jst": "19:00"},
]
SLOT_INDEX = {s["slot"]: i for i, s in enumerate(SLOTS)}

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
CDC_CONTEXT_HASHTAGS: dict[str, list[str]] = {
    "Security for AI": ["AIセキュリティ", "生成AI", "LLMセキュリティ"],
    "AI for Security": ["SOC", "MDR", "サイバーセキュリティ"],
    "SOC運用変化":     ["SOC", "MDR", "サイバーセキュリティ"],
    "Identity/ITDR":   ["ITDR", "ID管理", "サイバーセキュリティ"],
    "Exposure管理":    ["CISO", "脆弱性", "サイバーセキュリティ"],
    "MDR/MSSP設計":    ["MDR", "MSSP", "サイバーセキュリティ"],
    "CISO報告":        ["CISO", "サイバーセキュリティ"],
}

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
    main_id = article.get("tag_main_id", "")
    subs    = article.get("tag_subs", []) or []
    cdc_ctx = article.get("cdc_context", []) or []
    candidates: list[str] = []

    def add(tag: str) -> None:
        if tag not in candidates:
            candidates.append(tag)

    for ctx in cdc_ctx:
        tags = CDC_CONTEXT_HASHTAGS.get(ctx, [])
        if tags:
            add(tags[0])
            break

    for s in subs:
        if len(candidates) >= 3:
            break
        if s in HASHTAG_MAP:
            add(HASHTAG_MAP[s])

    if len(candidates) < 3:
        for ctx in cdc_ctx:
            for tag in CDC_CONTEXT_HASHTAGS.get(ctx, []):
                add(tag)
                if len(candidates) >= 3:
                    break
            if len(candidates) >= 3:
                break

    if len(candidates) < 3:
        for tag in PRIMARY_TAG_BY_MAIN.get(main_id, ["サイバーセキュリティ"]):
            add(tag)
            if len(candidates) >= 3:
                break

    return [f"#{t}" for t in candidates[:3]]


# ── 投稿文生成 ────────────────────────────────────────────────────────────

def _is_natural_ending(text: str) -> bool:
    return bool(text) and text[-1] not in _BAD_ENDING


def _first_sentence(text: str) -> str:
    idx = text.find("。")
    return text[:idx + 1] if idx >= 0 else text


def _natural_cut(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    idx = window.rfind("。")
    if idx >= max_chars // 2:
        return window[:idx + 1]
    idx = window.rfind("、")
    if idx >= max_chars // 2:
        return window[:idx] + "…"
    stripped = window.rstrip("".join(_BAD_ENDING))
    if stripped and len(stripped) >= max_chars // 2:
        return stripped + "…"
    return window[: max(max_chars - 1, 1)] + "…"


def _extract_insight(article: dict, budget: int) -> str:
    main_id = article.get("tag_main_id", "")
    fallback_candidate: str | None = None

    for key in ("insight", "summary_ja", "importance_reason"):
        raw = (article.get(key) or "").strip()
        if not raw:
            continue
        first = _first_sentence(raw)
        if len(first) <= budget and _is_natural_ending(first):
            return first
        cut = _natural_cut(raw, budget)
        if _is_natural_ending(cut):
            return cut
        if fallback_candidate is None:
            fallback_candidate = cut

    fallback = FALLBACK_SENTENCES.get(main_id, FALLBACK_DEFAULT)
    if len(fallback) <= budget:
        return fallback
    return _first_sentence(fallback)


def build_post_text(article: dict, hashtags: list[str]) -> str:
    title = (article.get("title_ja") or article.get("title") or "").strip()
    url   = f"{BASE_URL}/{article['id']}.html"

    def _overhead(title_str: str, tags_str: str) -> int:
        return (
            len("【AI×セキュリティ】\n\n")
            + len(title_str) + len("\n\n")
            + len("\n\n") + len(url) + len("\n")
            + len(tags_str)
        )

    def _compose(title_str: str, insight: str, tags_str: str) -> str:
        return f"【AI×セキュリティ】\n\n{title_str}\n\n{insight}\n\n{url}\n{tags_str}"

    TARGET  = 260
    MINIMUM = 280
    tags_full = " ".join(hashtags)
    tags_2    = " ".join(hashtags[:2])

    for tags_str in (tags_full, tags_2):
        budget = TARGET - _overhead(title, tags_str)
        if budget >= 10:
            insight = _extract_insight(article, budget)
            text = _compose(title, insight, tags_str)
            if len(text) <= TARGET:
                return text

    short_title = _natural_cut(title, 35)
    budget = TARGET - _overhead(short_title, tags_2)
    if budget >= 10:
        insight = _extract_insight(article, budget)
        text = _compose(short_title, insight, tags_2)
        if len(text) <= MINIMUM:
            return text

    insight = _extract_insight(article, 30)
    text = _compose(short_title, insight, tags_2)
    return text[:277] + "…" if len(text) > MINIMUM else text


# ── 投稿オブジェクト生成 ─────────────────────────────────────────────────

def _make_post(slot_info: dict, article: dict) -> dict:
    aid      = article["id"]
    hashtags = build_hashtags(article)
    text     = build_post_text(article, hashtags)
    return {
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
    }


def _print_post(p: dict) -> None:
    bar = "─" * 60
    print(bar)
    print(
        f"[{p['slot'].upper()}] {p['scheduled_time_jst']} JST"
        f" | score={p['score']} | {p['char_count']}文字"
        f" | {p['source_name']} ({p['importance']})"
    )
    print(bar)
    print(p["text"])
    print()


# ── 履歴管理 ─────────────────────────────────────────────────────────────

def _update_history(post: dict, date_str: str, generated_at: str) -> None:
    text_hash = hashlib.sha256(post["text"].encode("utf-8")).hexdigest()[:16]
    entry = {
        "date":         date_str,
        "slot":         post["slot"],
        "article_id":   post["article_id"],
        "text_hash":    text_hash,
        "status":       "dry_run_generated",
        "generated_at": generated_at,
    }

    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            hist = json.load(f)
    else:
        hist = {"history": []}

    dedup = (entry["date"], entry["slot"], entry["article_id"], entry["text_hash"])
    for existing in hist["history"]:
        if (existing.get("date"), existing.get("slot"),
                existing.get("article_id"), existing.get("text_hash")) == dedup:
            print(f"[HISTORY] 同一エントリが既に存在します。スキップ: {entry['date']} / {entry['slot']}")
            return

    hist["history"].append(entry)
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
    print(f"[HISTORY] 履歴を追記しました: {entry['date']} / {entry['slot']} / {entry['article_id']}")


# ── CLI引数 ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="X投稿文dry-run生成スクリプト（Phase 1-2）"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--all", dest="mode_all", action="store_true",
        help="3スロット分まとめて生成（デフォルト）"
    )
    group.add_argument(
        "--slot", choices=["morning", "noon", "evening"],
        help="指定スロット1本を生成し履歴に記録する"
    )
    parser.add_argument(
        "--dry-run", dest="dry_run", action="store_true", default=True,
        help="dry-runモード（現在は常にdry-run、将来拡張用）"
    )
    args = parser.parse_args()
    if not args.slot:
        args.mode_all = True
    return args


# ── メイン ────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    if not os.path.exists(DATA_PATH):
        print(
            f"[ERROR] {DATA_PATH} が見つかりません。"
            "先に fetch_and_summarize.py を実行してください。"
        )
        sys.exit(1)

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    articles  = data.get("articles", []) or []
    now_jst   = datetime.now(JST)
    date_str  = now_jst.strftime("%Y-%m-%d")
    generated = now_jst.isoformat()
    ranked    = sorted(articles, key=_sort_key) if articles else []

    # ── --all モード ──────────────────────────────────────────────────────
    if args.mode_all:
        posts = []
        for slot_info, article in zip(SLOTS, ranked[:3]):
            posts.append(_make_post(slot_info, article))

        output = {
            "date":         date_str,
            "generated_at": generated,
            "mode":         "dry_run",
            "posts":        posts,
        }
        os.makedirs(os.path.dirname(OUT_ALL), exist_ok=True)
        with open(OUT_ALL, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"[OK] {OUT_ALL} 出力完了（{len(posts)}本 / dry_run）")
        print()
        for p in posts:
            _print_post(p)
        return

    # ── --slot モード ─────────────────────────────────────────────────────
    slot_name = args.slot
    slot_idx  = SLOT_INDEX[slot_name]
    slot_info = SLOTS[slot_idx]
    out_path  = OUT_SLOT_TPL.format(slot=slot_name)

    if slot_idx >= len(ranked):
        print(
            f"[WARN] スロット '{slot_name}' に対応する記事がありません"
            f"（記事数: {len(ranked)}）"
        )
        output: dict = {
            "date":         date_str,
            "generated_at": generated,
            "mode":         "dry_run",
            "slot":         slot_name,
            "post":         None,
        }
    else:
        article = ranked[slot_idx]
        post    = _make_post(slot_info, article)
        output  = {
            "date":         date_str,
            "generated_at": generated,
            "mode":         "dry_run",
            "slot":         slot_name,
            "post":         post,
        }
        print(f"[OK] {slot_name} スロット生成完了")
        print()
        _print_post(post)
        _update_history(post, date_str, generated)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[OK] {out_path} 出力完了")


if __name__ == "__main__":
    main()
