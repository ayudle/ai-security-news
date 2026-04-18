"""
build_site.py
latest.jsonからSEO対応・AdSense枠付き・有料会員導線付きのHTMLを生成する
"""

import json
import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
DATA_PATH = "docs/data/latest.json"
OUT_PATH  = "docs/index.html"

ADSENSE_CLIENT = "ca-pub-XXXXXXXXXXXXXXXX"  # ← AdSense審査後に差し替え
ADSENSE_SLOT   = "XXXXXXXXXX"

IMPORTANCE_COLOR = {"高": "#E24B4A", "中": "#BA7517", "低": "#639922"}
TAG_COLOR = {
    "AI for Security": "#185FA5",
    "Security for AI": "#0F6E56",
    "脆弱性":           "#993C1D",
    "脅威インテル":      "#A32D2D",
    "規制・政策":        "#3C3489",
    "研究・学術":        "#3B6D11",
}


def tag_badge(tag: str) -> str:
    color = TAG_COLOR.get(tag, "#5F5E5A")
    return f'<span class="tag" style="background:{color}22;color:{color};border:1px solid {color}44">{tag}</span>'


def importance_badge(imp: str) -> str:
    color = IMPORTANCE_COLOR.get(imp, "#888780")
    return f'<span class="imp" style="color:{color};border:1px solid {color}66">重要度 {imp}</span>'


def tier_label(tier: str) -> str:
    labels = {"A": "公的・大手", "B": "専門メディア", "C": "学術"}
    return labels.get(tier, tier)


def article_card(a: dict, is_premium: bool = False) -> str:
    tags_html = "".join(tag_badge(t) for t in a.get("tags", []))
    pub = a.get("published", "")[:10]
    blur_class = "blur-card" if is_premium else ""
    premium_overlay = '<div class="premium-overlay"><span>会員限定</span><a href="#premium" class="join-btn">無料登録して読む</a></div>' if is_premium else ""

    return f"""
<article class="card {blur_class}">
  {premium_overlay}
  <div class="card-meta">
    <span class="source-tier">{tier_label(a['source_tier'])}</span>
    <span class="source-name">{a['source_name']}</span>
    <span class="pub-date">{pub}</span>
    {importance_badge(a.get('importance','中'))}
  </div>
  <h2 class="card-title">
    <a href="{a['url']}" target="_blank" rel="noopener">{a['title_ja']}</a>
  </h2>
  <p class="card-summary">{a.get('summary_ja','')}</p>
  <div class="card-tags">{tags_html}</div>
  <div class="card-source">
    出典: <a href="{a['url']}" target="_blank" rel="noopener">{a['source_name']}</a>
    <span class="original-title">"{a['title']}"</span>
  </div>
</article>"""


def build_html(data: dict) -> str:
    articles = data.get("articles", [])
    today = data.get("today", "")
    updated = data.get("updated", "")[:16].replace("T", " ")

    # 無料公開: 上位3件、それ以降は会員限定（将来有効化）
    free_articles    = articles[:3]
    premium_articles = articles[3:]

    free_html    = "\n".join(article_card(a, False) for a in free_articles)
    premium_html = "\n".join(article_card(a, True)  for a in premium_articles)

    # 履歴アーカイブ
    history = data.get("history", [])
    archive_html = ""
    for day in history[1:8]:  # 直近7日分（今日除く）
        d = day.get("date","")
        n = len(day.get("articles",[]))
        archive_html += f'<a href="archive/{d}.html" class="archive-link">{d} ({n}件)</a>\n'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI×セキュリティ ニュース日報 | {today}</title>
  <meta name="description" content="サイバーセキュリティ×AI分野の最新ニュースを毎日自動収集・日本語要約。CISA・NIST・Krebs・Dark Readingなど信頼できるソースのみ掲載。">
  <meta property="og:title" content="AI×セキュリティ ニュース日報 {today}">
  <meta property="og:description" content="サイバーセキュリティ×AI分野の最新ニュース日本語要約">
  <meta property="og:type" content="website">
  <link rel="alternate" type="application/rss+xml" title="AI×セキュリティ ニュース" href="/feed.xml">
  <!-- Google AdSense（審査通過後に有効化） -->
  <!-- <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script> -->
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #fafaf8; --card: #fff; --text: #1a1a18; --muted: #666662;
      --border: #e5e3dc; --accent: #185FA5; --radius: 10px;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{ --bg:#181816; --card:#222220; --text:#e8e6de; --muted:#9c9a92; --border:#333330; }}
    }}
    body {{ font-family: -apple-system, "Helvetica Neue", sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; }}
    .site-header {{ border-bottom: 1px solid var(--border); padding: 1rem 0; margin-bottom: 2rem; }}
    .header-inner {{ max-width: 720px; margin: 0 auto; padding: 0 1rem; display: flex; align-items: baseline; gap: 1rem; flex-wrap: wrap; }}
    .site-title {{ font-size: 1.2rem; font-weight: 600; color: var(--text); text-decoration: none; }}
    .site-subtitle {{ font-size: 0.8rem; color: var(--muted); }}
    .updated {{ font-size: 0.75rem; color: var(--muted); margin-left: auto; }}
    main {{ max-width: 720px; margin: 0 auto; padding: 0 1rem 4rem; }}
    .section-title {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: 1rem; }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.25rem; margin-bottom: 1rem; position: relative; }}
    .card-meta {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: .6rem; font-size: .72rem; }}
    .source-tier {{ background: #e6f1fb; color: #0c447c; padding: 2px 7px; border-radius: 99px; font-weight: 500; }}
    .source-name {{ color: var(--muted); }}
    .pub-date {{ color: var(--muted); margin-left: auto; }}
    .imp {{ font-size: .7rem; padding: 2px 7px; border-radius: 99px; }}
    .card-title {{ font-size: 1rem; font-weight: 600; margin-bottom: .5rem; line-height: 1.4; }}
    .card-title a {{ color: var(--text); text-decoration: none; }}
    .card-title a:hover {{ color: var(--accent); }}
    .card-summary {{ font-size: .88rem; color: var(--muted); margin-bottom: .75rem; line-height: 1.6; }}
    .card-tags {{ display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: .6rem; }}
    .tag {{ font-size: .7rem; padding: 2px 8px; border-radius: 99px; }}
    .card-source {{ font-size: .72rem; color: var(--muted); }}
    .card-source a {{ color: var(--accent); }}
    .original-title {{ font-style: italic; margin-left: 4px; }}
    /* AdSense枠 */
    .ad-unit {{ background: var(--card); border: 1px dashed var(--border); border-radius: var(--radius);
                padding: 1rem; text-align: center; color: var(--muted); font-size: .75rem;
                min-height: 90px; display: flex; align-items: center; justify-content: center; margin: 1.5rem 0; }}
    /* 会員限定ブラー */
    .blur-card .card-summary, .blur-card .card-source {{ filter: blur(4px); user-select: none; pointer-events: none; }}
    .premium-overlay {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
                         justify-content: center; gap: .5rem; border-radius: var(--radius); z-index: 1; }}
    .join-btn {{ background: var(--accent); color: #fff; padding: .4rem 1rem; border-radius: 99px;
                 font-size: .8rem; text-decoration: none; font-weight: 500; }}
    /* 会員登録セクション */
    .premium-section {{ background: linear-gradient(135deg,#e6f1fb,#eeedfe); border: 1px solid #b5d4f4;
                         border-radius: var(--radius); padding: 1.5rem; margin: 2rem 0; text-align: center; }}
    .premium-section h3 {{ font-size: 1rem; margin-bottom: .5rem; color: #0c447c; }}
    .premium-section p {{ font-size: .85rem; color: #185FA5; margin-bottom: 1rem; }}
    .premium-form {{ display: flex; gap: .5rem; max-width: 400px; margin: 0 auto; flex-wrap: wrap; }}
    .premium-form input {{ flex: 1; min-width: 180px; padding: .5rem .75rem; border: 1px solid #b5d4f4; border-radius: 99px; font-size: .85rem; }}
    .premium-form button {{ background: #185FA5; color: #fff; border: none; padding: .5rem 1.25rem; border-radius: 99px; font-size: .85rem; cursor: pointer; font-weight: 500; }}
    /* アーカイブ */
    .archive {{ margin-top: 2rem; }}
    .archive-link {{ display: inline-block; font-size: .78rem; color: var(--accent); margin-right: .75rem; margin-bottom: .25rem; }}
    footer {{ text-align: center; font-size: .72rem; color: var(--muted); padding: 2rem 1rem; border-top: 1px solid var(--border); margin-top: 2rem; }}
  </style>
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <a href="/" class="site-title">AI×セキュリティ ニュース日報</a>
    <span class="site-subtitle">信頼できるソースのみ・毎朝自動更新</span>
    <span class="updated">最終更新: {updated} JST</span>
  </div>
</header>

<main>
  <p class="section-title">{today} のニュース</p>

  {free_html}

  <!-- AdSense広告枠（審査通過後に insタグに差し替え） -->
  <div class="ad-unit" id="ad-1">広告枠（AdSense審査通過後に表示）</div>

  <!-- 会員登録セクション -->
  <section class="premium-section" id="premium">
    <h3>残り{len(premium_articles)}件は会員限定</h3>
    <p>メールアドレスを登録すると全記事 + 過去30日アーカイブを無料で読めます</p>
    <div class="premium-form">
      <input type="email" placeholder="your@email.com">
      <button onclick="alert('近日公開予定です！')">無料で登録</button>
    </div>
  </section>

  {premium_html}

  <!-- アーカイブ -->
  <div class="archive">
    <p class="section-title">過去のニュース</p>
    {archive_html if archive_html else '<p style="font-size:.8rem;color:var(--muted)">蓄積中...</p>'}
  </div>
</main>

<footer>
  <p>本サイトは公的機関・信頼できる専門メディアのRSSフィードを自動収集しAIで要約しています。</p>
  <p>各記事の著作権は原著者・掲載メディアに帰属します。</p>
  <p style="margin-top:.5rem">Powered by Gemini API + GitHub Actions | <a href="/feed.xml" style="color:var(--accent)">RSS</a></p>
</footer>
</body>
</html>"""


def main():
    if not os.path.exists(DATA_PATH):
        print(f"[ERROR] {DATA_PATH} が見つかりません。先に fetch_and_summarize.py を実行してください。")
        return

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs("docs", exist_ok=True)
    html = build_html(data)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"生成完了: {OUT_PATH}")

    # アーカイブページも生成
    os.makedirs("docs/archive", exist_ok=True)
    for day in data.get("history", []):
        d = day.get("date", "")
        archive_data = {**data, "today": d, "articles": day.get("articles", []), "history": []}
        archive_html = build_html(archive_data)
        archive_path = f"docs/archive/{d}.html"
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(archive_html)
    print(f"アーカイブ生成: {len(data.get('history',[]))}日分")


if __name__ == "__main__":
    main()
