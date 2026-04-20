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
  <h2 class="ct"><a href="{a.get('url','#')}" target="_blank" rel="noopener">{a.get('title_ja') or a.get('title','')}</a></h2>
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
<meta name="description" content="サイバーセキュリティ×AI分野の最新ニュースを毎日自動収集・日本語要約。示唆・学び・トレンド分析付き。">
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
  <div class="tab on"  onclick="switchTab('today',this)">本日のニュース</div>
  <div class="tab"     onclick="switchTab('popular',this)">人気記事</div>
  <div class="tab"     onclick="switchTab('archive',this)">アーカイブ</div>
  <div class="tab"     onclick="switchTab('trend',this)">トレンド分析</div>
  <a href="about.html" class="tab" style="text-decoration:none;display:block">About</a>
</div>

<div class="pane on" id="pane-today">
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

<footer style="text-align:center;font-size:10px;color:var(--dim);padding:20px;border-top:1px solid var(--border);margin-top:16px">
  <p>各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。</p>
  <p style="margin-top:4px">Powered by Gemini 2.0 Flash Lite + GitHub Actions（完全無料）</p>
</footer>

<script>
const ANA = {ana_json};
const TAX = {tax_json};
const IMP_COLORS = {{"高":"#E24B4A","中":"#BA7517","低":"#639922"}};
const MAIN_COLORS = {{"attack":"#E24B4A","vuln":"#BA7517","ai_sec":"#378ADD","ai_risk":"#7F77DD","policy":"#1D9E75","incident":"#D85A30","biz_tech":"#639922"}};

function switchTab(id, el) {{
  document.querySelectorAll('.pane').forEach(p => p.classList.remove('on'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
  document.getElementById('pane-' + id).classList.add('on');
  el.classList.add('on');
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

if __name__ == "__main__":
    main()
