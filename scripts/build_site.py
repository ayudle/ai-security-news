"""
build_site.py v3
タブUI・トレンドダッシュボード（大項目×中項目スパイク分析）付きHTML生成
"""

import json, os
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

JST       = timezone(timedelta(hours=9))
DATA_PATH = "docs/data/latest.json"
OUT_PATH  = "docs/index.html"

IMP_COLOR = {"高": "#E24B4A", "中": "#BA7517", "低": "#639922"}
MAIN_COLOR = {
    "attack":   "#E24B4A",
    "vuln":     "#BA7517",
    "ai_sec":   "#185FA5",
    "ai_risk":  "#7F77DD",
    "policy":   "#0F6E56",
    "incident": "#993C1D",
    "biz_tech": "#3B6D11",
}

def tier_label(tier):
    return {"A":"公的・大手","B":"専門メディア","C":"学術"}.get(tier, tier)

def imp_badge(imp):
    c = IMP_COLOR.get(imp, "#888")
    return f'<span class="imp" style="color:{c};border-color:{c}55">重要度 {imp}</span>'

def tag_main_badge(main_id, main_label):
    c = MAIN_COLOR.get(main_id, "#5F5E5A")
    return f'<span class="tag-main" style="background:{c}20;color:{c};border-color:{c}44">{main_label}</span>'

def tag_sub_badge(sub):
    return f'<span class="tag-sub">{sub}</span>'

def article_card(a, rank=None):
    rank_html    = f'<span class="rank">#{rank}</span>' if rank else ""
    pub          = a.get("published","")[:10]
    views        = a.get("views", 0)
    insight      = a.get("insight","")
    imp_reason   = a.get("importance_reason","")
    insight_html = f'<div class="insight"><span class="ins-lbl">示唆・学び</span>{insight}</div>' if insight else ""
    reason_html  = f'<span class="imp-reason" title="{imp_reason}">?</span>' if imp_reason else ""
    main_id      = a.get("tag_main_id","attack")
    main_label   = a.get("tag_main_label","攻撃・脅威")
    subs_html    = "".join(tag_sub_badge(s) for s in a.get("tag_subs",[]))

    return f"""<article class="card" data-id="{a.get('id','')}" data-main="{main_id}" onclick="countView('{a.get('id','')}')">
  <div class="cm">
    {rank_html}
    <span class="tier">{tier_label(a.get('source_tier','B'))}</span>
    <span class="src">{a.get('source_name','')}</span>
    <span class="dt">{pub}</span>
    {imp_badge(a.get('importance','中'))}{reason_html}
    <span class="vw" id="v-{a.get('id','')}">👁 {views}</span>
  </div>
  <h2 class="ct"><a href="article/{a.get('id','')}.html">{a.get('title_ja') or a.get('title','')}</a></h2>
  <p class="cs">{a.get('summary_ja') or a.get('summary','')}</p>
  {insight_html}
  <div class="tags">
    {tag_main_badge(main_id, main_label)}
    {subs_html}
  </div>
  <div class="cf">出典: <a href="{a.get('url','#')}" target="_blank" rel="noopener">{a.get('source_name','')}</a>
  <em class="orig">"{a.get('title','')}"</em></div>
</article>"""


def build_analytics(history, taxonomy):
    """過去30日・7日のタグ集計データを生成"""
    now = datetime.now(JST)

    # 日付ごとの中項目カウント（スパイク検出用）
    daily_sub = defaultdict(lambda: defaultdict(int))   # date -> sub -> count
    main_30   = Counter()
    sub_30    = Counter()
    main_7    = Counter()
    sub_7     = Counter()

    for day in history[:30]:
        d = day.get("date","")
        try:
            day_dt = datetime.fromisoformat(d + "T00:00:00+09:00")
        except Exception:
            continue
        is_7days = (now - day_dt).days <= 7

        for a in day.get("articles",[]):
            mid  = a.get("tag_main_id","")
            subs = a.get("tag_subs",[])
            main_30[mid] += 1
            for s in subs:
                sub_30[s] += 1
                daily_sub[d][s] += 1
            if is_7days:
                main_7[mid] += 1
                for s in subs:
                    sub_7[s] += 1

    # スパイク検出: 過去7日で2件以上かつ過去30日平均の2倍以上
    spikes = []
    for sub, cnt_7 in sub_7.items():
        cnt_30 = sub_30.get(sub, 0)
        avg_daily = cnt_30 / 30
        if cnt_7 >= 2 and avg_daily > 0 and (cnt_7 / 7) >= avg_daily * 1.8:
            spikes.append({"sub": sub, "cnt_7": cnt_7, "cnt_30": cnt_30})
    spikes.sort(key=lambda x: -x["cnt_7"])

    # 重要度集計
    imp_all = Counter()
    for day in history[:30]:
        for a in day.get("articles",[]):
            imp_all[a.get("importance","中")] += 1

    return {
        "main_30":  [(k, v, taxonomy.get(k,{}).get("label",k)) for k,v in main_30.most_common()],
        "main_7":   [(k, v, taxonomy.get(k,{}).get("label",k)) for k,v in main_7.most_common()],
        "sub_7":    sub_7.most_common(15),
        "spikes":   spikes[:5],
        "imp_list": imp_all.most_common(),
        "total_articles": sum(len(d.get("articles",[])) for d in history),
        "total_days":     len(history),
    }


def build_html(data):
    articles  = data.get("articles", [])
    today     = data.get("today", "")
    updated   = data.get("updated","")[:16].replace("T"," ")
    history   = data.get("history", [])
    taxonomy  = data.get("taxonomy", {})

    # 過去7日の人気記事（views降順）
    cutoff_7  = (datetime.now(JST) - timedelta(days=7)).strftime("%Y-%m-%d")
    week_arts = [a for day in history if day.get("date","") >= cutoff_7
                 for a in day.get("articles",[]) if "source_tier" in a]
    popular   = sorted(week_arts, key=lambda x: x.get("views",0), reverse=True)[:5]

    # アーカイブ
    archive_rows = ""
    for day in history[:30]:
        d = day.get("date","")
        n = len(day.get("articles",[]))
        archive_rows += f'<div class="arc-row"><a href="archive/{d}.html" class="arc-link">{d}</a><span class="arc-n">{n}件</span></div>\n'

    # 分析データ
    analytics   = build_analytics(history, taxonomy)
    ana_json    = json.dumps(analytics, ensure_ascii=False)
    tax_json    = json.dumps(taxonomy, ensure_ascii=False)

    today_html   = "\n".join(article_card(a) for a in articles) if articles \
                   else '<p class="empty">本日は該当記事がありませんでした。</p>'
    popular_html = "\n".join(article_card(a, rank=i+1) for i,a in enumerate(popular)) if popular \
                   else '<p class="empty">データ蓄積中（クリックで記録されます）</p>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI×セキュリティ ニュース日報 | {today}</title>
<meta name="description" content="サイバーセキュリティ×AI分野の最新ニュースを毎日自動収集・日本語要約。CISO視点での示唆・学び付き。">
<meta name="google-site-verification" content="m7S3bMP_P0V-BinV3MTpaO9qkk31af-RRKxsQ4_BoQg" />
<meta property="og:title" content="AI×セキュリティ ニュース日報">
<meta property="og:description" content="サイバーセキュリティ×AI分野の最新ニュースを毎日自動収集・日本語要約。CISO視点での示唆・学び付き。">
<meta property="og:url" content="https://ayudle.github.io/ai-security-news/">
<meta property="og:type" content="website">
<meta property="og:image" content="https://ayudle.github.io/ai-security-news/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="AI×セキュリティ ニュース日報">
<meta name="twitter:description" content="サイバーセキュリティ×AI分野の最新ニュースを毎日自動収集・日本語要約。CISO視点での示唆・学び付き。">
<meta name="twitter:image" content="https://ayudle.github.io/ai-security-news/og-image.png">
<link rel="canonical" href="https://ayudle.github.io/ai-security-news/">
<link rel="icon" type="image/png" href="favicon.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<script type="application/ld+json">
{{{{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "AI×セキュリティ ニュース日報",
  "url": "https://ayudle.github.io/ai-security-news/",
  "description": "サイバーセキュリティ×AI分野の最新ニュースを毎日自動収集・日本語要約",
  "publisher": {{{{
    "@type": "Organization",
    "name": "AI×セキュリティ ニュース日報",
    "url": "https://ayudle.github.io/ai-security-news/"
  }}}}
}}}}
</script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#0f0f0d;--card:#1a1a18;--card2:#222220;--text:#e6e4dc;--muted:#98968e;--dim:#6a6860;--border:#2a2a28;--accent:#378ADD;--r:10px}}
body{{font-family:-apple-system,"Helvetica Neue",sans-serif;background:var(--bg);color:var(--text);line-height:1.7;font-size:14px}}
a{{color:inherit;text-decoration:none}}
.hdr{{border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.ht{{font-size:15px;font-weight:700;color:#fff}}
.hs{{font-size:11px;color:var(--dim)}}
.hu{{font-size:11px;color:var(--dim);margin-left:auto}}
.tab-bar{{display:flex;border-bottom:1px solid var(--border);padding:0 24px;overflow-x:auto}}
.tab{{font-size:12px;padding:10px 16px;cursor:pointer;color:var(--dim);border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;transition:all .15s}}
.tab.on{{color:var(--text);border-bottom-color:var(--accent);font-weight:600}}
.pane{{display:none;padding:16px 24px;max-width:860px;margin:0 auto}}
.pane.on{{display:block}}
.plabel{{font-size:10px;font-weight:700;letter-spacing:.08em;color:var(--dim);text-transform:uppercase;margin-bottom:12px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:14px 16px;margin-bottom:10px;cursor:pointer;transition:border-color .15s}}
.card:hover{{border-color:#3a3a38}}
.cm{{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-bottom:8px}}
.tier{{background:#0c2a4a;color:#85b7eb;font-size:10px;padding:2px 7px;border-radius:99px;font-weight:600}}
.src,.dt{{font-size:10px;color:var(--dim)}}
.dt{{margin-left:auto}}
.imp{{font-size:10px;padding:2px 6px;border-radius:99px;border:1px solid}}
.imp-reason{{font-size:10px;color:var(--dim);cursor:help;margin-left:1px}}
.vw{{font-size:10px;color:var(--dim)}}
.rank{{font-size:13px;font-weight:700;color:var(--accent);min-width:22px}}
.ct{{font-size:14px;font-weight:600;margin-bottom:6px;line-height:1.45}}
.ct a:hover{{color:var(--accent)}}
.cs{{font-size:12px;color:var(--muted);line-height:1.65;margin-bottom:8px}}
.insight{{background:#0d1e36;border-left:3px solid var(--accent);border-radius:0 6px 6px 0;padding:7px 10px;margin-bottom:8px;font-size:11px;color:#85b7eb;line-height:1.55}}
.ins-lbl{{display:block;font-size:9px;font-weight:700;color:var(--accent);letter-spacing:.06em;margin-bottom:2px;text-transform:uppercase}}
.tags{{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}}
.tag-main{{font-size:10px;padding:2px 8px;border-radius:99px;border:1px solid;font-weight:600}}
.tag-sub{{font-size:10px;padding:2px 7px;border-radius:99px;background:#222220;border:1px solid #333330;color:var(--muted)}}
.cf{{font-size:10px;color:var(--dim)}}
.cf a{{color:var(--accent)}}
.orig{{font-style:italic;margin-left:4px}}
.empty{{font-size:12px;color:var(--dim);padding:1rem 0}}
.arc-row{{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border)}}
.arc-link{{font-size:12px;color:var(--accent)}}
.arc-n{{font-size:11px;color:var(--dim)}}
.arc-note{{font-size:11px;color:var(--dim);margin-top:12px;padding:10px;background:var(--card);border-radius:8px;line-height:1.6}}
.stat-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px}}
.stat{{background:var(--card);border-radius:8px;padding:12px;text-align:center}}
.stat-n{{font-size:24px;font-weight:700;color:var(--text)}}
.stat-l{{font-size:10px;color:var(--dim);margin-top:2px}}
.dash-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
@media(max-width:600px){{.dash-grid{{grid-template-columns:1fr}}}}
.dc{{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:12px 14px}}
.dc-title{{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}}
.dc-sub{{font-size:10px;color:var(--dim);margin-bottom:8px}}
.bar-row{{display:flex;align-items:center;gap:6px;margin-bottom:7px;cursor:pointer}}
.bar-row:hover .bl{{color:var(--text)}}
.bl{{width:88px;font-size:11px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex-shrink:0;transition:color .1s}}
.bt{{flex:1;height:5px;background:#2a2a28;border-radius:3px;overflow:hidden}}
.bf{{height:100%;border-radius:3px;transition:width .4s}}
.bn{{width:18px;text-align:right;font-size:10px;color:var(--dim)}}
.spike-list{{display:flex;flex-direction:column;gap:6px}}
.spike-item{{display:flex;align-items:center;justify-content:space-between;padding:6px 8px;background:#222220;border-radius:6px}}
.spike-name{{font-size:12px;color:var(--text)}}
.spike-badge{{font-size:10px;background:#E24B4A22;color:#E24B4A;border:1px solid #E24B4A44;padding:2px 7px;border-radius:99px}}
.sub-filter{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}}
.sf-btn{{font-size:11px;padding:4px 10px;border-radius:99px;border:1px solid var(--border);background:transparent;color:var(--dim);cursor:pointer;transition:all .15s}}
.sf-btn.on{{border-color:var(--accent);color:var(--accent);background:#0d1e36}}
.imp-note{{font-size:11px;color:var(--dim);background:var(--card);border-radius:8px;padding:10px 12px;line-height:1.6;margin-bottom:12px;border-left:3px solid #BA751755}}
</style>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-KV7Q7SQKZX"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){{dataLayer.push(arguments);}}
gtag('js', new Date());
gtag('config', 'G-KV7Q7SQKZX');
</script>
</head>
<body>
<header class="hdr">
  <span class="ht">AI×セキュリティ ニュース日報</span>
  <span class="hs">信頼できるソースのみ・毎朝自動更新・最大5件/日</span>
  <span class="hu">更新: {updated} JST</span>
</header>

<div class="tab-bar">
  <a href="#today"   class="tab">本日のニュース</a>
  <a href="#popular" class="tab">人気記事</a>
  <a href="#archive" class="tab">アーカイブ</a>
  <a href="#trend"   class="tab">トレンド分析</a>
  <a href="#about"   class="tab">About</a>
</div>

<div class="pane" id="pane-today">
  <p class="plabel">{today} のニュース（{len(articles)}件）</p>
  {today_html}
</div>

<div class="pane" id="pane-popular">
  <p class="plabel">人気記事 — 過去7日間</p>
  <p style="font-size:11px;color:var(--dim);margin-bottom:12px">記事をクリックすると閲覧数がカウントされます。あなた自身の端末での集計です。</p>
  {popular_html}
</div>

<div class="pane" id="pane-archive">
  <p class="plabel">過去のニュース</p>
  <div class="arc-note">
    過去最大90日分のアーカイブを保存しています。毎朝自動更新されます。<br>
    各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。
  </div>
  <div style="margin-top:12px">
    {archive_rows if archive_rows else '<p class="empty">蓄積中...</p>'}
  </div>
</div>

<div class="pane" id="pane-trend">
  <p class="plabel">トレンド分析</p>

  <div class="stat-row">
    <div class="stat"><div class="stat-n" id="s-total">—</div><div class="stat-l">累計記事数</div></div>
    <div class="stat"><div class="stat-n" id="s-days">—</div><div class="stat-l">更新日数</div></div>
    <div class="stat"><div class="stat-n" id="s-spike">—</div><div class="stat-l">急上昇トピック数</div></div>
  </div>

  <div class="dash-grid">

    <div class="dc" style="grid-column:1/-1">
      <div class="dc-title">急上昇トピック（過去7日）</div>
      <div class="dc-sub">先週と比べて話題が急増しているキーワード</div>
      <div class="spike-list" id="spike-list"></div>
    </div>

    <div class="dc" style="grid-column:1/-1">
      <div class="dc-title">大項目を選んで中項目トレンドを見る</div>
      <div class="sub-filter" id="main-filter"></div>
      <div id="sub-bars"></div>
    </div>

    <div class="dc">
      <div class="dc-title">大項目の分布（過去7日）</div>
      <div id="main-bars-7"></div>
    </div>

    <div class="dc">
      <div class="dc-title">重要度の内訳</div>
      <div class="imp-note">
        <strong style="color:var(--text)">重要度の判断基準</strong><br>
        高: 広範囲に影響・即時対応が必要<br>
        中: 特定分野に影響・注目トレンド<br>
        低: 参考情報・長期動向<br>
        <span style="font-size:10px">AIが記事内容から自動判定。各記事の「重要度」横の「?」にカーソルを合わせると理由が表示されます。</span>
      </div>
      <div id="imp-bars"></div>
    </div>

  </div>
</div>


<div class="pane" id="pane-about">
  <p class="plabel">About</p>
  <div style="max-width:720px;margin:0 auto;padding:1rem 0">
    <h1 style="font-size:28px;font-weight:700;color:#fff;margin-bottom:6px;letter-spacing:-.01em">Ayudle</h1>
    <p style="font-size:13px;color:#6a6860;margin-bottom:2.5rem">AI×セキュリティ ニュース日報 運営者</p>
    <div style="margin-bottom:2.5rem">
      <div style="font-size:11px;font-weight:700;letter-spacing:.1em;color:#6a6860;text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #2a2a28">Profile</div>
      <div style="font-size:14px;color:#98968e;line-height:1.85"><p>若手セキュリティエンジニアです。セキュリティ監視・運用の高度化や自動化、AI×セキュリティの検証・サービス開発に携わってきました。AI for SecurityとSecurity for AIの両方に興味を持ち、業界の標準化・研究活動にも関わっています。</p></div>
    </div>
    <div style="margin-bottom:2.5rem">
      <div style="font-size:11px;font-weight:700;letter-spacing:.1em;color:#6a6860;text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #2a2a28">このサイトを作った理由</div>
      <div style="font-size:14px;color:#98968e;line-height:1.85">
        <p style="margin-bottom:1rem">AIエージェントが企業のあらゆる業務に浸透していく中で、「AIエージェント自体のリスクをどう管理するか」という問いへの関心が高まっています。</p>
        <p>私自身、セキュリティ監視運用の現場に携わりながら、この領域が今後どう変わっていくのかを継続的に追いかけたいと考えていました。断片的なニュースを都度追うのではなく、構造的に理解するための情報基盤が欲しい。それがこのサイトを作った理由です。</p>
      </div>
    </div>
    <div style="margin-bottom:2.5rem">
      <div style="font-size:11px;font-weight:700;letter-spacing:.1em;color:#6a6860;text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #2a2a28">私が持っている仮説</div>
      <div style="font-size:14px;color:#98968e;line-height:1.85">
        <p style="margin-bottom:1rem">AIエージェントのリスクは、以下の6つの層に分けて考えると整理しやすいと思っています。</p>
        <div style="display:flex;flex-direction:column;gap:6px;margin:1rem 0">
          <div style="background:#1a1a18;border-radius:10px;padding:10px 14px;font-size:13px"><span style="font-size:11px;font-weight:700;color:#378ADD;margin-right:6px">①</span><span style="font-weight:500;color:#e6e4dc">モデル・推論層</span><div style="font-size:12px;color:#6a6860;margin-top:2px">プロンプトインジェクション、ハルシネーション、目的逸脱</div></div>
          <div style="background:#1a1a18;border-radius:10px;padding:10px 14px;font-size:13px"><span style="font-size:11px;font-weight:700;color:#378ADD;margin-right:6px">②</span><span style="font-weight:500;color:#e6e4dc">ツール・実行層</span><div style="font-size:12px;color:#6a6860;margin-top:2px">権限過剰、ツール誤操作、エージェントハイジャック</div></div>
          <div style="background:#1a1a18;border-radius:10px;padding:10px 14px;font-size:13px"><span style="font-size:11px;font-weight:700;color:#378ADD;margin-right:6px">③</span><span style="font-weight:500;color:#e6e4dc">マルチエージェント層</span><div style="font-size:12px;color:#6a6860;margin-top:2px">AI間の誤連携、カスケード障害、攻撃の自動化</div></div>
          <div style="background:#1a1a18;border-radius:10px;padding:10px 14px;font-size:13px"><span style="font-size:11px;font-weight:700;color:#378ADD;margin-right:6px">④</span><span style="font-weight:500;color:#e6e4dc">データ・インフラ層</span><div style="font-size:12px;color:#6a6860;margin-top:2px">データ境界の崩壊、シャドーAI、サプライチェーン攻撃</div></div>
          <div style="background:#1a1a18;border-radius:10px;padding:10px 14px;font-size:13px"><span style="font-size:11px;font-weight:700;color:#378ADD;margin-right:6px">⑤</span><span style="font-weight:500;color:#e6e4dc">アイデンティティ・権限層</span><div style="font-size:12px;color:#6a6860;margin-top:2px">非人間IDの管理、過剰自律性、Observability欠如</div></div>
          <div style="background:#1a1a18;border-radius:10px;padding:10px 14px;font-size:13px"><span style="font-size:11px;font-weight:700;color:#378ADD;margin-right:6px">⑥</span><span style="font-weight:500;color:#e6e4dc">組織・ガバナンス層</span><div style="font-size:12px;color:#6a6860;margin-top:2px">責任所在の不明確さ、automation bias、法規制の未整備</div></div>
        </div>
        <p style="margin-bottom:1rem">これらのリスクをエンドポイント・ネットワーク・サーバー・アプリケーションといったあらゆる領域にわたって、識別・防御・検知・対応・復旧の観点で一元的に監視するセンターが、近い将来必ず必要になると考えています。</p>
        <p style="margin-bottom:1rem">従来のSOCは人間が操作するシステムを守る前提で設計されています。しかしAIエージェントが主体として動く環境では、監視対象の性質が根本的に変わります。エージェントの判断の異常を検知し、その連鎖を止め、影響を復旧する。そのような機能を持つ組織が、従来のSOCと統合されてより広い範囲をカバーするサイバーディフェンスセンターへと進化していくと見ています。</p>
        <p>現在の市場では、Observabilityツール・プロンプトセキュリティ・AI権限管理などが個別のソリューションとして存在しています。これらを統合して一元的に可視化・監視するプラットフォームはまだ確立されていません。このサイトは、その空白を埋めていくための知識インフラとして育てていくつもりです。</p>
      </div>
    </div>
    <div style="margin-bottom:2.5rem">
      <div style="font-size:11px;font-weight:700;letter-spacing:.1em;color:#6a6860;text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #2a2a28">SNS</div>
      <div style="font-size:14px;color:#98968e;line-height:1.85">
        <p style="margin-bottom:1rem">X（旧Twitter）で最新ニュースを毎朝発信しています。フォローお待ちしています。</p>
        <a href="https://x.com/ayudle_aisec" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:8px;padding:10px 18px;background:#1a1a18;border:1px solid #2a2a28;border-radius:6px;text-decoration:none;color:#e6e4dc;font-size:13px;font-weight:500;transition:border-color .15s" onmouseover="this.style.borderColor='#378ADD'" onmouseout="this.style.borderColor='#2a2a28'">
          <span style="font-size:16px">𝕏</span>
          <span>@ayudle_aisec をフォロー</span>
        </a>
      </div>
    </div>

    <div>
      <div style="font-size:11px;font-weight:700;letter-spacing:.1em;color:#6a6860;text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #2a2a28">このサイトでやっていること</div>
      <div style="font-size:14px;color:#98968e;line-height:1.85"><p>信頼できるソースからAI×セキュリティの最新ニュースを毎日自動収集・日本語要約して公開しています。単なるニュースの羅列にとどまらず、上記の仮説に基づいた構造的な可視化プラットフォームとして発展させていく予定です。</p></div>
    </div>
  </div>
</div>

<footer style="text-align:center;font-size:10px;color:var(--dim);padding:20px;border-top:1px solid var(--border);margin-top:16px">
  <p>各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。</p>
  <p style="margin-top:4px">Powered by Gemini 2.5 Flash + GitHub Actions（完全無料）</p>
</footer>

<script>
const ANA = {ana_json};
const TAX = {tax_json};
const IMP_COLORS = {{"高":"#E24B4A","中":"#BA7517","低":"#639922"}};
const MAIN_COLORS = {{"attack":"#E24B4A","vuln":"#BA7517","ai_sec":"#378ADD","ai_risk":"#7F77DD","policy":"#1D9E75","incident":"#D85A30","biz_tech":"#639922"}};

function showTab(id) {{
  var valid = ['today','popular','archive','trend','about'];
  if (valid.indexOf(id) < 0) id = 'today';
  document.querySelectorAll('.pane').forEach(function(p) {{ p.classList.remove('on'); }});
  document.querySelectorAll('.tab-bar .tab').forEach(function(t) {{ t.classList.remove('on'); }});
  var pane = document.getElementById('pane-' + id);
  if (pane) pane.classList.add('on');
  var tab = document.querySelector('.tab-bar a[href="#' + id + '"]');
  if (tab) tab.classList.add('on');
}}

function initTab() {{
  var h = location.hash.replace('#','') || 'today';
  showTab(h);
}}

window.addEventListener('hashchange', function() {{
  var h = location.hash.replace('#','') || 'today';
  showTab(h);
}});

// すぐ実行（load待ちしない）
if (document.readyState === 'loading') {{
  document.addEventListener('DOMContentLoaded', initTab);
}} else {{
  initTab();
}}

function renderBars(containerId, data, colorFn, maxOverride) {{
  const el = document.getElementById(containerId);
  if (!el || !data.length) {{ if(el) el.innerHTML='<p class="empty">データ蓄積中...</p>'; return; }}
  const max = maxOverride || data[0][1] || 1;
  el.innerHTML = data.map(([label, count]) => {{
    const pct = Math.round(count / max * 100);
    const color = colorFn(label);
    return `<div class="bar-row">
      <span class="bl" title="${{label}}">${{label}}</span>
      <div class="bt"><div class="bf" style="width:${{pct}}%;background:${{color}}"></div></div>
      <span class="bn">${{count}}</span></div>`;
  }}).join('');
}}

// 重要度を履歴から集計
const impCount = {{"高":0,"中":0,"低":0}};
(ANA.imp_list||[]).forEach(([imp,cnt]) => {{ if(impCount[imp]!==undefined) impCount[imp]=cnt; }});

function initDashboard() {{
  document.getElementById('s-total').textContent = ANA.total_articles;
  document.getElementById('s-days').textContent  = ANA.total_days;
  document.getElementById('s-spike').textContent = ANA.spikes.length;

  const spikeEl = document.getElementById('spike-list');
  if (ANA.spikes.length) {{
    spikeEl.innerHTML = ANA.spikes.map(s =>
      `<div class="spike-item">
        <span class="spike-name">${{s.sub}}</span>
        <span class="spike-badge">今週 ${{s.cnt_7}}件 急増</span>
      </div>`
    ).join('');
  }} else {{
    spikeEl.innerHTML = '<p class="empty">データ蓄積中... 1週間以上のデータが揃うと表示されます</p>';
  }}

  renderBars('main-bars-7',
    ANA.main_7.map(([k,v,l]) => [l,v]),
    label => {{ const k = ANA.main_7.find(([_,__,l])=>l===label)?.[0]; return MAIN_COLORS[k]||'#378ADD'; }}
  );

  // 重要度バー
  const impData = [["高", impCount["高"]], ["中", impCount["中"]], ["低", impCount["低"]]].filter(([,v])=>v>0);
  renderBars('imp-bars', impData, label => IMP_COLORS[label]||'#888');

  // 大項目フィルターボタン生成
  const filterEl = document.getElementById('main-filter');
  const mainKeys = [...new Set(ANA.main_7.map(([k])=>k))];
  if (!mainKeys.length) {{
    filterEl.innerHTML = '<p class="empty">データ蓄積中...</p>';
    return;
  }}
  filterEl.innerHTML = "";
  mainKeys.forEach(function(k,i) {{
    const label = TAX[k] ? TAX[k].label : k;
    const color = MAIN_COLORS[k] || '#378ADD';
    const btn = document.createElement("button");
    btn.className = "sf-btn" + (i===0 ? " on" : "");
    btn.dataset.key = k;
    if (i===0) {{ btn.style.borderColor=color; btn.style.color=color; btn.style.background=color+"22"; }}
    btn.textContent = label;
    btn.addEventListener("click", (function(key,c){{ return function(){{ selectMain(key,this,c); }}; }})(k,color));
    filterEl.appendChild(btn);
  }});
  selectMain(mainKeys[0], filterEl.querySelector('.sf-btn.on'), MAIN_COLORS[mainKeys[0]]||'#378ADD');
}}

document.addEventListener('DOMContentLoaded', initDashboard);

function selectMain(key, el, color) {{
  document.querySelectorAll('.sf-btn').forEach(b => {{
    b.classList.remove('on');
    b.style.cssText = '';
  }});
  el.classList.add('on');
  el.style.borderColor = color;
  el.style.color = color;
  el.style.background = color + '22';

  const subs = TAX[key]?.subs || [];
  const subData = subs.map(s => [s, ANA.sub_7.find(([k])=>k===s)?.[1] || 0])
                      .filter(([,v]) => v > 0)
                      .sort((a,b) => b[1]-a[1]);

  const el2 = document.getElementById('sub-bars');
  if (!subData.length) {{
    el2.innerHTML = '<p class="empty">この大項目の記事はまだありません</p>';
    return;
  }}
  renderBars('sub-bars', subData, () => color, Math.max(...subData.map(([,v])=>v)));
}}

const VK = 'aisc_v3';
function loadViews() {{ try {{ return JSON.parse(localStorage.getItem(VK)||'{{}}'); }} catch {{ return {{}}; }} }}
function countView(id) {{
  const v = loadViews(); v[id] = (v[id]||0) + 1;
  localStorage.setItem(VK, JSON.stringify(v));
  const el = document.getElementById('v-' + id);
  if (el) el.textContent = '👁 ' + v[id];
}}
(function() {{
  const v = loadViews();
  Object.entries(v).forEach(([id,cnt]) => {{
    const el = document.getElementById('v-' + id);
    if (el) el.textContent = '👁 ' + cnt;
  }});
}})();
</script>

</body>
</html>"""


def build_article_page(article, all_articles, taxonomy):
    """記事個別ページのHTMLを生成する"""
    a = article
    aid = a.get("id","")
    title_ja = a.get("title_ja") or a.get("title","")
    title_en = a.get("title","")
    summary_ja = a.get("summary_ja") or a.get("summary","")
    summary_en = a.get("summary","")
    insight = a.get("insight","")
    imp = a.get("importance","中")
    imp_reason = a.get("importance_reason","")
    pub = a.get("published","")[:10]
    url = a.get("url","#")
    source_name = a.get("source_name","")
    source_tier = a.get("source_tier","B")
    main_id = a.get("tag_main_id","attack")
    main_label = a.get("tag_main_label","攻撃・脅威")
    subs = a.get("tag_subs",[])

    # 同じ大項目の関連記事を日付の新しい順に最大3件
    related = []
    for other in all_articles:
        if other.get("id") == aid:
            continue
        if other.get("tag_main_id") == main_id:
            related.append(other)
    related.sort(key=lambda x: x.get("published",""), reverse=True)
    related = related[:3]

    related_html = ""
    if related:
        related_items = []
        for r in related:
            r_pub = r.get("published","")[:10]
            r_title = r.get("title_ja") or r.get("title","")
            r_imp = r.get("importance","中")
            r_src = r.get("source_name","")
            r_id = r.get("id","")
            related_items.append(
                f'<a href="{r_id}.html" class="rel-item">'
                f'<div class="rel-meta"><span class="rel-date">{r_pub}</span>'
                f'{imp_badge(r_imp)}<span class="rel-src">{r_src}</span></div>'
                f'<div class="rel-title">{r_title}</div></a>'
            )
        related_html = f"""<section class="ap-section">
  <h3 class="ap-sec-title">関連記事：同じ「{main_label}」の最近の記事</h3>
  <div class="rel-list">{"".join(related_items)}</div>
</section>"""

    subs_html = "".join(tag_sub_badge(s) for s in subs)

    # シェアURL（URLエンコード対応）
    from urllib.parse import quote
    site_url = f"https://ayudle.github.io/ai-security-news/article/{aid}.html"
    share_text_raw = f"{title_ja} | AI×セキュリティ ニュース日報"
    share_text_encoded = quote(share_text_raw, safe='')
    site_url_encoded = quote(site_url, safe='')
    twitter_url = f"https://x.com/intent/post?text={share_text_encoded}&url={site_url_encoded}"

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title_ja} | AI×セキュリティ ニュース日報</title>
<meta name="description" content="{summary_ja[:120]}">
<meta property="og:title" content="{title_ja}">
<meta property="og:description" content="{summary_ja[:120]}">
<meta property="og:url" content="{site_url}">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title_ja}">
<meta name="twitter:description" content="{summary_ja[:120]}">
<meta property="og:image" content="https://ayudle.github.io/ai-security-news/og-image.png">
<meta name="twitter:image" content="https://ayudle.github.io/ai-security-news/og-image.png">
<link rel="canonical" href="{site_url}">
<link rel="icon" type="image/png" href="../favicon.png">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "NewsArticle",
  "headline": "{title_ja}",
  "description": "{summary_ja[:200]}",
  "datePublished": "{pub}",
  "url": "{site_url}",
  "image": "https://ayudle.github.io/ai-security-news/og-image.png",
  "publisher": {{
    "@type": "Organization",
    "name": "AI×セキュリティ ニュース日報",
    "url": "https://ayudle.github.io/ai-security-news/"
  }},
  "author": {{
    "@type": "Person",
    "name": "Ayudle"
  }}
}}
</script>
<style>
:root{{--bg:#0f0f0e;--text:#e6e4dc;--dim:#6a6860;--border:#2a2a28;--accent:#378ADD;--card:#1a1a18;--insight-bg:#14243a;--insight-border:#378ADD}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);line-height:1.7}}
header{{border-bottom:1px solid var(--border);padding:16px 24px;display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}}
.logo{{font-size:18px;font-weight:700}}
.meta-top{{font-size:11px;color:var(--dim)}}
.back{{display:inline-block;padding:8px 16px;margin:16px 24px;color:var(--accent);text-decoration:none;font-size:13px}}
.back:hover{{text-decoration:underline}}
.ap{{max-width:720px;margin:0 auto;padding:16px 24px 60px}}
.ap-head{{border-bottom:1px solid var(--border);padding-bottom:24px;margin-bottom:24px}}
.ap-meta{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px;color:var(--dim);margin-bottom:12px}}
.ap-tier{{display:inline-block;padding:2px 8px;border-radius:4px;background:var(--card);color:var(--accent);font-weight:600}}
.ap-src{{color:var(--text)}}
.ap-title{{font-size:26px;font-weight:700;color:#fff;margin:8px 0;line-height:1.4}}
.ap-section{{margin-bottom:32px}}
.ap-sec-title{{font-size:11px;font-weight:700;letter-spacing:.1em;color:var(--dim);text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)}}
.ap-body{{font-size:15px;line-height:1.85;color:var(--text)}}
.insight-box{{background:var(--insight-bg);border-left:3px solid var(--insight-border);padding:16px 20px;border-radius:4px;margin-top:12px}}
.insight-lbl{{display:block;font-size:11px;font-weight:700;color:var(--accent);margin-bottom:8px;letter-spacing:.05em}}
.imp-box{{padding:12px 16px;background:var(--card);border-radius:4px;margin-top:12px;font-size:13px;color:var(--dim)}}
.tags-box{{display:flex;flex-wrap:wrap;gap:6px}}
.tag-main{{display:inline-block;padding:4px 10px;border-radius:4px;font-size:12px;font-weight:600}}
.tag-sub{{display:inline-block;padding:4px 10px;border-radius:4px;font-size:12px;background:var(--card);color:var(--text);border:1px solid var(--border)}}
.orig-box{{background:var(--card);padding:16px;border-radius:4px;font-size:13px}}
.orig-box > div{{margin-bottom:6px}}
.orig-box .lbl{{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}}
.orig-en{{font-style:italic;color:var(--dim);margin-top:8px;font-size:12px;line-height:1.6}}
.actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}}
.btn{{display:inline-block;padding:10px 16px;border-radius:4px;text-decoration:none;font-size:13px;font-weight:500;cursor:pointer;border:none;font-family:inherit}}
.btn-primary{{background:var(--accent);color:#fff}}
.btn-primary:hover{{opacity:.9}}
.btn-secondary{{background:var(--card);color:var(--text);border:1px solid var(--border)}}
.btn-secondary:hover{{border-color:var(--accent)}}
.rel-list{{display:flex;flex-direction:column;gap:8px}}
.rel-item{{display:block;background:var(--card);padding:12px 16px;border-radius:4px;text-decoration:none;color:inherit;border:1px solid transparent;transition:border-color .15s}}
.rel-item:hover{{border-color:var(--accent)}}
.rel-meta{{display:flex;gap:8px;align-items:center;font-size:11px;color:var(--dim);margin-bottom:4px}}
.rel-date{{color:var(--dim)}}
.rel-src{{color:var(--text)}}
.rel-title{{font-size:14px;font-weight:500;line-height:1.5;color:var(--text)}}
footer{{text-align:center;font-size:10px;color:var(--dim);padding:20px;border-top:1px solid var(--border);margin-top:16px}}
</style>
</head>
<body>
<header>
  <div class="logo">AI×セキュリティ ニュース日報</div>
</header>

<a href="../#today" class="back">← 本日のニュースに戻る</a>

<article class="ap">
  <div class="ap-head">
    <div class="ap-meta">
      <span class="ap-tier">{tier_label(source_tier)}</span>
      <span class="ap-src">{source_name}</span>
      <span>{pub}</span>
      {imp_badge(imp)}
    </div>
    <h1 class="ap-title">{title_ja}</h1>
  </div>

  <section class="ap-section">
    <h3 class="ap-sec-title">要約</h3>
    <div class="ap-body">{summary_ja}</div>
  </section>

  {"<section class='ap-section'><h3 class='ap-sec-title'>CISO視点での示唆・学び</h3><div class='insight-box'><span class='insight-lbl'>示唆・学び</span>" + insight + "</div></section>" if insight else ""}

  {"<section class='ap-section'><h3 class='ap-sec-title'>重要度判定の理由</h3><div class='imp-box'>" + imp_reason + "</div></section>" if imp_reason else ""}

  <section class="ap-section">
    <h3 class="ap-sec-title">タグ</h3>
    <div class="tags-box">
      {tag_main_badge(main_id, main_label)}
      {subs_html}
    </div>
  </section>

  <section class="ap-section">
    <h3 class="ap-sec-title">元記事情報</h3>
    <div class="orig-box">
      <div class="lbl">原題</div>
      <div>{title_en}</div>
      <div class="lbl" style="margin-top:10px">ソース・公開日</div>
      <div>{source_name} / {pub}</div>
      <div class="orig-en">{summary_en[:300]}</div>
    </div>
    <div class="actions">
      <a href="{url}" target="_blank" rel="noopener" class="btn btn-primary">🔗 元記事を読む（外部サイト）</a>
      <a href="{twitter_url}" target="_blank" rel="noopener" class="btn btn-secondary">𝕏 でシェア</a>
      <button onclick="navigator.clipboard.writeText('{site_url}').then(()=>alert('URLをコピーしました'))" class="btn btn-secondary">📋 URLをコピー</button>
    </div>
  </section>

  {related_html}
</article>

<footer>
  各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。<br>
  <p style="margin-top:4px">Powered by Gemini 2.5 Flash + GitHub Actions（完全無料）</p>
</footer>

</body>
</html>"""


def main():
    if not os.path.exists(DATA_PATH):
        print(f"[ERROR] {DATA_PATH} なし"); return
    with open(DATA_PATH,"r",encoding="utf-8") as f:
        data = json.load(f)
    os.makedirs("docs", exist_ok=True)
    with open(OUT_PATH,"w",encoding="utf-8") as f:
        f.write(build_html(data))
    print(f"生成完了: {OUT_PATH} ({len(data.get('articles',[]))}件)")
    os.makedirs("docs/archive", exist_ok=True)
    for day in data.get("history",[]):
        d = day.get("date","")
        arc = {**data, "today":d, "articles":day.get("articles",[]), "history":[]}
        arc_html = build_html(arc)
        arc_html = arc_html.replace(
            "onclick=\"switchTab('today',this)\">本日のニュース",
            "onclick=\"location.href='/ai-security-news/#today'\">本日のニュース"
        ).replace(
            "onclick=\"switchTab('popular',this)\">人気記事",
            "onclick=\"location.href='/ai-security-news/#popular'\">人気記事"
        ).replace(
            "onclick=\"switchTab('archive',this)\">アーカイブ",
            "onclick=\"location.href='/ai-security-news/#archive'\">アーカイブ"
        ).replace(
            "onclick=\"switchTab('trend',this)\">トレンド分析",
            "onclick=\"location.href='/ai-security-news/#trend'\">トレンド分析"
        ).replace(
            '<a href="about.html" class="tab"',
            '<a href="/ai-security-news/about.html" class="tab"'
        )
        with open(f"docs/archive/{d}.html","w",encoding="utf-8") as f:
            f.write(arc_html)
    print(f"アーカイブ: {len(data.get('history',[]))}日分")

    # 記事個別ページ生成（全履歴の記事 + 本日の記事）
    os.makedirs("docs/article", exist_ok=True)
    all_articles = list(data.get("articles", []))
    for day in data.get("history", []):
        all_articles.extend(day.get("articles", []))
    # 重複除去（id基準）
    seen_ids = set()
    unique_articles = []
    for a in all_articles:
        aid = a.get("id")
        if aid and aid not in seen_ids:
            seen_ids.add(aid)
            unique_articles.append(a)

    taxonomy = data.get("taxonomy", {})
    article_count = 0
    for a in unique_articles:
        aid = a.get("id")
        if not aid:
            continue
        html = build_article_page(a, unique_articles, taxonomy)
        with open(f"docs/article/{aid}.html", "w", encoding="utf-8") as f:
            f.write(html)
        article_count += 1
    print(f"個別記事ページ: {article_count}件")

    # 月別アーカイブJSON生成
    from collections import defaultdict
    monthly = defaultdict(list)
    for day in data.get('history', []):
        d = day.get('date', '')
        if len(d) >= 7:
            monthly[d[:7]].extend(day.get('articles', []))

    os.makedirs('docs/data/archive', exist_ok=True)

    index = [{'date': d.get('date',''), 'count': len(d.get('articles',[]))} for d in data.get('history',[])]
    with open('docs/data/archive/index.json', 'w', encoding='utf-8') as f:
        json.dump({'days': index}, f, ensure_ascii=False, indent=2)

    for month, articles in monthly.items():
        with open(f'docs/data/archive/{month}.json', 'w', encoding='utf-8') as f:
            json.dump({'month': month, 'articles': articles}, f, ensure_ascii=False, indent=2)

    print(f'月別アーカイブ: {len(monthly)}ヶ月分')

    # sitemap.xml 生成
    site_url = 'https://ayudle.github.io/ai-security-news'
    sitemap_urls = [
        {'loc': f'{site_url}/', 'priority': '1.0', 'changefreq': 'daily'},
    ]
    # 個別記事ページ
    for a in unique_articles:
        aid = a.get('id')
        pub = a.get('published', '')[:10]
        if aid:
            sitemap_urls.append({
                'loc': f'{site_url}/article/{aid}.html',
                'priority': '0.8',
                'changefreq': 'weekly',
                'lastmod': pub
            })
    # 日別アーカイブ
    for day in data.get('history', []):
        d = day.get('date', '')
        if d:
            sitemap_urls.append({
                'loc': f'{site_url}/archive/{d}.html',
                'priority': '0.6',
                'changefreq': 'monthly',
                'lastmod': d
            })

    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in sitemap_urls:
        sitemap_xml += '  <url>\n'
        sitemap_xml += f'    <loc>{u["loc"]}</loc>\n'
        if 'lastmod' in u:
            sitemap_xml += f'    <lastmod>{u["lastmod"]}</lastmod>\n'
        sitemap_xml += f'    <changefreq>{u["changefreq"]}</changefreq>\n'
        sitemap_xml += f'    <priority>{u["priority"]}</priority>\n'
        sitemap_xml += '  </url>\n'
    sitemap_xml += '</urlset>\n'

    with open('docs/sitemap.xml', 'w', encoding='utf-8') as f:
        f.write(sitemap_xml)
    print(f'sitemap.xml: {len(sitemap_urls)}件')

    # robots.txt 生成
    robots_txt = f"""User-agent: *
Allow: /

Sitemap: {site_url}/sitemap.xml
"""
    with open('docs/robots.txt', 'w', encoding='utf-8') as f:
        f.write(robots_txt)
    print('robots.txt: generated')

if __name__ == "__main__":
    main()
