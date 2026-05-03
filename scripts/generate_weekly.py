# -*- coding: utf-8 -*-
"""
generate_weekly.py
過去7日間の記事データとtoday_implicationからウィークリーダイジェストJSONをGemini APIで生成する
"""

import json, os, re
from datetime import datetime, timezone, timedelta
from collections import Counter
from google import genai

JST        = timezone(timedelta(hours=9))
DATA_PATH  = "docs/data/latest.json"
WEEKLY_DIR = "docs/weekly"


def compute_keyword_changes(history):
    """過去7日と8〜14日のキーワード件数を比較して変動リストを返す"""
    now = datetime.now(JST)
    kw_this = Counter()
    kw_last = Counter()
    for day in history:
        d = day.get("date", "")
        try:
            day_dt = datetime.fromisoformat(d + "T00:00:00+09:00")
        except Exception:
            continue
        age = (now - day_dt).days
        for a in day.get("articles", []):
            for kw in a.get("related_keywords", []):
                kw = kw.strip()
                if not kw:
                    continue
                if age <= 7:
                    kw_this[kw] += 1
                elif age <= 14:
                    kw_last[kw] += 1

    all_kws = set(kw_this.keys()) | set(kw_last.keys())
    changes = []
    for kw in all_kws:
        this = kw_this.get(kw, 0)
        last = kw_last.get(kw, 0)
        change = this - last
        if change == 0:
            continue
        change_pct = round(change / max(last, 1) * 100)
        changes.append({
            "keyword": kw,
            "this_week_count": this,
            "last_week_count": last,
            "change": change,
            "change_pct": change_pct,
        })
    changes.sort(key=lambda x: -abs(x["change"]))
    return changes[:10]


def build_prompt(period_start, period_end, articles, implications, keyword_changes):
    arts_text = "\n".join(
        f"[{a['id']}] {a['date']} 重要度:{a['importance']} カテゴリ:{a['tag_main_id']}\n"
        f"  タイトル: {a['title']}\n"
        f"  示唆: {a['insight']}"
        for a in articles
    )
    impl_text = "\n".join(
        f"--- {d['date']} の示唆 ---\n{d['text']}"
        for d in implications
    ) or "（日次示唆データなし）"
    kw_text = "\n".join(
        f"  {k['keyword']}: 今週{k['this_week_count']}件 / 先週{k['last_week_count']}件"
        f" ({'+' if k['change'] >= 0 else ''}{k['change']}件)"
        for k in keyword_changes
    ) or "  （先週比データなし）"

    return f"""あなたはサイバーセキュリティ×AI領域に精通したCISOアドバイザーです。

以下は {period_start} から {period_end} の1週間のAI×セキュリティニュースの記事リストと日次示唆です。
これらを基に、CISO/セキュリティ責任者向けの週次レポートを日本語で生成してください。

【対象記事】
{arts_text}

【各日の示唆】
{impl_text}

【キーワード変動（今週vs先週）】
{kw_text}

必ず以下のJSONスキーマのみを返してください。前置き・説明文・```記号は一切不要です。

{{
  "executive_summary": "今週のAI×セキュリティ動向の総括。3〜5文。CISO/経営層が朝のブリーフィングで読める水準。事実に基づき自組織への示唆を含める。抽象的な定型句は使わない。",
  "top_topics": [
    {{
      "title": "トピックタイトル（20字以内）",
      "summary": "このトピックが今週重要だった理由と自組織への示唆（2〜3文）",
      "article_ids": ["上記 [id] から選んだ記事IDのリスト"]
    }}
  ],
  "layer_trends": [
    {{
      "layer_name": "以下6層のいずれか: デバイス/エッジ, ネットワーク, クラウド/サーバー, アプリ/API, データ/AI, ガバナンス/規制",
      "trend_text": "この層の今週の動向（1〜2文。記事がない層は「今週は主要な言及なし」）"
    }}
  ],
  "next_week_outlook": "来週注目すべきテーマや予測（2〜3文）"
}}

top_topicsは重要度が高いもの順に最大3件。layer_trendsは6層すべてを含めること。"""


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が未設定です")

    if not os.path.exists(DATA_PATH):
        print(f"[ERROR] {DATA_PATH} なし"); return

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    history = data.get("history", [])
    now = datetime.now(JST)

    # 過去7日分を抽出
    week_days = []
    for day in history:
        d = day.get("date", "")
        try:
            day_dt = datetime.fromisoformat(d + "T00:00:00+09:00")
        except Exception:
            continue
        if (now - day_dt).days <= 7:
            week_days.append(day)

    if not week_days:
        print("[WARN] 過去7日分のデータがありません"); return

    dates = sorted(d.get("date", "") for d in week_days)
    period_start  = dates[0]
    period_end    = dates[-1]
    total_articles = sum(len(d.get("articles", [])) for d in week_days)

    os.makedirs(WEEKLY_DIR, exist_ok=True)
    out_json = f"{WEEKLY_DIR}/{period_end}.json"
    if os.path.exists(out_json):
        print(f"[SKIP] {out_json} は既に存在します"); return

    keyword_changes = compute_keyword_changes(history)

    # LLM入力データを構築
    articles_input = []
    implications_input = []
    for day in sorted(week_days, key=lambda x: x.get("date", "")):
        if day.get("today_implication"):
            implications_input.append({
                "date": day["date"],
                "text": day["today_implication"],
            })
        for a in day.get("articles", []):
            articles_input.append({
                "id":         a.get("id", ""),
                "date":       day.get("date", ""),
                "title":      a.get("title_ja") or a.get("title", ""),
                "insight":    a.get("insight", ""),
                "importance": a.get("importance", "中"),
                "tag_main_id": a.get("tag_main_id", ""),
            })

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(period_start, period_end, articles_input, implications_input, keyword_changes)

    print(f"Gemini APIで週次ダイジェスト生成中... ({period_start}〜{period_end}, {total_articles}件)")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    raw = response.text.strip()

    # コードブロックが含まれていれば除去
    m = re.search(r'```(?:json)?\s*(.*?)\s*```', raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()

    weekly_data = json.loads(raw)
    weekly_data["period"]          = {"start": period_start, "end": period_end}
    weekly_data["total_articles"]  = total_articles
    weekly_data["keyword_changes"] = keyword_changes
    weekly_data["generated_at"]    = now.isoformat()

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(weekly_data, f, ensure_ascii=False, indent=2)
    print(f"週次ダイジェスト生成完了: {out_json}")


if __name__ == "__main__":
    main()
