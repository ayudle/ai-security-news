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

def tag_layer_badge(layer):
    return f'<span class="tag-layer">{layer}</span>'

def tag_kw_badge(kw):
    return f'<span class="tag-kw">{kw}</span>'

def article_card(a, rank=None):
    rank_html    = f'<span class="rank">#{rank}</span>' if rank else ""
    pub          = a.get("published","")[:10]
    views        = a.get("views", 0)
    insight      = a.get("insight","")
    imp_reason   = a.get("importance_reason","")
    reason_html  = f'<span class="imp-reason" title="{imp_reason}">?</span>' if imp_reason else ""
    main_id      = a.get("tag_main_id","attack")
    main_label   = a.get("tag_main_label","攻撃・脅威")
    subs_html    = "".join(tag_sub_badge(s) for s in a.get("tag_subs",[]))
    layers_html  = "".join(tag_layer_badge(l) for l in a.get("affected_layers",[]))
    kws_html     = "".join(tag_kw_badge(k) for k in a.get("related_keywords",[])[:5])
    summary      = a.get("summary_ja") or a.get("summary", "")
    preview_txt  = (summary[:80] + "…") if len(summary) > 80 else summary
    preview_html = f'<div class="article-preview">{preview_txt}</div>' if preview_txt else ""
    # 示唆スニペット（タイトル直下1〜2行）
    insight_snippet = ""
    if insight:
        itxt = (insight[:80] + "…") if len(insight) > 80 else insight
        insight_snippet = f'<div class="insight-snippet">{itxt}</div>'
    # レイヤーは常時表示、related_keywordsは折りたたみ
    layers_row = f'<div class="tags tags-meta">{layers_html}</div>' if layers_html else ""
    kw_section = ""
    if kws_html:
        kid = f"kw-{a.get('id','')}"
        kw_section = (f'<div class="kw-fold">'
                      f'<div class="tags tags-meta" id="{kid}" style="display:none">{kws_html}</div>'
                      f'<button class="kw-btn" onclick="toggleKw(\'{kid}\',this);event.stopPropagation()">タグを表示</button>'
                      f'</div>')

    return f"""<article class="card" data-id="{a.get('id','')}" data-main="{main_id}" onclick="navigateCard('{a.get('id','')}')">
  <div class="cm">
    {rank_html}
    <span class="tier">{tier_label(a.get('source_tier','B'))}</span>
    <span class="src">{a.get('source_name','')}</span>
    <span class="dt">{pub}</span>
    {imp_badge(a.get('importance','中'))}{reason_html}
    <span class="vw" id="v-{a.get('id','')}">👁 {views}</span>
  </div>
  <h2 class="ct"><a href="/ai-security-news/article/{a.get('id','')}.html" onclick="event.stopPropagation()">{a.get('title_ja') or a.get('title','')}</a></h2>
  {insight_snippet}
  {preview_html}
  <div class="tags">
    {tag_main_badge(main_id, main_label)}
    {subs_html}
  </div>
  {layers_row}
  {kw_section}
  <div class="cf">出典: <a href="{a.get('url','#')}" target="_blank" rel="noopener" onclick="event.stopPropagation()">{a.get('source_name','')}</a>
  <em class="orig">"{a.get('title','')}"</em></div>
</article>"""


def build_analytics(history, taxonomy):
    """過去30日・7日のタグ集計データを生成"""
    now = datetime.now(JST)

    # 日付ごとの中項目カウント（スパイク検出用）
    daily_sub   = defaultdict(lambda: defaultdict(int))   # date -> sub -> count
    layer_daily = defaultdict(lambda: defaultdict(int))   # date -> layer -> count
    main_30  = Counter()
    sub_30   = Counter()
    main_7   = Counter()
    sub_7    = Counter()
    layer_7  = Counter()
    kw_7     = Counter()

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
                for l in a.get("affected_layers", []):
                    layer_7[l] += 1
                    layer_daily[d][l] += 1
                for kw in a.get("related_keywords", []):
                    kw_norm = kw.strip()
                    if kw_norm:
                        kw_7[kw_norm] += 1

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

    today_implication = history[0].get("today_implication", "") if history else ""

    _layers_order = ["デバイス/エッジ", "ネットワーク", "クラウド/サーバー", "アプリ/API", "データ/AI", "ガバナンス/規制"]
    _dates_7  = [(now - timedelta(days=6-i)) for i in range(7)]
    _date_keys = [dt.strftime("%Y-%m-%d") for dt in _dates_7]
    _date_lbls = [dt.strftime("%m/%d")     for dt in _dates_7]
    layer_heatmap = {
        "dates": _date_lbls,
        "rows": [
            {"layer": layer, "counts": [layer_daily[dk].get(layer, 0) for dk in _date_keys]}
            for layer in _layers_order
        ],
    }

    return {
        "main_30":  [(k, v, taxonomy.get(k,{}).get("label",k)) for k,v in main_30.most_common()],
        "main_7":   [(k, v, taxonomy.get(k,{}).get("label",k)) for k,v in main_7.most_common()],
        "sub_7":    sub_7.most_common(15),
        "spikes":   spikes[:5],
        "imp_list": imp_all.most_common(),
        "total_articles": sum(len(d.get("articles",[])) for d in history),
        "total_days":     len(history),
        "today_implication": today_implication,
        "layer_7":       layer_7.most_common(),
        "kw_7":          kw_7.most_common(30),
        "layer_heatmap": layer_heatmap,
    }


def build_html(data, weekly_list=None):
    weekly_list = weekly_list or []
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

    # 週次レポートリンク（#todayペイン内・示唆ボックス直下）
    weekly_today_link = ""
    if weekly_list:
        latest_w = weekly_list[0]
        wp = latest_w.get("period", {})
        wps = wp.get("start", ""); wpe = wp.get("end", "")
        wps_s = wps[5:].replace("-", "/") if len(wps) >= 10 else wps
        wpe_s = wpe[5:].replace("-", "/") if len(wpe) >= 10 else wpe
        weekly_today_link = (
            f'<a href="weekly/{wpe}.html" '
            f'style="display:inline-block;font-size:11px;color:#378ADD;'
            f'text-decoration:none;margin-top:8px">'
            f'&#x1F4CA; 先週のレポート（{wps_s}〜{wpe_s}）を読む →</a>'
        )

    # #weeklyペイン HTML
    if not weekly_list:
        weekly_pane_html = (
            '<div class="pane" id="pane-weekly">\n'
            '  <p class="plabel">週次レポート</p>\n'
            '  <p class="empty">週次レポートはまだありません。毎週月曜日に自動生成されます。</p>\n'
            '</div>'
        )
    else:
        latest_w = weekly_list[0]
        wp = latest_w.get("period", {})
        wps = wp.get("start", ""); wpe = wp.get("end", "")
        wps_s = wps[5:].replace("-", "/") if len(wps) >= 10 else wps
        wpe_s = wpe[5:].replace("-", "/") if len(wpe) >= 10 else wpe
        w_summary = latest_w.get("executive_summary", "")
        w_summary_short = (w_summary[:200] + "…") if len(w_summary) > 200 else w_summary
        latest_card = (
            f'<div style="background:#14243a;border-left:3px solid #378ADD;'
            f'padding:14px 18px;border-radius:4px;margin-bottom:18px">'
            f'<div style="font-size:11px;font-weight:700;color:#378ADD;'
            f'letter-spacing:.05em;margin-bottom:6px">最新レポート（{wps_s}〜{wpe_s}）</div>'
            f'<div style="font-size:13px;line-height:1.8;color:#e6e4dc;margin-bottom:10px">'
            f'{w_summary_short}</div>'
            f'<a href="weekly/{wpe}.html" style="font-size:12px;color:#378ADD">'
            f'全文を読む →</a></div>'
        )
        past_rows = ""
        for w in weekly_list:
            wp2 = w.get("period", {})
            wps2 = wp2.get("start", ""); wpe2 = wp2.get("end", "")
            wps2_s = wps2[5:].replace("-", "/") if len(wps2) >= 10 else wps2
            wpe2_s = wpe2[5:].replace("-", "/") if len(wpe2) >= 10 else wpe2
            wn = w.get("total_articles", "?")
            past_rows += (
                f'<div class="arc-row">'
                f'<a href="weekly/{wpe2}.html" class="arc-link">{wps2_s}〜{wpe2_s}</a>'
                f'<span class="arc-n">{wn}件</span></div>\n'
            )
        weekly_pane_html = (
            '<div class="pane" id="pane-weekly">\n'
            '  <p class="plabel">週次レポート</p>\n'
            f'  {latest_card}\n'
            '  <p class="plabel" style="margin-top:16px">過去のレポート</p>\n'
            f'  <div style="margin-top:8px">{past_rows}</div>\n'
            '</div>'
        )

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
{{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "AI×セキュリティ ニュース日報",
  "url": "https://ayudle.github.io/ai-security-news/",
  "description": "サイバーセキュリティ×AI分野の最新ニュースを毎日自動収集・日本語要約",
  "publisher": {{
    "@type": "Organization",
    "name": "AI×セキュリティ ニュース日報",
    "url": "https://ayudle.github.io/ai-security-news/"
  }}
}}
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
.tags-meta{{margin-top:3px}}
.tag-layer{{font-size:9px;padding:1px 6px;border-radius:99px;background:#0d2233;border:1px solid #1a4060;color:#6aabdd}}
.tag-kw{{font-size:9px;padding:1px 5px;border-radius:99px;background:#1e1e1c;border:1px solid #2e2e2c;color:#6a6860}}
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
.kw-cloud{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:4px 0}}
.kw-bubble{{border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:default;text-align:center;padding:6px;line-height:1.25;word-break:break-word;overflow:hidden;transition:opacity .15s;flex-shrink:0}}
.kw-bubble:hover{{opacity:.75}}
.kw-bubble-word{{color:#fff;font-weight:600}}
.kw-bubble-cnt{{color:rgba(255,255,255,.6);font-size:8px;margin-top:1px}}
.hm-legend{{display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap}}
.hm-lg-lbl{{font-size:10px;color:var(--dim);font-weight:700;letter-spacing:.05em}}
.hm-lg-item{{display:flex;align-items:center;gap:4px;font-size:10px;color:var(--dim)}}
.hm-lg-cell{{width:14px;height:14px;border-radius:3px;display:inline-block;flex-shrink:0}}
.hm-grid{{display:grid;grid-template-columns:88px repeat(7,1fr);gap:3px;align-items:center}}
.hm-th{{font-size:9px;color:var(--dim);text-align:center;padding-bottom:2px}}
.hm-lb{{font-size:10px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:4px}}
.hm-cell{{height:22px;border-radius:3px;cursor:default;transition:filter .1s}}
.hm-cell:hover{{filter:brightness(1.4)}}
@media(max-width:600px){{.hm-grid{{grid-template-columns:64px repeat(7,1fr);gap:2px}}.hm-lb{{font-size:9px}}.hm-cell{{height:16px}}}}
.article-preview{{font-size:12px;color:var(--muted);line-height:1.55;margin-bottom:6px}}
.insight-snippet{{font-size:12px;color:#9ca3af;line-height:1.55;margin-bottom:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.kw-fold{{margin-top:2px}}
.kw-btn{{font-size:9px;background:transparent;border:1px solid var(--border);color:var(--dim);border-radius:99px;padding:2px 8px;cursor:pointer;margin-top:4px;font-family:inherit;transition:color .15s,border-color .15s}}
.kw-btn:hover{{color:var(--muted);border-color:#3a3a38}}
.hidden{{display:none}}
@media(max-width:600px){{.article-preview{{display:none}}}}
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
  <span class="hs">信頼できるソースのみ・毎日自動更新・最大10件/日</span>
  <span class="hu">更新: {updated} JST</span>
</header>

<div class="tab-bar">
  <a href="#today"   class="tab">本日のニュース</a>
  <a href="#popular" class="tab">人気記事</a>
  <a href="#archive" class="tab">アーカイブ</a>
  <a href="#trend"   class="tab">トレンド分析</a>
  <a href="#weekly"  class="tab">週次レポート</a>
  <a href="#about"   class="tab">About</a>
</div>

<div class="pane" id="pane-today">
  <div id="today-impl-box" style="display:none;background:#0d1b2e;border-left:3px solid #378ADD;border-radius:4px;padding:12px 16px;margin-bottom:16px">
    <div style="font-size:10px;font-weight:700;color:#378ADD;letter-spacing:.05em;text-transform:uppercase;margin-bottom:6px">本日の示唆</div>
    <div id="today-impl-text" style="font-size:12px;line-height:1.8;color:#c0beb6"></div>
    <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-top:8px">
      <a href="#trend" style="font-size:11px;color:#378ADD;text-decoration:none">→ トレンド分析で詳しく見る</a>
      {weekly_today_link}
    </div>
  </div>
  <p class="plabel">{today} のニュース（{len(articles)}件）</p>
  {today_html}
</div>

<div class="pane" id="pane-popular">
  <p class="plabel">人気記事 — 過去7日間 <span style="display:inline-block;padding:2px 8px;margin-left:8px;font-size:10px;font-weight:700;background:#BA7517;color:#0f0f0e;border-radius:4px;letter-spacing:.05em">BETA</span></p>
  <div style="background:#1a1a18;border-left:3px solid #BA7517;padding:12px 16px;border-radius:4px;margin-bottom:16px">
    <p style="font-size:12px;color:#e6e4dc;line-height:1.7;margin:0">
      <strong style="color:#BA7517">Beta機能</strong><br>
      この一覧は<strong>あなたがこの端末で閲覧した記事</strong>を回数順に表示しています。他の方の閲覧情報は含まれていません。<br>
      端末を変えると一覧はリセットされます。今後、より便利な機能に進化させていく予定です。
    </p>
  </div>
  {popular_html}
</div>

<div class="pane" id="pane-archive">
  <p class="plabel">過去のニュース</p>
  <div class="arc-note">
    過去最大90日分のアーカイブを保存しています。毎日自動更新されます。<br>
    各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。<br>日本語要約・タグ・示唆はLLMにより自動生成されており、誤りや不正確な情報を含む可能性があります。重要な判断には必ず元記事をご確認ください。
  </div>
  <div style="margin-top:12px">
    {archive_rows if archive_rows else '<p class="empty">蓄積中...</p>'}
  </div>
</div>

<div class="pane" id="pane-trend">
  <p class="plabel">トレンド分析</p>

  <div id="today-implication-box" style="display:none;background:#14243a;border-left:3px solid #378ADD;padding:14px 18px;border-radius:4px;margin-bottom:18px">
    <div style="font-size:11px;font-weight:700;color:#378ADD;letter-spacing:.05em;margin-bottom:6px">本日の示唆</div>
    <div id="today-implication-text" style="font-size:13px;line-height:1.8;color:#e6e4dc"></div>
    <div style="font-size:10px;color:#6a6860;margin-top:8px">AI for Security / Security for AI / CDC・SOCへの示唆</div>
  </div>

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

    <div class="dc" id="dc-layer" style="grid-column:1/-1">
      <div class="dc-title">影響レイヤー分布（過去7日）</div>
      <div class="dc-sub">各記事が影響するインフラ・ガバナンス層の内訳</div>
      <div id="layer-bars"></div>
    </div>

    <div class="dc" id="dc-kw" style="grid-column:1/-1">
      <div class="dc-title">キーワードクラウド（過去7日）</div>
      <div class="dc-sub">頻出キーワードをフォントサイズで表現（大きいほど多出現）</div>
      <div class="kw-cloud" id="kw-cloud"></div>
    </div>

    <div class="dc" id="dc-heatmap" style="grid-column:1/-1">
      <div class="dc-title">6階層ヒートマップ（過去7日）</div>
      <div class="dc-sub">日付×インフラ階層の記事件数</div>
      <div class="hm-legend">
        <span class="hm-lg-lbl">凡例</span>
        <span class="hm-lg-item"><span class="hm-lg-cell" style="background:#1e1e1c"></span>0件</span>
        <span class="hm-lg-item"><span class="hm-lg-cell" style="background:rgba(55,138,221,.2)"></span>少</span>
        <span class="hm-lg-item"><span class="hm-lg-cell" style="background:rgba(55,138,221,.55)"></span>中</span>
        <span class="hm-lg-item"><span class="hm-lg-cell" style="background:rgba(55,138,221,.9)"></span>多</span>
        <span class="hm-lg-item" style="margin-left:4px;font-size:10px;color:var(--dim)">※各層の固有色で表示</span>
      </div>
      <div id="layer-heatmap"></div>
    </div>

  </div>
</div>


{weekly_pane_html}

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
        <p style="margin-bottom:1rem">X（旧Twitter）で最新ニュースを毎日発信しています。フォローお待ちしています。</p>
        <a href="https://x.com/ayudle_aisec" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:8px;padding:10px 18px;background:#1a1a18;border:1px solid #2a2a28;border-radius:6px;text-decoration:none;color:#e6e4dc;font-size:13px;font-weight:500;transition:border-color .15s" onmouseover="this.style.borderColor='#378ADD'" onmouseout="this.style.borderColor='#2a2a28'">
          <span style="font-size:14px;font-weight:700">X</span>
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
  <p>各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。<br>日本語要約・タグ・示唆はLLMにより自動生成されており、誤りや不正確な情報を含む可能性があります。重要な判断には必ず元記事をご確認ください。</p>
  <p style="margin-top:4px">Powered by Gemini 2.5 Flash + GitHub Actions（完全無料）</p>
  <p style="margin-top:8px"><a href="https://x.com/ayudle_aisec" target="_blank" rel="noopener" style="color:var(--dim);text-decoration:none;font-size:10px">X: @ayudle_aisec</a></p>
</footer>

<script>
const ANA = {ana_json};
const TAX = {tax_json};
const IMP_COLORS = {{"高":"#E24B4A","中":"#BA7517","低":"#639922"}};
const MAIN_COLORS = {{"attack":"#E24B4A","vuln":"#BA7517","ai_sec":"#378ADD","ai_risk":"#7F77DD","policy":"#1D9E75","incident":"#D85A30","biz_tech":"#639922"}};
const LAYER_COLORS = {{"デバイス/エッジ":"#639922","ネットワーク":"#378ADD","クラウド/サーバー":"#1D9E75","アプリ/API":"#BA7517","データ/AI":"#7F77DD","ガバナンス/規制":"#98968e"}};

function showTab(id) {{
  var valid = ['today','popular','archive','trend','weekly','about'];
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

function renderKwCloud(containerId, data) {{
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!data || !data.length) {{ el.innerHTML='<p class="empty">データ蓄積中...</p>'; return; }}
  const top = data.slice(0, 15);
  const max = top[0][1] || 1;
  el.innerHTML = top.map(([kw, cnt]) => {{
    const t    = Math.sqrt(cnt / max);
    const size = Math.round(52 + t * 36);
    const bgOp = (0.2 + t * 0.65).toFixed(2);
    const fs   = kw.length > 8 ? 9 : kw.length > 5 ? 10 : 11;
    return `<div class="kw-bubble" style="width:${{size}}px;height:${{size}}px;background:rgba(55,138,221,${{bgOp}});font-size:${{fs}}px" title="${{cnt}}件">` +
           `<span class="kw-bubble-word">${{kw}}</span>` +
           `<span class="kw-bubble-cnt">${{cnt}}件</span></div>`;
  }}).join('');
}}

function hexToRgb(hex) {{
  return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)];
}}

function renderHeatmap(containerId, data) {{
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!data || !data.rows || !data.rows.length) {{ el.innerHTML='<p class="empty">データ蓄積中...</p>'; return; }}
  const allCounts = data.rows.flatMap(r => r.counts);
  const max = Math.max(...allCounts, 1);
  let html = '<div class="hm-grid">';
  html += '<div class="hm-th"></div>';
  data.dates.forEach(d => {{ html += `<div class="hm-th">${{d}}</div>`; }});
  data.rows.forEach(row => {{
    const color = LAYER_COLORS[row.layer] || '#378ADD';
    const [r,g,b] = hexToRgb(color);
    html += `<div class="hm-lb" title="${{row.layer}}">${{row.layer}}</div>`;
    row.counts.forEach(cnt => {{
      const bg  = cnt === 0 ? '#1e1e1c' : `rgba(${{r}},${{g}},${{b}},${{Math.max(0.18, cnt/max).toFixed(2)}})`;
      const tip = cnt > 0 ? cnt + '件' : 'なし';
      html += `<div class="hm-cell" style="background:${{bg}}" title="${{tip}}"></div>`;
    }});
  }});
  html += '</div>';
  el.innerHTML = html;
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

function renderImplication(text, textElId, boxElId, hd) {{
  var el = document.getElementById(textElId);
  var box = document.getElementById(boxElId);
  if (!el || !box) return;
  var fs = hd ? '10px' : '11px';
  var mt = hd ? '10px' : '14px';
  el.innerHTML = text
    .replace(/★[^\\n]*/g, '')
    .replace(/【([^】]+)】\\n?/g,
      '<span style="display:block;font-size:'+fs+';font-weight:700;color:#378ADD;letter-spacing:.04em;margin-top:'+mt+';margin-bottom:2px">【$1】</span>')
    .replace(/\\n/g, '<br>');
  box.style.display = '';
}}

function initDashboard() {{
  if (ANA.today_implication) {{
    renderImplication(ANA.today_implication, 'today-implication-text', 'today-implication-box', false);
    renderImplication(ANA.today_implication, 'today-impl-text', 'today-impl-box', true);
  }}

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

  // 影響レイヤーバー
  if (ANA.layer_7 && ANA.layer_7.length) {{
    renderBars('layer-bars', ANA.layer_7, label => LAYER_COLORS[label]||'#378ADD');
  }} else {{
    const dcLayer = document.getElementById('dc-layer');
    if (dcLayer) dcLayer.classList.add('hidden');
  }}

  // キーワードクラウド
  if (ANA.kw_7 && ANA.kw_7.length) {{
    renderKwCloud('kw-cloud', ANA.kw_7);
  }} else {{
    const dcKw = document.getElementById('dc-kw');
    if (dcKw) dcKw.classList.add('hidden');
  }}

  // 6階層ヒートマップ
  const hmData = ANA.layer_heatmap || null;
  const hmAllZero = !hmData || !hmData.rows || hmData.rows.every(r => r.counts.every(c => c === 0));
  if (!hmAllZero) {{
    renderHeatmap('layer-heatmap', hmData);
  }} else {{
    const dcHm = document.getElementById('dc-heatmap');
    if (dcHm) dcHm.classList.add('hidden');
  }}

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
function navigateCard(id) {{
  if (!id) return;
  countView(id);
  location.href = '/ai-security-news/article/' + id + '.html';
}}
function toggleKw(id, btn) {{
  var el = document.getElementById(id);
  if (!el) return;
  var open = btn.dataset.open === '1';
  el.style.display = open ? 'none' : '';
  btn.dataset.open = open ? '0' : '1';
  btn.textContent = open ? 'タグを表示' : 'タグを隠す';
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

    # シェアURL（URLエンコード対応 + 完成形テンプレ + 動的ハッシュタグ）
    from urllib.parse import quote
    site_url = f"https://ayudle.github.io/ai-security-news/article/{aid}.html"

    # tag_subs から動的にハッシュタグを選定
    HASHTAG_MAP = {
        "プロンプトインジェクション": "プロンプトインジェクション",
        "LLMセキュリティ": "LLMセキュリティ",
        "モデル汚染": "モデル汚染",
        "敵対的攻撃": "敵対的攻撃",
        "AIを使った攻撃": "AI攻撃",
        "AIを使った防御": "AI防御",
        "ハルシネーション": "ハルシネーション",
        "EU AI法": "EUAI法",
        "コンプライアンス": "AIコンプライアンス",
        "標準化": "AI標準化",
        "安全性評価": "AI安全性",
        "アライメント": "アライメント",
        "プライバシー侵害": "プライバシー",
        "サプライチェーン攻撃": "サプライチェーン",
        "モデル逆転攻撃": "モデル逆転",
        "バイアス・差別": "AIバイアス",
        "誤情報生成": "AI誤情報",
        "著作権": "AI著作権",
    }
    extra_tags = []
    for s in subs:
        if s in HASHTAG_MAP and HASHTAG_MAP[s] not in extra_tags:
            extra_tags.append(HASHTAG_MAP[s])
        if len(extra_tags) >= 2:
            break

    # 主軸ハッシュタグを記事タイプに応じて切り替え
    PRIMARY_TAG_BY_MAIN = {
        "ai_sec": ["AIセキュリティ"],
        "ai_risk": ["AIリスク", "AIガバナンス"],
        "vuln": ["脆弱性", "サイバーセキュリティ"],
        "attack": ["サイバー攻撃", "サイバーセキュリティ"],
        "incident": ["セキュリティインシデント", "サイバーセキュリティ"],
        "policy": ["セキュリティ規制", "サイバーセキュリティ"],
        "biz_tech": ["セキュリティ業界", "サイバーセキュリティ"],
    }
    primary_tags = PRIMARY_TAG_BY_MAIN.get(main_id, ["サイバーセキュリティ"])

    # 重複を避けつつ最大3個に絞る
    all_tags = []
    for tag in primary_tags + extra_tags:
        if tag not in all_tags:
            all_tags.append(tag)
        if len(all_tags) >= 3:
            break

    hashtags_str = " ".join([f"#{t}" for t in all_tags])

    share_text_raw = f"【AI×セキュリティニュース】\n\n{title_ja}\n\n{hashtags_str}"
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
      <a href="{twitter_url}" target="_blank" rel="noopener" class="btn btn-secondary">Xでシェア</a>
      <button onclick="navigator.clipboard.writeText('{site_url}').then(()=>alert('URLをコピーしました'))" class="btn btn-secondary">📋 URLをコピー</button>
    </div>
  </section>

  {related_html}
</article>

<footer>
  各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。<br>日本語要約・タグ・示唆はLLMにより自動生成されており、誤りや不正確な情報を含む可能性があります。重要な判断には必ず元記事をご確認ください。<br>
  <p style="margin-top:4px">Powered by Gemini 2.5 Flash + GitHub Actions（完全無料）</p>
  <p style="margin-top:8px"><a href="https://x.com/ayudle_aisec" target="_blank" rel="noopener" style="color:var(--dim);text-decoration:none;font-size:10px">X: @ayudle_aisec</a></p>
</footer>

</body>
</html>"""


def build_archive_page(day_data, date):
    """アーカイブページ（記事一覧のみ）を生成する"""
    articles = day_data.get("articles", [])
    n = len(articles)
    articles_html = "\n".join(article_card(a) for a in articles) if articles \
                    else '<p class="empty">この日の記事はありませんでした。</p>'
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{date} のニュース | AI×セキュリティ ニュース日報</title>
<meta name="description" content="{date} のAI×セキュリティニュース（{n}件）">
<link rel="icon" type="image/png" href="../favicon.png">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#0f0f0d;--card:#1a1a18;--card2:#222220;--text:#e6e4dc;--muted:#98968e;--dim:#6a6860;--border:#2a2a28;--accent:#378ADD;--r:10px}}
body{{font-family:-apple-system,"Helvetica Neue",sans-serif;background:var(--bg);color:var(--text);line-height:1.7;font-size:14px}}
a{{color:inherit;text-decoration:none}}
.hdr{{border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.ht{{font-size:15px;font-weight:700;color:#fff}}
.back{{display:inline-block;padding:8px 16px;margin:12px 24px;color:var(--accent);text-decoration:none;font-size:13px}}
.back:hover{{text-decoration:underline}}
.content{{max-width:860px;margin:0 auto;padding:16px 24px}}
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
.ct{{font-size:14px;font-weight:600;margin-bottom:6px;line-height:1.45}}
.ct a:hover{{color:var(--accent)}}
.article-preview{{font-size:12px;color:var(--muted);line-height:1.55;margin-bottom:6px}}
.tags{{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}}
.tag-main{{font-size:10px;padding:2px 8px;border-radius:99px;border:1px solid;font-weight:600}}
.tag-sub{{font-size:10px;padding:2px 7px;border-radius:99px;background:#222220;border:1px solid #333330;color:var(--muted)}}
.tags-meta{{margin-top:3px}}
.tag-layer{{font-size:9px;padding:1px 6px;border-radius:99px;background:#0d2233;border:1px solid #1a4060;color:#6aabdd}}
.tag-kw{{font-size:9px;padding:1px 5px;border-radius:99px;background:#1e1e1c;border:1px solid #2e2e2c;color:#6a6860}}
.cf{{font-size:10px;color:var(--dim)}}
.cf a{{color:var(--accent)}}
.orig{{font-style:italic;margin-left:4px}}
.empty{{font-size:12px;color:var(--dim);padding:1rem 0}}
.insight{{background:#0d1e36;border-left:3px solid var(--accent);border-radius:0 6px 6px 0;padding:7px 10px;margin-bottom:8px;font-size:11px;color:#85b7eb;line-height:1.55}}
.ins-lbl{{display:block;font-size:9px;font-weight:700;color:var(--accent);letter-spacing:.06em;margin-bottom:2px;text-transform:uppercase}}
.insight-snippet{{font-size:12px;color:#9ca3af;line-height:1.55;margin-bottom:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.kw-fold{{margin-top:2px}}
.kw-btn{{font-size:9px;background:transparent;border:1px solid var(--border);color:var(--dim);border-radius:99px;padding:2px 8px;cursor:pointer;margin-top:4px;font-family:inherit;transition:color .15s,border-color .15s}}
.kw-btn:hover{{color:var(--muted);border-color:#3a3a38}}
@media(max-width:600px){{.article-preview{{display:none}}}}
</style>
</head>
<body>
<header class="hdr">
  <span class="ht">AI×セキュリティ ニュース日報</span>
</header>

<a href="/ai-security-news/#today" class="back">← トップページに戻る</a>

<div class="content">
  <p class="plabel">{date} のニュース（{n}件）</p>
  {articles_html}
</div>

<footer style="text-align:center;font-size:10px;color:var(--dim);padding:20px;border-top:1px solid var(--border);margin-top:16px">
  <p>各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。<br>日本語要約・タグ・示唆はLLMにより自動生成されており、誤りや不正確な情報を含む可能性があります。重要な判断には必ず元記事をご確認ください。</p>
  <p style="margin-top:4px">Powered by Gemini 2.5 Flash + GitHub Actions（完全無料）</p>
  <p style="margin-top:8px"><a href="https://x.com/ayudle_aisec" target="_blank" rel="noopener" style="color:var(--dim);text-decoration:none;font-size:10px">X: @ayudle_aisec</a></p>
</footer>

<script>
const VK = 'aisc_v3';
function loadViews() {{ try {{ return JSON.parse(localStorage.getItem(VK)||'{{}}'); }} catch {{ return {{}}; }} }}
function countView(id) {{
  const v = loadViews(); v[id] = (v[id]||0) + 1;
  localStorage.setItem(VK, JSON.stringify(v));
  const el = document.getElementById('v-' + id);
  if (el) el.textContent = '👁 ' + v[id];
}}
function navigateCard(id) {{
  if (!id) return;
  countView(id);
  location.href = '/ai-security-news/article/' + id + '.html';
}}
function toggleKw(id, btn) {{
  var el = document.getElementById(id);
  if (!el) return;
  var open = btn.dataset.open === '1';
  el.style.display = open ? 'none' : '';
  btn.dataset.open = open ? '0' : '1';
  btn.textContent = open ? 'タグを表示' : 'タグを隠す';
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


LAYER_COLORS_WEEKLY = {
    "デバイス/エッジ":   "#639922",
    "ネットワーク":       "#378ADD",
    "クラウド/サーバー": "#1D9E75",
    "アプリ/API":         "#BA7517",
    "データ/AI":          "#7F77DD",
    "ガバナンス/規制":   "#98968e",
}


def load_weekly_list():
    """docs/weekly/*.json を読み込み、新しい順にリストを返す"""
    wdir = "docs/weekly"
    if not os.path.exists(wdir):
        return []
    result = []
    for fname in sorted(os.listdir(wdir), reverse=True):
        if not fname.endswith(".json"):
            continue
        try:
            with open(f"{wdir}/{fname}", "r", encoding="utf-8") as f:
                w = json.load(f)
            result.append({
                "date":              fname[:-5],
                "period":            w.get("period", {}),
                "executive_summary": w.get("executive_summary", ""),
                "total_articles":    w.get("total_articles", 0),
            })
        except Exception:
            continue
    return result


def build_weekly_html(weekly_data):
    """週次レポートの standalone HTML ページを生成する"""
    from urllib.parse import quote

    ps  = weekly_data.get("period", {}).get("start", "")
    pe  = weekly_data.get("period", {}).get("end", "")
    pss = ps[5:].replace("-", "/") if len(ps) >= 10 else ps
    pes = pe[5:].replace("-", "/") if len(pe) >= 10 else pe
    total       = weekly_data.get("total_articles", 0)
    exec_sum    = weekly_data.get("executive_summary", "")
    top_topics  = weekly_data.get("top_topics", [])
    layer_trends = weekly_data.get("layer_trends", [])
    kw_changes  = weekly_data.get("keyword_changes", [])
    next_week   = weekly_data.get("next_week_outlook", "")

    site_url = f"https://ayudle.github.io/ai-security-news/weekly/{pe}.html"
    share_text = f"【AI×セキュリティ 週次レポート {pss}〜{pes}】\n{exec_sum[:100]}…\n#AIセキュリティ #CISO"
    twitter_url = f"https://x.com/intent/post?text={quote(share_text, safe='')}&url={quote(site_url, safe='')}"

    # 重要トピック HTML
    topics_html = ""
    for t in top_topics:
        title   = t.get("title", "")
        summary = t.get("summary", "")
        aids    = t.get("article_ids", [])
        links   = " ".join(
            f'<a href="../article/{aid}.html" '
            f'style="font-size:10px;color:#378ADD;text-decoration:none">[{aid[:8]}]</a>'
            for aid in aids
        )
        topics_html += (
            f'<div style="background:#1a1a18;border:1px solid #2a2a28;'
            f'border-radius:10px;padding:14px 16px;margin-bottom:10px">'
            f'<div style="font-size:14px;font-weight:600;color:#e6e4dc;margin-bottom:6px">{title}</div>'
            f'<div style="font-size:13px;color:#98968e;line-height:1.7;margin-bottom:8px">{summary}</div>'
            f'<div>{links}</div></div>'
        )
    if not topics_html:
        topics_html = '<p style="font-size:12px;color:#6a6860">データなし</p>'

    # 6階層トレンド HTML
    layers_html = ""
    for l in layer_trends:
        lname  = l.get("layer_name", "")
        ltext  = l.get("trend_text", "")
        lcolor = LAYER_COLORS_WEEKLY.get(lname, "#378ADD")
        layers_html += (
            f'<div style="display:flex;gap:12px;padding:10px 0;'
            f'border-bottom:1px solid #2a2a28;align-items:flex-start">'
            f'<div style="min-width:90px;font-size:11px;font-weight:700;'
            f'color:{lcolor};padding-top:2px;flex-shrink:0">{lname}</div>'
            f'<div style="font-size:13px;color:#98968e;line-height:1.65">{ltext}</div></div>'
        )
    if not layers_html:
        layers_html = '<p style="font-size:12px;color:#6a6860">データなし</p>'

    # キーワード変動 HTML
    kw_html = ""
    if kw_changes:
        max_abs = max((abs(k.get("change", 0)) for k in kw_changes), default=1)
        for k in kw_changes[:8]:
            kw      = k.get("keyword", "")
            this_w  = k.get("this_week_count", 0)
            last_w  = k.get("last_week_count", 0)
            change  = k.get("change", 0)
            bar_pct = round(abs(change) / max(max_abs, 1) * 100)
            pct_abs = abs(round(change / max(last_w, 1) * 100))
            color   = "#E24B4A" if change > 0 else "#6a6860"
            sign    = "+" if change >= 0 else ""
            kw_html += (
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
                f'<div style="width:80px;font-size:11px;color:#e6e4dc;white-space:nowrap;'
                f'overflow:hidden;text-overflow:ellipsis">{kw}</div>'
                f'<div style="flex:1;height:5px;background:#2a2a28;border-radius:3px;overflow:hidden">'
                f'<div style="width:{bar_pct}%;height:100%;background:{color};border-radius:3px"></div></div>'
                f'<div style="font-size:10px;color:{color};width:55px;text-align:right">'
                f'{sign}{change}件({sign}{pct_abs}%)</div>'
                f'<div style="font-size:10px;color:#6a6860;width:40px;text-align:right">'
                f'今週{this_w}件</div></div>'
            )
    else:
        kw_html = '<p style="font-size:12px;color:#6a6860">先週比データがまだありません</p>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>週次レポート {pss}〜{pes} | AI×セキュリティ ニュース日報</title>
<meta name="description" content="AI×セキュリティ週次レポート（{pss}〜{pes}）。{total}件の記事を分析したCISO向けダイジェスト。">
<meta property="og:title" content="AI×セキュリティ 週次レポート {pss}〜{pes}">
<meta property="og:description" content="{exec_sum[:120]}">
<meta property="og:url" content="{site_url}">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary_large_image">
<meta property="og:image" content="https://ayudle.github.io/ai-security-news/og-image.png">
<meta name="twitter:image" content="https://ayudle.github.io/ai-security-news/og-image.png">
<link rel="canonical" href="{site_url}">
<link rel="icon" type="image/png" href="../favicon.png">
<style>
:root{{--bg:#0f0f0e;--text:#e6e4dc;--dim:#6a6860;--border:#2a2a28;--accent:#378ADD;--card:#1a1a18}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);line-height:1.7}}
header{{border-bottom:1px solid var(--border);padding:16px 24px;display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}}
.logo{{font-size:18px;font-weight:700}}
.back{{display:inline-block;padding:8px 16px;margin:16px 24px;color:var(--accent);text-decoration:none;font-size:13px}}
.back:hover{{text-decoration:underline}}
.wp{{max-width:720px;margin:0 auto;padding:16px 24px 60px}}
.wp-head{{border-bottom:1px solid var(--border);padding-bottom:20px;margin-bottom:24px}}
.wp-period{{font-size:12px;color:var(--dim);margin-bottom:6px}}
.wp-title{{font-size:22px;font-weight:700;color:#fff;line-height:1.4}}
.wp-meta{{font-size:11px;color:var(--dim);margin-top:8px}}
.sec{{margin-bottom:32px}}
.sec-title{{font-size:11px;font-weight:700;letter-spacing:.1em;color:var(--dim);text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)}}
.actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:24px}}
.btn{{display:inline-block;padding:10px 16px;border-radius:4px;text-decoration:none;font-size:13px;font-weight:500;cursor:pointer;border:none;font-family:inherit;background:var(--card);color:var(--text);border:1px solid var(--border)}}
.btn:hover{{border-color:var(--accent)}}
footer{{text-align:center;font-size:10px;color:var(--dim);padding:20px;border-top:1px solid var(--border);margin-top:16px}}
</style>
</head>
<body>
<header>
  <a href="/ai-security-news/" style="text-decoration:none;color:inherit">
    <div class="logo">AI×セキュリティ ニュース日報</div>
  </a>
</header>

<a href="/ai-security-news/#weekly" class="back">← 週次レポート一覧に戻る</a>

<div class="wp">
  <div class="wp-head">
    <div class="wp-period">週次レポート</div>
    <h1 class="wp-title">AI×セキュリティ 週次ダイジェスト</h1>
    <div class="wp-meta">{pss}〜{pes}（{total}件の記事を分析）</div>
  </div>

  <section class="sec">
    <h3 class="sec-title">エグゼクティブサマリー</h3>
    <div style="background:#14243a;border-left:3px solid #378ADD;padding:14px 18px;border-radius:4px;font-size:14px;line-height:1.85;color:#e6e4dc">{exec_sum}</div>
  </section>

  <section class="sec">
    <h3 class="sec-title">今週の重要トピック TOP3</h3>
    {topics_html}
  </section>

  <section class="sec">
    <h3 class="sec-title">6階層別 今週のトレンド</h3>
    {layers_html}
  </section>

  <section class="sec">
    <h3 class="sec-title">キーワード変動（先週比）</h3>
    {kw_html}
  </section>

  <section class="sec">
    <h3 class="sec-title">来週の注目ポイント</h3>
    <div style="background:#0d1b2e;border-left:3px solid #378ADD55;padding:14px 18px;border-radius:4px;font-size:14px;line-height:1.85;color:#c0beb6">{next_week}</div>
  </section>

  <div class="actions">
    <a href="{twitter_url}" target="_blank" rel="noopener" class="btn">Xでシェア</a>
    <button onclick="navigator.clipboard.writeText('{site_url}').then(function(){{alert('URLをコピーしました')}})" class="btn">📋 URLをコピー</button>
  </div>
</div>

<footer>
  各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。<br>
  日本語要約・タグ・示唆はLLMにより自動生成されており、誤りや不正確な情報を含む可能性があります。重要な判断には必ず元記事をご確認ください。<br>
  <p style="margin-top:4px">Powered by Gemini 2.5 Flash + GitHub Actions（完全無料）</p>
  <p style="margin-top:8px"><a href="https://x.com/ayudle_aisec" target="_blank" rel="noopener" style="color:var(--dim);text-decoration:none;font-size:10px">X: @ayudle_aisec</a></p>
</footer>

</body>
</html>"""


def main():
    if not os.path.exists(DATA_PATH):
        print(f"[ERROR] {DATA_PATH} なし"); return
    with open(DATA_PATH,"r",encoding="utf-8") as f:
        data = json.load(f)
    weekly_list = load_weekly_list()
    os.makedirs("docs", exist_ok=True)
    with open(OUT_PATH,"w",encoding="utf-8") as f:
        f.write(build_html(data, weekly_list))
    print(f"生成完了: {OUT_PATH} ({len(data.get('articles',[]))}件)")
    os.makedirs("docs/archive", exist_ok=True)
    for day in data.get("history",[]):
        d = day.get("date","")
        arc_html = build_archive_page(day, d)
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

    # 週次レポートHTML生成
    os.makedirs("docs/weekly", exist_ok=True)
    for w in weekly_list:
        wdate = w["date"]
        wjson = f"docs/weekly/{wdate}.json"
        whtml = f"docs/weekly/{wdate}.html"
        if not os.path.exists(wjson):
            continue
        with open(wjson, "r", encoding="utf-8") as f:
            wd = json.load(f)
        with open(whtml, "w", encoding="utf-8") as f:
            f.write(build_weekly_html(wd))
    print(f'週次レポート: {len(weekly_list)}件')

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
    # 週次レポート
    for w in weekly_list:
        wpe = w.get("period", {}).get("end", "")
        if wpe:
            sitemap_urls.append({
                'loc': f'{site_url}/weekly/{w["date"]}.html',
                'priority': '0.7',
                'changefreq': 'monthly',
                'lastmod': wpe,
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
