#!/usr/bin/env python3
"""
generate_x_posts.py
当日記事からX投稿候補を生成し、オプションでXへ本番投稿する。
Phase 1-3: --post を指定したときのみX APIへ投稿。デフォルトはdry-run。

使い方:
  python generate_x_posts.py                      # --all と同じ（dry-run）
  python generate_x_posts.py --all --dry-run      # 3スロット分まとめて生成
  python generate_x_posts.py --slot morning       # morning の1本生成・履歴記録（dry-run）
  python generate_x_posts.py --slot morning --post  # morning をX APIへ実際に投稿
  python generate_x_posts.py --slot morning --post --force  # 投稿済みでも強制再投稿

安全仕様:
  - --post なしでは絶対にX APIを呼ばない
  - --all --post は禁止（複数本同時投稿を防ぐ）
  - --post には --slot が必須
  - 投稿文が280文字を超える場合は投稿しない
  - 必要な環境変数が未設定なら投稿しない
  - 同じ date+slot が既に posted の場合は --force なしでスキップ
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
X_API_URL    = "https://api.x.com/2/tweets"
X_VERIFY_URL = "https://api.x.com/2/users/me"
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

def _load_history() -> dict:
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"history": []}


def _save_history(hist: dict) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _update_history(post: dict, date_str: str, generated_at: str) -> None:
    """dry-run生成を履歴に追記（重複チェックあり）。"""
    entry = {
        "date":         date_str,
        "slot":         post["slot"],
        "article_id":   post["article_id"],
        "text_hash":    _text_hash(post["text"]),
        "status":       "dry_run_generated",
        "generated_at": generated_at,
    }
    hist  = _load_history()
    dedup = (entry["date"], entry["slot"], entry["article_id"], entry["text_hash"])
    for existing in hist["history"]:
        if (existing.get("date"), existing.get("slot"),
                existing.get("article_id"), existing.get("text_hash")) == dedup:
            print(f"[HISTORY] 同一エントリが既に存在します。スキップ: {entry['date']} / {entry['slot']}")
            return
    hist["history"].append(entry)
    _save_history(hist)
    print(f"[HISTORY] 履歴を追記しました: {entry['date']} / {entry['slot']} / {entry['article_id']}")


def _check_already_posted(slot_name: str, date_str: str) -> bool:
    """同じ date+slot で status==posted のレコードが存在するか確認する。"""
    hist = _load_history()
    return any(
        e.get("date") == date_str
        and e.get("slot") == slot_name
        and e.get("status") == "posted"
        for e in hist["history"]
    )


def _record_posted(
    post: dict, tweet_id: str, date_str: str, generated_at: str, posted_at: str
) -> None:
    entry = {
        "date":         date_str,
        "slot":         post["slot"],
        "article_id":   post["article_id"],
        "text_hash":    _text_hash(post["text"]),
        "status":       "posted",
        "tweet_id":     tweet_id,
        "posted_at":    posted_at,
        "generated_at": generated_at,
    }
    hist = _load_history()
    hist["history"].append(entry)
    _save_history(hist)
    print(f"[HISTORY] posted を記録しました: tweet_id={tweet_id}")


def _record_failed(
    post: dict, error: str, date_str: str, generated_at: str, failed_at: str
) -> None:
    entry = {
        "date":         date_str,
        "slot":         post["slot"],
        "article_id":   post["article_id"],
        "text_hash":    _text_hash(post["text"]),
        "status":       "failed",
        "error":        error,
        "failed_at":    failed_at,
        "generated_at": generated_at,
    }
    hist = _load_history()
    hist["history"].append(entry)
    _save_history(hist)
    print(f"[HISTORY] failed を記録しました: {error}")


# ── X API共通：OAuth認証ヘルパー ─────────────────────────────────────────

def _make_oauth1() -> "OAuth1":
    """環境変数からOAuth1オブジェクトを生成する。Secrets値はログに出さない。"""
    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        raise RuntimeError(
            "requests-oauthlib が未インストールです。"
            "`pip install requests-oauthlib` を実行してください。"
        )
    required_vars = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"環境変数が未設定です: {', '.join(missing)}")
    return OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )


# ── アカウント確認 ────────────────────────────────────────────────────────

def _get_account_info() -> tuple[str, str, str]:
    """
    X API v2 (GET /2/users/me) で投稿先アカウント情報を取得する。
    戻り値: (username, user_id, name)
    Secrets の値はログに出力しない。
    """
    try:
        import requests
    except ImportError:
        raise RuntimeError("requests が未インストールです。")

    try:
        auth = _make_oauth1()
    except RuntimeError:
        raise

    try:
        resp = requests.get(X_VERIFY_URL, auth=auth, timeout=20)
    except Exception as e:
        raise RuntimeError(f"リクエスト例外: {type(e).__name__}")

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")

    data = resp.json().get("data", {})
    username = data.get("username", "")
    user_id  = data.get("id", "")
    name     = data.get("name", "")
    if not username:
        raise RuntimeError("レスポンスに username が含まれていませんでした")
    return username, user_id, name


# ── X API投稿 ────────────────────────────────────────────────────────────

def _post_to_x(text: str) -> tuple[bool, str, str]:
    """
    X API v2 (POST /2/tweets) へ OAuth 1.0a で投稿する。
    戻り値: (success, tweet_id, error_message)
    APIキーは環境変数から取得。ログに値は出力しない。
    """
    try:
        import requests
    except ImportError:
        return False, "", "requests が未インストールです。"

    try:
        auth = _make_oauth1()
    except RuntimeError as e:
        return False, "", str(e)

    try:
        resp = requests.post(
            X_API_URL,
            json={"text": text},
            auth=auth,
            timeout=20,
        )
    except Exception as e:
        return False, "", f"リクエスト例外: {type(e).__name__}"

    if resp.status_code == 201:
        data = resp.json().get("data", {})
        tweet_id = data.get("id", "")
        if not tweet_id:
            return False, "", "レスポンスに tweet id が含まれていませんでした"
        return True, tweet_id, ""

    # エラー時はステータスコードのみ記録（レスポンス本文は機密情報を含む可能性があるため省略）
    return False, "", f"HTTP {resp.status_code}"


# ── ファイル出力 ──────────────────────────────────────────────────────────

def _write_slot_json(out_path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] {out_path} 出力完了")


# ── CLI引数 ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="X投稿文生成・投稿スクリプト（Phase 3）"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--all", dest="mode_all", action="store_true",
        help="3スロット分まとめて生成（dry-runのみ、--post不可）"
    )
    mode_group.add_argument(
        "--slot", choices=["morning", "noon", "evening"],
        help="指定スロット1本を生成する"
    )
    parser.add_argument(
        "--post", action="store_true", default=False,
        help="X APIへ実際に投稿する（--slot と組み合わせて使う。--all と同時使用禁止）"
    )
    parser.add_argument(
        "--force", action="store_true", default=False,
        help="同じ date+slot が already posted でも強制再投稿する（--post と組み合わせて使う）"
    )
    parser.add_argument(
        "--dry-run", dest="dry_run", action="store_true", default=False,
        help="dry-runモード（--post なしのデフォルト動作と同じ、将来拡張用）"
    )
    parser.add_argument(
        "--verify-account", dest="verify_account", action="store_true", default=False,
        help="X APIアカウント情報（username/id/name）を表示して終了する（投稿しない）"
    )

    args = parser.parse_args()

    # ── バリデーション ────────────────────────────────────────────────────
    if args.verify_account and (args.post or args.force or args.slot or args.mode_all):
        parser.error("--verify-account は単独で使用してください。")
    if args.post and args.mode_all:
        parser.error("--all --post は禁止です。--slot morning|noon|evening を指定してください。")
    if args.post and not args.slot:
        parser.error("--post には --slot morning|noon|evening が必要です。")
    if args.force and not args.post:
        parser.error("--force は --post と組み合わせて使ってください。")

    # デフォルト: --all
    if not args.slot:
        args.mode_all = True

    return args


# ── メイン ────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    # ── --verify-account: アカウント確認して終了 ──────────────────────────
    if args.verify_account:
        print("[VERIFY] X APIアカウント情報を取得します...")
        try:
            username, user_id, name = _get_account_info()
            print(f"[OK] @{username}  (id={user_id}, name={name})")
            print("     ↑ 本番投稿前にこのアカウントが正しいか確認してください。")
        except RuntimeError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)
        return

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

    # ──────────────────────────────────────────────────────────────────────
    # --all モード（dry-runのみ、投稿なし）
    # ──────────────────────────────────────────────────────────────────────
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

    # ──────────────────────────────────────────────────────────────────────
    # --slot モード
    # ──────────────────────────────────────────────────────────────────────
    slot_name = args.slot
    slot_idx  = SLOT_INDEX[slot_name]
    slot_info = SLOTS[slot_idx]
    out_path  = OUT_SLOT_TPL.format(slot=slot_name)

    if slot_idx >= len(ranked):
        print(
            f"[WARN] スロット '{slot_name}' に対応する記事がありません"
            f"（記事数: {len(ranked)}）"
        )
        _write_slot_json(out_path, {
            "date":         date_str,
            "generated_at": generated,
            "mode":         "dry_run",
            "slot":         slot_name,
            "post":         None,
        })
        return

    article = ranked[slot_idx]
    post    = _make_post(slot_info, article)

    print(f"[{'POST' if args.post else 'DRY-RUN'}] {slot_name} スロット")
    print()
    _print_post(post)

    # ── dry-run ───────────────────────────────────────────────────────────
    if not args.post:
        _update_history(post, date_str, generated)
        _write_slot_json(out_path, {
            "date":         date_str,
            "generated_at": generated,
            "mode":         "dry_run",
            "slot":         slot_name,
            "post":         post,
        })
        return

    # ── 本番投稿（--post）────────────────────────────────────────────────

    # 安全チェック 1: 文字数
    if post["char_count"] > 280:
        print(
            f"[ERROR] 投稿文が280文字を超えています（{post['char_count']}字）。"
            "投稿を中止します。"
        )
        sys.exit(1)

    # 安全チェック 2: 二重投稿防止
    if not args.force and _check_already_posted(slot_name, date_str):
        print(
            f"[SKIP] {date_str} / {slot_name} は既に投稿済みです。"
            "--force を指定すると強制再投稿できます。"
        )
        sys.exit(0)

    # 投稿先アカウント確認
    print("[VERIFY] 投稿先アカウントを確認します...")
    try:
        username, user_id, _ = _get_account_info()
        print(f"[OK] 投稿先: @{username} (id={user_id})")
    except RuntimeError as e:
        print(f"[ERROR] アカウント確認に失敗しました: {e}")
        sys.exit(1)

    # X API 投稿
    print("[POST] X APIへ投稿します...")
    success, tweet_id, error = _post_to_x(post["text"])
    action_at = datetime.now(JST).isoformat()

    if success:
        print(f"[OK] 投稿成功: tweet_id={tweet_id}")
        post["status"]   = "posted"
        post["tweet_id"] = tweet_id
        _record_posted(post, tweet_id, date_str, generated, action_at)
        _write_slot_json(out_path, {
            "date":         date_str,
            "generated_at": generated,
            "mode":         "posted",
            "slot":         slot_name,
            "post":         post,
        })

    else:
        print(f"[ERROR] 投稿失敗: {error}")
        post["status"] = "failed"
        post["error"]  = error
        _record_failed(post, error, date_str, generated, action_at)
        _write_slot_json(out_path, {
            "date":         date_str,
            "generated_at": generated,
            "mode":         "failed",
            "slot":         slot_name,
            "post":         post,
        })
        sys.exit(1)


if __name__ == "__main__":
    main()
