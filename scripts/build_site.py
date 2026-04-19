"""
build_site.py - 示唆・人気ランキング・トレンドダッシュボード付きHTML生成
"""

import json, os
from datetime import datetime, timezone, timedelta
from collections import Counter

JST       = timezone(timedelta(hours=9))
DATA_PATH = "docs/data/latest.json"
OUT_PATH  = "docs/index.html"

IMPORTANCE_COLOR = {"高": "#E24B4A", "中": "#BA7517", "低": "#639922"}
TAG_COLOR = {
    "AI for Security": "#185FA5", "Security for AI": "#0F6E56",
    "脆弱性": "#993C1D", "脅威インテル": "#A32D2D",
    "規制・政策": "#3C3489", "研究・学術": "#3B6D11",
}

def tag_badge(tag):
    c = TAG_COLOR.get(tag, "#5F5E5A")
    return f'<span class="tag" style="background:{c}18;color:{c};border:1px solid {c}40">{tag}</span>'

def imp_badge(imp):
    c = IMPORTANCE_COLOR.get(imp, "#888")
    return f'<span class="imp-badge" style="color:{c};border-color:{c}60">重要度 {imp}</span>'

def tier_label(tier):
    return {"A":"公的・大手","B":"専門メディア","C":"学術"}.get(tier, tier)

def article_card(a, rank=None):
    tags    = "".join(tag_badge(t) for t in a.get("tags", []))
    pub     = a.get("published","")[:10]
    views   = a.get("views", 0)
    insight = a.get("insight","")
    insight_html = f'<div class="insight"><span class="insight-label">示唆・学び</span>{insight}</div>' if insight else ""
    rank_html    = f'<span class="rank-num">#{rank}</span>' if rank else ""
    return f"""<article class="card" data-id="{a['id']}" onclick="countView('{a['id']}')">
  <div class="card-meta">
    {rank_html}
    <span class="tier">{tier_label(a['source_tier'])}</span>
    <span class="source">{a['source_name']}</span>
    <span class="pub">{pub}</span>
    {imp_badge(a.get('importance','中'))}
    <span class="views-badge" id="views-{a['id']}">👁 {views}</span>
  </div>
  <h2 class="card-title"><a href="{a['url']}" target="_blank" rel="noopener">{a.get('title_ja') or a['title']}</a></h2>
  <p class="card-summary">{a.get('summary_ja') or a.get('summary','')}</p>
  {insight_html}
  <div class="card-tags">{tags}</div>
  <div class="card-footer">出典: <a href="{a['url']}" target="_blank" rel="noopener">{a['source_name']}</a>
  <em class="orig-title">"{a['title']}"</em></div>
</article>"""


def build_trend_data(history):
    tag_counts, imp_counts, kw_counts, daily_counts = Counter(), Counter(), Counter(), []
    for day in history[:30]:
        articles = day.get("articles", [])
        daily_counts.append({"date": day["date"], "count": len(articles)})
        for a in articles:
            for t in a.get("tags", []):    tag_counts[t] += 1
            imp_counts[a.get("importance","中")] += 1
            for kw in a.get("keywords", []): kw_counts[kw] += 1
    return {
        "tags":  tag_counts.most_common(6),
        "imp":   imp_counts.most_common(),
        "kw":    kw_counts.most_common(12),
        "daily": list(reversed(daily_counts[:14])),
    }


def build_html(data):
    articles = data.get("articles", [])
    today    = data.get("today", "")
    updated  = data.get("updated","")[:16].replace("T"," ")
    history  = data.get("history", [])

    all_articles = [a for day in history for a in day.get("articles",[])]
    popular      = sorted(all_articles, key=lambda x: x.get("views",0), reverse=True)[:5]

    archive_html = ""
    for day in history[1:8]:
        d = day.get("date","")
        n = len(day.get("articles",[]))
        archive_html += f'<a href="archive/{d}.html" class="arc-link">{d}（{n}件）</a>\n'

    trend      = build_trend_data(history)
    trend_json = json.dumps(trend, ensure_ascii=False)

    today_html   = "\n".join(article_card(a) for a in articles) if articles else '<p class="empty">本日は該当記事がありませんでした。</p>'
    popular_html = "\n".join(article_card(a, rank=i+1) for i, a in enumerate(popular)) if popular else '<p class="empty">データ蓄積中...</p>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI×セキュリティ ニュース日報 | {today}</title>
<meta name="description" content="サイバーセキュリティ×AI分野の最新ニュースを毎日自動収集・日本語要約。示唆・学び付き。">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#f8f8f6;--card:#fff;--text:#1a1a18;--muted:#66665e;--border:#e4e2db;--accent:#185FA5;--r:10px}}
@media(prefers-color-scheme:dark){{:root{{--bg:#161614;--card:#202020;--text:#e6e4dc;--muted:#98968e;--border:#2e2e2c}}}}
body{{font-family:-apple-system,"Helvetica Neue",sans-serif;background:var(--bg);color:var(--text);line-height:1.7;font-size:15px}}
a{{color:inherit;text-decoration:none}}
.site-header{{border-bottom:1px solid var(--border);padding:.9rem 0;margin-bottom:2rem}}
.h-inner{{max-width:960px;margin:0 auto;padding:0 1.25rem;display:flex;align-items:center;gap:.75rem;flex-wrap:wrap}}
.site-title{{font-size:1.1rem;font-weight:700}}
.site-sub{{font-size:.75rem;color:var(--muted)}}
.updated{{font-size:.72rem;color:var(--muted);margin-left:auto}}
.wrap{{max-width:960px;margin:0 auto;padding:0 1.25rem 4rem;display:grid;grid-template-columns:1fr 300px;gap:2rem}}
@media(max-width:700px){{.wrap{{grid-template-columns:1fr}}}}
.main-col,.side-col{{min-width:0}}
.sec-label{{font-size:.7rem;font-weight:700;letter-spacing:.08em;color:var(--muted);text-transform:uppercase;margin-bottom:.9rem}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:1.1rem 1.2rem;margin-bottom:.9rem;cursor:pointer;transition:border-color .15s}}
.card:hover{{border-color:#aaa9a0}}
.card-meta{{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-bottom:.55rem;font-size:.7rem}}
.tier{{background:#e6f1fb;color:#0c447c;padding:2px 7px;border-radius:99px;font-weight:600}}
.source,.pub{{color:var(--muted)}}
.pub{{margin-left:auto}}
.imp-badge{{font-size:.68rem;padding:2px 6px;border-radius:99px;border:1px solid}}
.views-badge{{font-size:.68rem;color:var(--muted)}}
.rank-num{{font-size:.85rem;font-weight:700;color:var(--accent);min-width:24px}}
.card-title{{font-size:.95rem;font-weight:600;margin-bottom:.45rem;line-height:1.4}}
.card-title a:hover{{color:var(--accent)}}
.card-summary{{font-size:.83rem;color:var(--muted);margin-bottom:.6rem;line-height:1.65}}
.insight{{background:#eef4ff;border-left:3px solid #378ADD;border-radius:0 6px 6px 0;padding:.5rem .75rem;margin-bottom:.6rem;font-size:.8rem;line-height:1.55}}
@media(prefers-color-scheme:dark){{.insight{{background:#1a2035}}}}
.insight-label{{display:block;font-size:.65rem;font-weight:700;color:#185FA5;letter-spacing:.05em;margin-bottom:2px}}
.card-tags{{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:.5rem}}
.tag{{font-size:.67rem;padding:2px 7px;border-radius:99px}}
.card-footer{{font-size:.68rem;color:var(--muted)}}
.card-footer a{{color:var(--accent)}}
.orig-title{{font-style:italic;margin-left:4px}}
.empty{{font-size:.85rem;color:var(--muted);padding:1.5rem 0}}
.dash-card{{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:1rem 1.1rem;margin-bottom:1rem}}
.dash-title{{font-size:.78rem;font-weight:600;margin-bottom:.75rem}}
.bar-row{{display:flex;align-items:center;gap:6px;margin-bottom:6px;font-size:.72rem}}
.bar-label{{width:95px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex-shrink:0}}
.bar-track{{flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:3px}}
.bar-count{{width:20px;text-align:right;color:var(--muted)}}
.kw-cloud{{display:flex;flex-wrap:wrap;gap:5px}}
.kw-tag{{font-size:.7rem;padding:3px 9px;border-radius:99px;background:var(--bg);border:1px solid var(--border);color:var(--muted)}}
.arc-link{{display:inline-block;font-size:.75rem;color:var(--accent);margin-right:.6rem;margin-bottom:.25rem}}
canvas{{display:block;width:100%!important;height:52px!important}}
footer{{text-align:center;font-size:.7rem;color:var(--muted);padding:1.5rem;border-top:1px solid var(--border);margin-top:1rem}}
</style>
</head>
<body>
<header class="site-header">
  <div class="h-inner">
    <a href="/" class="site-title">AI×セキュリティ ニュース日報</a>
    <span class="site-sub">信頼できるソースのみ・毎朝自動更新・最大5件/日</span>
    <span class="updated">更新: {updated} JST</span>
  </div>
</header>

<div class="wrap">
  <main class="main-col">
    <p class="sec-label">{today} のニュース（{len(articles)}件）</p>
    {today_html}

    <div style="margin-top:2rem">
      <p class="sec-label">人気記事ランキング</p>
      {popular_html}
    </div>

    <div style="margin-top:2rem">
      <p class="sec-label">過去のニュース</p>
      {archive_html if archive_html else '<p class="empty">蓄積中...</p>'}
    </div>
  </main>

  <aside class="side-col">
    <div class="dash-card">
      <p class="dash-title">カテゴリ分布（過去30日）</p>
      <div id="tag-bars"></div>
    </div>
    <div class="dash-card">
      <p class="dash-title">記事数の推移（過去14日）</p>
      <canvas id="sparkline"></canvas>
    </div>
    <div class="dash-card">
      <p class="dash-title">頻出キーワード</p>
      <div class="kw-cloud" id="kw-cloud"></div>
    </div>
    <div class="dash-card">
      <p class="dash-title">重要度の内訳</p>
      <div id="imp-bars"></div>
    </div>
  </aside>
</div>

<footer>
  <p>各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。</p>
  <p style="margin-top:.3rem">Powered by Gemini 2.0 Flash Lite + GitHub Actions（完全無料）</p>
</footer>

<script>
const TREND = {trend_json};
const TAG_COLORS = {{"AI for Security":"#185FA5","Security for AI":"#0F6E56","脆弱性":"#993C1D","脅威インテル":"#A32D2D","規制・政策":"#3C3489","研究・学術":"#3B6D11"}};
const IMP_COLORS = {{"高":"#E24B4A","中":"#BA7517","低":"#639922"}};

function renderBars(id, data, colorMap) {{
  const el = document.getElementById(id);
  if (!el || !data.length) return;
  const max = data[0][1] || 1;
  el.innerHTML = data.map(([label, count]) => {{
    const pct = Math.round(count / max * 100);
    const color = colorMap[label] || '#378ADD';
    return `<div class="bar-row">
      <span class="bar-label" title="${{label}}">${{label}}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${{pct}}%;background:${{color}}"></div></div>
      <span class="bar-count">${{count}}</span></div>`;
  }}).join('');
}}
renderBars('tag-bars', TREND.tags, TAG_COLORS);
renderBars('imp-bars', TREND.imp,  IMP_COLORS);

const kwEl = document.getElementById('kw-cloud');
if (kwEl && TREND.kw.length) {{
  const maxKw = TREND.kw[0][1] || 1;
  kwEl.innerHTML = TREND.kw.map(([kw, cnt]) => {{
    const size = (0.65 + (cnt / maxKw) * 0.3).toFixed(2);
    return `<span class="kw-tag" style="font-size:${{size}}rem">${{kw}}</span>`;
  }}).join('');
}}

(function() {{
  const canvas = document.getElementById('sparkline');
  if (!canvas || !TREND.daily.length) return;
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth || 280, H = 52;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const counts = TREND.daily.map(d => d.count);
  const maxV = Math.max(...counts, 1);
  const step = W / (counts.length - 1 || 1);
  const pts = counts.map((v, i) => [i * step, H - 6 - (v / maxV) * (H - 14)]);
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, 'rgba(55,138,221,.25)');
  grad.addColorStop(1, 'rgba(55,138,221,0)');
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  pts.slice(1).forEach(([x,y]) => ctx.lineTo(x, y));
  ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  pts.slice(1).forEach(([x,y]) => ctx.lineTo(x, y));
  ctx.strokeStyle = '#378ADD'; ctx.lineWidth = 1.5; ctx.lineJoin = 'round'; ctx.stroke();
}})();

const VIEWS_KEY = 'aisc_views_v2';
function loadViews() {{ try {{ return JSON.parse(localStorage.getItem(VIEWS_KEY) || '{{}}'); }} catch {{ return {{}}; }} }}
function countView(id) {{
  const v = loadViews(); v[id] = (v[id] || 0) + 1;
  localStorage.setItem(VIEWS_KEY, JSON.stringify(v));
  const el = document.getElementById('views-' + id);
  if (el) el.textContent = '👁 ' + v[id];
}}
(function() {{
  const v = loadViews();
  Object.entries(v).forEach(([id, cnt]) => {{
    const el = document.getElementById('views-' + id);
    if (el) el.textContent = '👁 ' + cnt;
  }});
}})();
</script>
</body>
</html>"""


def main():
    if not os.path.exists(DATA_PATH):
        print(f"[ERROR] {DATA_PATH} なし"); return
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    os.makedirs("docs", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(build_html(data))
    print(f"生成完了: {OUT_PATH} ({len(data.get('articles',[]))}件)")
    os.makedirs("docs/archive", exist_ok=True)
    for day in data.get("history", []):
        d = day.get("date","")
        arc = {**data, "today": d, "articles": day.get("articles",[]), "history": []}
        with open(f"docs/archive/{d}.html", "w", encoding="utf-8") as f:
            f.write(build_html(arc))
    print(f"アーカイブ: {len(data.get('history',[]))}日分")

if __name__ == "__main__":
    main()
