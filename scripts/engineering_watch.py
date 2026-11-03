"""診断技術と評価手法の最近の記事を、既存データから独立して表示する。"""
from datetime import datetime, timedelta, timezone
from html import escape

from engineering import engineering_topics


def render(history, safe_id):
    cutoff = datetime.now(timezone(timedelta(hours=9))).date() - timedelta(days=29)
    rows = []
    seen = set()
    for day in history:
        try:
            day_date = datetime.fromisoformat(day.get("date", "")).date()
        except ValueError:
            continue
        if day_date < cutoff:
            continue
        for article in day.get("articles", []):
            article_id = safe_id(article.get("id", ""))
            if not article_id or article_id in seen:
                continue
            seen.add(article_id)
            topics = article.get("engineering_topics") or engineering_topics(
                article.get("title", ""), article.get("summary", ""))
            if topics:
                rows.append((day.get("date", ""), article, article_id, topics))
    rows.sort(key=lambda row: (row[0], row[1].get("published", "")), reverse=True)

    out = ['<div class="pane" id="pane-engineering">'
           '<h2 class="watch-title">診断技術・評価の最前線</h2>'
           '<p class="watch-intro">直近30日の収集記事から、診断ハーネス、検知性能、修正案の評価に関するものを表示します。'
           '論文の実験結果とベンダー寄稿の製品説明は区別し、数値や主張は原文で確認してください。</p>'
           '<section class="watch-section"><h3>読むときの確認軸</h3>'
           '<ul class="watch-gaps">'
           '<li>検知：正解データ、見逃し・誤検知、未知の対象への汎化</li>'
           '<li>動的診断：スコープ、認証、実行制御、再現できる証拠</li>'
           '<li>修正：脆弱性の解消、機能維持、回帰試験、再診断</li>'
           '<li>運用：人による確認、実行時間・費用、環境ごとの安全性</li>'
           '</ul></section><section class="watch-section"><h3>最近の記事</h3>']
    if not rows:
        out.append('<p class="watch-empty">この期間に該当する記事はありません。件数を満たすための記事は追加しません。</p>')
    for date, article, article_id, topics in rows[:20]:
        title = article.get("title_ja") or article.get("title") or "無題"
        summary = article.get("summary_ja") or "要約はありません。原文をご確認ください。"
        source = article.get("source_name", "不明")
        provenance = ""
        if "the-harness-is-hard-part-of-agentic" in article.get("url", ""):
            provenance = " · ベンダー寄稿"
        elif source.startswith("arXiv"):
            provenance = " · 研究論文"
        out.append('<article class="watch-item">'
                   f'<p class="watch-meta">{escape(date)} · {escape(source)}{provenance}</p>'
                   f'<h4><a href="article/{article_id}.html">{escape(title)}</a></h4>'
                   f'<p class="watch-meta">焦点: {escape("、".join(topics))}</p>'
                   f'<p>{escape(summary)}</p></article>')
    out.append('</section><p class="watch-note"><a href="?theme=engineering#archive">過去の記事を同じテーマで探す</a></p></div>')
    return ''.join(out)
