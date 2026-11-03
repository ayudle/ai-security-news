"""
build_site.py v3
タブUI・トレンドダッシュボード（大項目×中項目スパイク分析）付きHTML生成
"""

import json, os, re, glob
from html import escape as html_escape
from urllib.parse import quote as _url_quote
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from attack_watch import render as render_attack_watch
from engineering_watch import render as render_engineering_watch
from engineering import engineering_topics

JST       = timezone(timedelta(hours=9))
DATA_PATH = "docs/data/latest.json"
OUT_PATH  = "docs/index.html"

GA_ID = "G-KV7Q7SQKZX"

def ga_snippet():
    return f"""<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){{dataLayer.push(arguments);}}
gtag('js', new Date());
gtag('config', '{GA_ID}');
</script>"""

IMP_COLOR = {"高": "#E24B4A", "中": "#BA7517", "低": "#639922"}

_NOISE_KW = {
    "inaturalist", "simon willison", "photo", "photography",
    "disneyland", "personal blog", "bird", "birds", "cli tool",
}

def _is_noise_kw(kw):
    kl = kw.strip().lower()
    return kl in _NOISE_KW or any(n in kl for n in _NOISE_KW)

_SAFE_URL_SCHEME = re.compile(r'^https?://', re.IGNORECASE)
_SAFE_ID_RE      = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

def _safe_url(url: str) -> str:
    """RSS由来URLを http/https のみ許可する。それ以外は # に置き換える。"""
    u = (url or "").strip().replace("\n", "").replace("\r", "").replace("\t", "")
    if not u or u == "#":
        return "#"
    return html_escape(u, quote=True) if _SAFE_URL_SCHEME.match(u) else "#"

def business_details(article, compact=False):
    from business import normalize_metadata
    meta = normalize_metadata(article.get("business"))
    if compact:
        return ('<div class="business-brief">' + ' · '.join(html_escape(v) for v in [
            '日本との関連: ' + meta['japan_relevance'],
            '悪用: ' + meta['exploitation'], '対応: ' + meta['urgency'],
        ]) + '</div>') if article.get('business') else ''
    fields = [("日本企業との関連", meta["japan_relevance"]), ("悪用状況", meta["exploitation"]),
              ("対応緊急度", meta["urgency"]), ("対象製品・技術", '、'.join(meta["products"])),
              ("ライフサイクル", '、'.join(meta["lifecycle"])), ("診断種別", '、'.join(meta["assessments"])),
              ("根拠（収集時の抜粋）", meta["evidence"])]
    note = '' if article.get('business') else '<p class="metadata-note">過去記事のため追加情報は未評価です。</p>'
    return '<section class="ap-section"><h2 class="ap-sec-title">業務で確認する情報</h2>' + note + '<dl class="business-details">' + ''.join('<div><dt>' + html_escape(k) + '</dt><dd>' + html_escape(v) + '</dd></div>' for k, v in fields) + '</dl></section>'

def safe_article_id(raw_id: str) -> str:
    """記事IDを検証し、安全なもののみ返す。不正な場合は空文字。"""
    s = (raw_id or "").strip()
    return s if _SAFE_ID_RE.match(s) else ""

# ── コラム機能 ─────────────────────────────────────────────

def parse_frontmatter(text):
    """Markdownのfrontmatterをパースして (meta_dict, body_text) を返す"""
    meta = {}
    body = text
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            fm = text[3:end].strip()
            body = text[end + 4:].strip()
            last_list_key = None
            for line in fm.split('\n'):
                line = line.rstrip()
                if line.startswith('  - ') or line.startswith('- '):
                    if last_list_key:
                        meta[last_list_key].append(line.lstrip('- ').strip())
                elif ':' in line:
                    k, _, v = line.partition(':')
                    k = k.strip(); v = v.strip().strip('"').strip("'")
                    if v == '':
                        meta[k] = []; last_list_key = k
                    else:
                        meta[k] = v; last_list_key = None
    return meta, body


def _md_inline(text):
    """インライン要素（太字・イタリック）をHTML化する（エスケープ済みテキストに適用）"""
    t = html_escape(text)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'\*([^*]+?)\*', r'<em>\1</em>', t)
    return t


def md_to_html(text):
    """最小限のMarkdown→HTML変換（XSS安全）"""
    blocks = re.split(r'\n{2,}', text.strip())
    out = []
    for block in blocks:
        lines = block.strip().split('\n')
        first = lines[0].rstrip()
        if first.startswith('### '):
            out.append(f'<h3>{_md_inline(first[4:])}</h3>')
        elif first.startswith('## '):
            out.append(f'<h2>{_md_inline(first[3:])}</h2>')
        elif first.startswith('# '):
            out.append(f'<h1>{_md_inline(first[2:])}</h1>')
        elif all(l.rstrip().startswith(('- ', '* ')) or not l.rstrip() for l in lines):
            items = ''.join(
                f'<li>{_md_inline(l.rstrip()[2:])}</li>'
                for l in lines if l.rstrip().startswith(('- ', '* '))
            )
            out.append(f'<ul>{items}</ul>')
        else:
            content = _md_inline(''.join(l.rstrip() for l in lines))
            out.append(f'<p>{content}</p>')
    return '\n'.join(out)


def load_columns():
    """columns/*.md を読み込んでリストを返す（日付降順）"""
    cols = []
    if not os.path.isdir('columns'):
        return cols
    for path in sorted(glob.glob('columns/*.md'), reverse=True):
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        meta, body = parse_frontmatter(raw)
        if not meta.get('slug'):
            continue
        cols.append({
            'title':       meta.get('title', ''),
            'date':        meta.get('date', ''),
            'slug':        meta.get('slug', ''),
            'description': meta.get('description', ''),
            'tags':        meta.get('tags', []),
            'body_md':     body,
        })
    return cols


def build_column_page(col, all_articles=None, all_columns=None):
    """個別コラムページのHTMLを生成する"""
    title = col.get('title', '')
    date  = col.get('date', '')
    slug  = col.get('slug', '')
    desc  = col.get('description', '')
    tags  = col.get('tags', [])
    body  = md_to_html(col.get('body_md', ''))
    tags_html = ''.join(
        f'<span class="col-tag-ap">{html_escape(t)}</span>' for t in tags
    )
    human_badge = '<span class="human-badge">著者執筆</span>'

    # このコラムのCDC contextセットに一致する記事を最大5件抽出
    col_cdcs = col_cdc_set(tags)
    related_news_html = ""
    if col_cdcs and all_articles:
        matched = [
            a for a in all_articles
            if set(a.get("cdc_context", [])) & col_cdcs
            and int(a.get("cdc_relevance", 0) or 0) >= 1
        ]
        matched.sort(key=lambda x: x.get("published", ""), reverse=True)
        matched = matched[:5]
        if matched:
            items = []
            for a in matched:
                a_id  = a.get("id", "")
                a_pub = a.get("published", "")[:10]
                a_title = a.get("title_ja") or a.get("title", "")
                a_src = a.get("source_name", "")
                a_imp = a.get("importance", "中")
                a_cdcs = [c for c in a.get("cdc_context", []) if c in col_cdcs]
                badge_html = "".join(f'<span style="font-size:9px;padding:1px 5px;border-radius:99px;background:#f2f6fa;border:1px solid #d9dfe5;color:#245d86">{c}</span>' for c in a_cdcs[:2])
                items.append(
                    f'<a href="../article/{a_id}.html" style="display:block;padding:10px 12px;background:#f6f7f8;border-radius:6px;text-decoration:none;color:inherit;margin-bottom:6px">'
                    f'<div style="font-size:10px;color:#566473;margin-bottom:4px;display:flex;flex-wrap:wrap;gap:6px;align-items:center">'
                    f'<span>{a_pub}</span><span>{html_escape(a_src)}</span>{badge_html}</div>'
                    f'<div style="font-size:13px;color:#202830;line-height:1.5">{html_escape(a_title)}</div>'
                    f'</a>'
                )
            related_news_html = (
                '<div style="margin-top:40px;padding-top:20px;border-top:1px solid var(--border)">'
                '<div style="font-size:11px;font-weight:700;letter-spacing:.1em;color:#245d86;text-transform:uppercase;margin-bottom:14px">このテーマの最近のニュース</div>'
                + "".join(items) +
                '</div>'
            )
    # 関連コラム（自分以外の最大3本）
    related_cols_html = ""
    if all_columns:
        others = [c for c in all_columns if c.get('slug','') != slug][:3]
        if others:
            items_c = []
            for c in others:
                c_slug  = html_escape(c.get('slug', ''))
                c_title = html_escape(c.get('title', ''))
                c_desc  = html_escape(c.get('description', ''))
                c_date  = html_escape(c.get('date', ''))
                items_c.append(
                    f'<a href="../columns/{c_slug}.html" style="display:block;padding:10px 12px;background:#f6f7f8;border-radius:6px;text-decoration:none;color:inherit;margin-bottom:6px">'
                    f'<div style="font-size:10px;color:#566473;margin-bottom:4px">{c_date}</div>'
                    f'<div style="font-size:13px;color:#202830;font-weight:600;line-height:1.4;margin-bottom:4px">{c_title}</div>'
                    f'<div style="font-size:12px;color:#9ca3af;line-height:1.5">{c_desc}</div>'
                    f'</a>'
                )
            related_cols_html = (
                '<div style="margin-top:40px;padding-top:20px;border-top:1px solid var(--border)">'
                '<div style="font-size:11px;font-weight:700;letter-spacing:.1em;color:#245d86;text-transform:uppercase;margin-bottom:14px">関連する設計ノート</div>'
                + "".join(items_c) +
                '</div>'
            )
    page_url  = f'https://ayudle.github.io/ai-security-news/columns/{slug}.html'
    site_url  = page_url  # 後方互換のため両名を維持
    ogp_image = 'https://ayudle.github.io/ai-security-news/og-image.png'
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": desc,
        "author": {"@type": "Organization", "name": "Cyber Defense Notes"},
        "publisher": {"@type": "Organization", "name": "Cyber Defense Notes",
                      "url": "https://ayudle.github.io/ai-security-news/"},
        "datePublished": date,
        "dateModified":  date,
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
        "url": page_url,
        "image": ogp_image,
    }, ensure_ascii=False).replace('</', '<\\/')
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html_escape(title)} | Cyber Defense Notes</title>
<meta name="description" content="{html_escape(desc)}">
<meta property="og:title" content="{html_escape(title)}">
<meta property="og:description" content="{html_escape(desc)}">
<meta property="og:url" content="{page_url}">
<meta property="og:type" content="article">
<meta property="og:image" content="{ogp_image}">
<link rel="canonical" href="{page_url}">
<link rel="icon" type="image/png" href="../favicon.png">
<script type="application/ld+json">{jsonld}</script>
<style>
:root{{--bg:#ffffff;--text:#202830;--dim:#566473;--border:#d9dfe5;--accent:#245d86;--card:#f6f7f8}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);line-height:1.7}}
header{{border-bottom:1px solid var(--border);padding:16px 24px;display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}}
.logo{{font-size:18px;font-weight:700}}
.back{{display:inline-block;padding:8px 16px;margin:16px 24px;color:var(--accent);text-decoration:none;font-size:13px}}
.back:hover{{text-decoration:underline}}
nav.col-nav{{padding:8px 24px 10px;border-bottom:1px solid #d9dfe5;display:flex;flex-wrap:wrap;gap:16px;font-size:12px}}
nav.col-nav a{{color:var(--accent);text-decoration:none}}
.col-ap{{max-width:720px;margin:0 auto;padding:16px 24px 60px}}
.col-head{{border-bottom:1px solid var(--border);padding-bottom:20px;margin-bottom:28px}}
.col-meta{{font-size:11px;color:var(--dim);margin-bottom:8px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}}
.col-tags-ap{{display:flex;flex-wrap:wrap;gap:4px}}
.col-tag-ap{{font-size:12px;padding:2px 7px;border-radius:2px;background:#f2f4f6;border:1px solid #d9dfe5;color:#35414d}}
h1.col-title{{font-size:24px;font-weight:700;color:#202830;line-height:1.4;margin-bottom:10px}}
.col-desc{{font-size:14px;color:var(--dim);line-height:1.65;margin-top:8px}}
.col-body{{font-size:15px;line-height:1.9;color:var(--text)}}
.col-body h1,.col-body h2{{font-size:18px;font-weight:700;color:#202830;margin:2em 0 .6em;padding-bottom:6px;border-bottom:1px solid var(--border)}}
.col-body h3{{font-size:15px;font-weight:700;color:#475361;margin:1.6em 0 .5em}}
.col-body p{{margin-bottom:1.2em}}
.col-body ul{{margin:0 0 1.2em 1.4em}}
.col-body li{{margin-bottom:.4em}}
.col-body strong{{color:#202830;font-weight:700}}
.col-footer{{margin-top:40px;padding-top:20px;border-top:1px solid var(--border);display:flex;flex-wrap:wrap;gap:12px}}
footer{{text-align:center;font-size:10px;color:var(--dim);padding:20px;border-top:1px solid var(--border);margin-top:16px}}
</style>
{ga_snippet()}
</head>
<body>
<header>
  <a href="/ai-security-news/" style="text-decoration:none;color:inherit">
    <div class="logo">Cyber Defense Notes</div>
  </a>
</header>

<a href="/ai-security-news/#columns" class="back">← コラム一覧に戻る</a>

<nav class="col-nav">
  <a href="/ai-security-news/#today">本日のニュース</a>
  <a href="/ai-security-news/#trend">攻撃・インシデント動向</a>
  <a href="/ai-security-news/#weekly">週次レポート</a>
  <a href="/ai-security-news/#columns">コラム一覧</a>
</nav>

<article class="col-ap">
  <div class="col-head">
    <div class="col-meta">
      <span>{html_escape(date)}</span>
      {human_badge}
    </div>
    <h1 class="col-title">{html_escape(title)}</h1>
    <p class="col-desc">{html_escape(desc)}</p>
    <div class="col-related-themes"><strong>関連テーマ</strong><div class="col-tags-ap">{tags_html}</div></div>
  </div>

  <div class="col-body">
{body}
  </div>

  {related_news_html}

  {related_cols_html}

  <div class="col-footer">
    <a href="/ai-security-news/#columns" style="font-size:13px;color:var(--accent);text-decoration:none">← コラム一覧に戻る</a>
    <a href="/ai-security-news/#today" style="font-size:13px;color:var(--accent);text-decoration:none">← 本日のニュースに戻る</a>
  </div>
</article>

<footer>
  本コラムは著者が執筆した考察であり、LLMによる自動生成ではありません。<br>
</footer>

</body>
</html>"""


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
    return f'<span class="imp" style="color:{c};border-color:{c}55">重要度 {html_escape(imp)}</span>'

def tag_main_badge(main_id, main_label):
    c = MAIN_COLOR.get(main_id, "#5F5E5A")
    return f'<span class="tag-main" style="background:{c}20;color:{c};border-color:{c}44">{html_escape(main_label)}</span>'

def tag_sub_badge(sub):
    return f'<span class="tag-sub">{html_escape(sub)}</span>'

def tag_layer_badge(layer):
    return f'<span class="tag-layer">{html_escape(layer)}</span>'

def tag_kw_badge(kw):
    return f'<span class="tag-kw">{html_escape(kw)}</span>'

# コラムタグ → CDC context の対応表
COL_TAG_TO_CDC = {
    "Identity":    ["Identity/ITDR"],
    "Exposure":    ["Exposure管理"],
    "MSSP":        ["MDR/MSSP設計", "サービス企画", "顧客課題"],
    "CDC":         ["MDR/MSSP設計", "SOC運用変化"],
    "AI Security": ["Security for AI", "AI for Security"],
}

def col_cdc_set(col_tags):
    """コラムのタグリストをCDC context語彙のセットに展開する"""
    result = set()
    for tag in col_tags:
        for cdc in COL_TAG_TO_CDC.get(tag, []):
            result.add(cdc)
    return result

def article_card(a, rank=None):
    rank_html    = f'<span class="rank">#{rank}</span>' if rank else ""
    pub          = a.get("published","")[:10]
    insight      = a.get("insight","")
    main_id      = a.get("tag_main_id","attack")
    main_label   = a.get("tag_main_label","攻撃・脅威")
    subs_html    = "".join(tag_sub_badge(s) for s in a.get("tag_subs",[]))
    layers_html  = "".join(tag_layer_badge(l) for l in a.get("affected_layers",[]))
    kws_html     = "".join(tag_kw_badge(k) for k in a.get("related_keywords",[])[:5])
    aid          = safe_article_id(a.get("id", ""))
    aid_esc      = html_escape(aid)
    # 示唆スニペット（タイトル直下1〜2行）
    insight_snippet = ""
    if insight:
        itxt = (insight[:120] + "…") if len(insight) > 120 else insight
        insight_snippet = f'<div class="insight-snippet">{html_escape(itxt)}</div>'
    # CDC観点バッジ（cdc_context が存在する記事のみ・最大3個）
    cdc_html = ""
    cdc_contexts = a.get("cdc_context", [])[:3]
    if cdc_contexts:
        badges = "".join(f'<span class="cdc-badge">{html_escape(ctx)}</span>' for ctx in cdc_contexts)
        cdc_html = f'<div class="cdc-badges"><span class="cdc-lbl">CDC観点</span>{badges}</div>'
    # レイヤーは常時表示、related_keywordsは折りたたみ
    layers_row = f'<div class="tags tags-meta">{layers_html}</div>' if layers_html else ""
    kw_section = ""
    if kws_html and aid_esc:
        kid = f"kw-{aid_esc}"
        kw_section = (f'<div class="kw-fold">'
                      f'<div class="tags tags-meta" id="{kid}" style="display:none">{kws_html}</div>'
                      f'<button class="kw-btn" onclick="toggleKw(\'{kid}\',this);event.stopPropagation()">タグを表示</button>'
                      f'</div>')

    return f"""<article class="card" data-id="{aid_esc}" data-main="{html_escape(main_id)}" onclick="navigateCard('{aid_esc}')">
  <div class="cm">
    {rank_html}
    <span class="tier">{tier_label(a.get('source_tier','B'))}</span>
    <span class="src">{html_escape(a.get('source_name',''))}</span>
    <span class="dt">{pub}</span>
    {imp_badge(a.get('importance','中'))}
  </div>
  <h2 class="ct"><a href="/ai-security-news/article/{aid_esc}.html" onclick="event.stopPropagation()">{html_escape(a.get('title_ja') or a.get('title',''))}</a></h2>
  <p class="article-summary">{html_escape((a.get('summary_ja') or '')[:200])}</p>
  {business_details(a, compact=True)}
  <div class="tags">
    {tag_main_badge(main_id, main_label)}
    {subs_html}
  </div>
  <div class="cf">出典: <a href="{_safe_url(a.get('url','#'))}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">{html_escape(a.get('source_name',''))}</a>
  <em class="orig">"{html_escape(a.get('title',''))}"</em></div>
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
                    if kw_norm and not _is_noise_kw(kw_norm):
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


def build_html(data, weekly_list=None, columns=None):
    weekly_list = weekly_list or []
    articles  = data.get("articles", [])
    today     = data.get("today", "")
    updated   = data.get("updated","")[:16].replace("T"," ")
    history   = data.get("history", [])
    taxonomy  = data.get("taxonomy", {})

    # アーカイブ
    archive_rows = ""
    for day in history[:30]:
        d = day.get("date","")
        n = len(day.get("articles",[]))
        archive_rows += f'<div class="arc-row"><a href="archive/{d}.html" class="arc-link">{d}</a><span class="arc-n">{n}件</span></div>\n'

    # 記事検索用データ（history全件フラット化・id重複排除・日付付与）
    _srch_seen = set()
    search_articles = []
    for _day in history:
        _d = _day.get("date", "")
        for _a in _day.get("articles", []):
            _aid = _a.get("id") or ""
            if not _aid or _aid in _srch_seen:
                continue
            _srch_seen.add(_aid)
            search_articles.append({
                "id":            _aid,
                "date":          _d,
                "title_ja":      _a.get("title_ja") or _a.get("title", ""),
                "summary_ja":    (_a.get("summary_ja") or "")[:200],
                "insight":       (_a.get("insight") or "")[:150],
                "tag_main_id":   _a.get("tag_main_id", ""),
                "tag_main_label":_a.get("tag_main_label", ""),
                "tag_subs":      _a.get("tag_subs", [])[:4],
                "cdc_context":   _a.get("cdc_context", [])[:4],
                "cdc_relevance": _a.get("cdc_relevance", 0),
                "related_keywords": _a.get("related_keywords", [])[:6],
                "engineering_topics": _a.get("engineering_topics") or engineering_topics(_a.get("title", ""), _a.get("summary", "")),
                "source_name":   _a.get("source_name", ""),
            })
    search_json = json.dumps(search_articles, ensure_ascii=False).replace('</', '<\\/')

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
            f'style="display:inline-block;font-size:11px;color:#245d86;'
            f'text-decoration:none;margin-top:8px">'
            f'&#x1F4CA; 先週のレポート（{wps_s}〜{wpe_s}）を読む →</a>'
        )

    # 関連コラムリンク（#todayペイン内・示唆ボックス直下）
    related_column_link = ""
    if columns:
        latest_col = columns[0]
        ctitle = latest_col.get('title', '')
        cslug  = latest_col.get('slug', '')
        ctitle_short = (ctitle[:38] + "…") if len(ctitle) > 38 else ctitle
        related_column_link = (
            f'<a href="columns/{cslug}.html" '
            f'style="display:inline-block;font-size:11px;color:#6add8a;'
            f'text-decoration:none;margin-top:8px">'
            f'&#x270D; 関連コラム：{html_escape(ctitle_short)} →</a>'
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
            f'<div style="background:#f2f6fa;border-left:3px solid #245d86;'
            f'padding:14px 18px;border-radius:4px;margin-bottom:18px">'
            f'<div style="font-size:11px;font-weight:700;color:#245d86;'
            f'letter-spacing:.05em;margin-bottom:6px">最新レポート（{wps_s}〜{wpe_s}）</div>'
            f'<div style="font-size:13px;line-height:1.8;color:#202830;margin-bottom:10px">'
            f'{html_escape(w_summary_short)}</div>'
            f'<a href="weekly/{wpe}.html" style="font-size:12px;color:#245d86">'
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

    # コラムペイン HTML
    columns = columns or []
    if columns:
        col_cards_html = ""
        for col in columns:
            ctitle = col.get('title','')
            cdate  = col.get('date','')
            cslug  = col.get('slug','')
            cdesc  = col.get('description','')
            ctags  = col.get('tags',[])
            ctags_html = "".join(f'<span class="col-tag">{html_escape(t)}</span>' for t in ctags[:3])
            col_cards_html += (
                f'<article class="col-card">'
                f'<div class="col-card-meta">{html_escape(cdate)}</div>'
                f'<h2 class="col-card-title"><a href="columns/{cslug}.html">{html_escape(ctitle)}</a></h2>'
                f'<p class="col-card-desc">{html_escape(cdesc)}</p>'
                f'<div class="col-card-tags">{ctags_html}</div>'
                f'</article>\n'
            )
        columns_pane_html = (
            '<div class="pane" id="pane-columns">\n'
            '  <p class="plabel">コラム</p>\n'
            '  <p class="col-intro">ニュースの観察から生まれた考察を記録しています。</p>\n'
            + col_cards_html +
            '</div>'
        )
    else:
        columns_pane_html = (
            '<div class="pane" id="pane-columns">\n'
            '  <p class="plabel">コラム</p>\n'
            '  <p class="empty">コラムはまだありません。</p>\n'
            '</div>'
        )

    # 分析データ
    analytics   = build_analytics(history, taxonomy)
    watch_html = render_attack_watch(history, safe_article_id)
    engineering_html = render_engineering_watch(history, safe_article_id)
    ana_json    = json.dumps(analytics, ensure_ascii=False).replace('</', '<\\/')
    tax_json    = json.dumps(taxonomy, ensure_ascii=False).replace('</', '<\\/')

    today_html   = "\n".join(article_card(a) for a in articles) if articles \
                   else '<p class="empty">本日は該当記事がありませんでした。</p>'
    vuln_count = sum(1 for a in articles if a.get("tag_main_id") == "vuln")
    ops_count = sum(1 for a in articles if any(
        c in {"SOC運用変化", "Identity/ITDR", "Exposure管理", "MDR/MSSP設計"}
        for c in a.get("cdc_context", [])
    ))

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Cyber Defense Notes | {today}</title>
<meta name="description" content="脆弱性、脅威インテリジェンス、SOC/CDC、MDR/MSSP、Identity/ITDR、Exposure管理、AI×セキュリティの最新動向を実務者視点で整理する設計ノート。">
<meta name="google-site-verification" content="m7S3bMP_P0V-BinV3MTpaO9qkk31af-RRKxsQ4_BoQg" />
<meta property="og:title" content="Cyber Defense Notes">
<meta property="og:description" content="脆弱性診断・管理とAIエージェントの情報ノート — SOC/CDC、MDR/MSSP、Security for AI / AI for Securityの論点を整理するナレッジ基盤。">
<meta property="og:url" content="https://ayudle.github.io/ai-security-news/">
<meta property="og:type" content="website">
<meta property="og:image" content="https://ayudle.github.io/ai-security-news/og-image.png">
<link rel="canonical" href="https://ayudle.github.io/ai-security-news/">
<link rel="icon" type="image/png" href="favicon.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "Cyber Defense Notes",
  "url": "https://ayudle.github.io/ai-security-news/",
  "description": "脆弱性診断・管理とAIエージェントの情報ノート — SOC/CDC、MDR/MSSP、Security for AI / AI for Securityの論点を整理するナレッジ基盤",
  "publisher": {{
    "@type": "Organization",
    "name": "Cyber Defense Notes",
    "url": "https://ayudle.github.io/ai-security-news/"
  }}
}}
</script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#ffffff;--card:#f6f7f8;--card2:#eef1f4;--text:#202830;--muted:#475361;--dim:#566473;--border:#d9dfe5;--accent:#245d86;--r:12px}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP","Hiragino Sans",sans-serif;background:var(--bg);color:var(--text);line-height:1.8;font-size:15px}}
a{{color:inherit;text-decoration:none}}
.hdr{{border-bottom:1px solid var(--border);padding:16px max(24px,calc((100vw - 980px)/2));display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#ffffff}}
.hdr-home{{display:inline-flex;align-items:center;text-decoration:none;color:inherit}}
.hdr-home:hover .ht{{color:var(--accent)}}
.ht{{font-size:18px;font-weight:750;color:#202830;margin:0;letter-spacing:-.01em}}
.hs{{font-size:12px;color:var(--muted)}}
.hu{{font-size:11px;color:var(--dim);margin-left:auto}}
.tab-bar{{display:flex;border-bottom:1px solid var(--border);padding:0 max(24px,calc((100vw - 980px)/2));overflow-x:auto;background:#ffffff;-webkit-mask-image:linear-gradient(to right,black 0,black calc(100% - 32px),transparent 100%);mask-image:linear-gradient(to right,black 0,black calc(100% - 32px),transparent 100%)}}
@media(min-width:768px){{.tab-bar{{-webkit-mask-image:none;mask-image:none}}}}
.tab{{font-size:13px;padding:12px 16px;cursor:pointer;color:var(--dim);border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;transition:color .15s,border-color .15s}}
.tab.on,.tab[aria-current="page"]{{color:var(--text);border-bottom-color:var(--accent);font-weight:600}}
.tab:hover{{color:var(--text);border-bottom-color:var(--border)}}
.tab:focus-visible{{outline:2px solid var(--accent);outline-offset:-2px}}
.pane{{display:none;padding:24px;max-width:980px;margin:0 auto}}
.pane.on{{display:block}}
.plabel{{font-size:12px;font-weight:700;letter-spacing:.05em;color:var(--muted);margin-bottom:14px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;margin-bottom:14px;cursor:pointer;transition:border-color .15s,transform .15s}}
.card:hover{{border-color:#3a3a38}}
.cm{{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-bottom:8px}}
.tier{{background:#eef1f4;color:#245d86;font-size:10px;padding:2px 7px;border-radius:99px;font-weight:600}}
.src,.dt{{font-size:10px;color:var(--dim)}}
.dt{{margin-left:auto}}
.imp{{font-size:10px;padding:2px 6px;border-radius:99px;border:1px solid}}
.rank{{font-size:13px;font-weight:700;color:var(--accent);min-width:22px}}
.cdc-badges{{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin:4px 0}}
.cdc-lbl{{font-size:9px;font-weight:700;color:#245d86;letter-spacing:.06em;text-transform:uppercase;margin-right:2px}}
.cdc-badge{{font-size:9px;padding:1px 6px;border-radius:99px;background:#f2f6fa;border:1px solid #d9dfe5;color:#245d86}}
.ct{{font-size:17px;font-weight:700;margin-bottom:8px;line-height:1.55;letter-spacing:.005em}}
.ct a:hover{{color:var(--accent)}}
.cs{{font-size:14px;color:var(--muted);line-height:1.85;margin-bottom:10px}}
.insight{{background:#f2f6fa;border-left:3px solid var(--accent);border-radius:0 8px 8px 0;padding:10px 12px;margin-bottom:10px;font-size:13px;color:#245d86;line-height:1.75}}
.ins-lbl{{display:block;font-size:9px;font-weight:700;color:var(--accent);letter-spacing:.06em;margin-bottom:2px;text-transform:uppercase}}
.tags{{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}}
.tag-main{{font-size:10px;padding:2px 8px;border-radius:99px;border:1px solid;font-weight:600}}
.tag-sub{{font-size:10px;padding:2px 7px;border-radius:99px;background:#f2f4f6;border:1px solid #d9dfe5;color:var(--muted)}}
.tags-meta{{margin-top:3px}}
.tag-layer{{font-size:9px;padding:1px 6px;border-radius:99px;background:#eef1f4;border:1px solid #d9dfe5;color:#245d86}}
.tag-kw{{font-size:9px;padding:1px 5px;border-radius:99px;background:#f2f4f6;border:1px solid #d9dfe5;color:#566473}}
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
.bl{{width:130px;font-size:11px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex-shrink:0;transition:color .1s}}
.bt{{flex:1;height:5px;background:#d9dfe5;border-radius:3px;overflow:hidden}}
.bf{{height:100%;border-radius:3px;transition:width .4s}}
.bn{{width:18px;text-align:right;font-size:10px;color:var(--dim)}}
.spike-list{{display:flex;flex-direction:column;gap:6px}}
.spike-item{{display:flex;align-items:center;justify-content:space-between;padding:6px 8px;background:#f2f4f6;border-radius:6px}}
.spike-name{{font-size:12px;color:var(--text)}}
.spike-badge{{font-size:10px;background:#E24B4A22;color:#E24B4A;border:1px solid #E24B4A44;padding:2px 7px;border-radius:99px}}
.sub-filter{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}}
.sf-btn{{font-size:11px;padding:4px 10px;border-radius:99px;border:1px solid var(--border);background:transparent;color:var(--dim);cursor:pointer;transition:all .15s}}
.sf-btn.on{{border-color:var(--accent);color:var(--accent);background:#0d1e36}}
.imp-note{{font-size:11px;color:var(--dim);background:var(--card);border-radius:8px;padding:10px 12px;line-height:1.6;margin-bottom:12px;border-left:3px solid #BA751755}}
.kw-cloud{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:4px 0}}
.kw-bubble{{border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:default;text-align:center;padding:6px;line-height:1.25;word-break:break-word;overflow:hidden;transition:opacity .15s;flex-shrink:0}}
.kw-bubble:hover{{opacity:.75}}
.kw-bubble-word{{color:#202830;font-weight:600}}
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
.insight-snippet{{font-size:12px;color:#9ca3af;line-height:1.55;margin-bottom:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.kw-fold{{margin-top:2px}}
.kw-btn{{font-size:11px;background:transparent;border:1px solid var(--border);color:var(--muted);border-radius:99px;padding:4px 10px;cursor:pointer;margin-top:4px;font-family:inherit;transition:color .15s,border-color .15s;min-height:26px}}
.kw-btn:hover{{color:var(--text);border-color:var(--muted)}}
.kw-btn[aria-expanded="true"]{{background:var(--card2)}}
.hidden{{display:none}}
.imp-detail{{margin-top:8px}}
.imp-detail-toggle{{cursor:pointer;display:block;font-size:0;color:#245d86;padding:4px 0;user-select:none;outline:none;list-style:none}}
.imp-detail-toggle::before{{content:"▶ 全文を読む";font-size:11px;color:#245d86}}
.imp-detail[open] .imp-detail-toggle::before{{content:"▼ 閉じる";font-size:11px}}
.imp-detail-toggle::-webkit-details-marker{{display:none}}
.imp-detail-toggle::marker{{display:none}}
.col-card{{background:#fff;border:0;border-bottom:1px solid var(--border);border-radius:0;padding:24px 0;margin:0}}
.col-card-meta{{font-size:10px;color:var(--dim);margin-bottom:6px}}
.col-card-title{{font-size:16px;font-weight:700;line-height:1.4;margin-bottom:8px}}
.col-card-title a{{color:var(--text)}}
.col-card-title a:hover{{color:var(--accent)}}
.col-card-desc{{font-size:13px;color:var(--muted);line-height:1.65;margin-bottom:8px}}
.col-card-tags{{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px}}
.col-tag{{font-size:12px;padding:2px 7px;border-radius:2px;background:#f2f4f6;border:1px solid #d9dfe5;color:#35414d}}
.col-intro{{font-size:12px;color:var(--dim);margin-bottom:16px;line-height:1.65}}
.col-read-link{{display:inline-block;font-size:12px;color:var(--accent);padding:4px 0}}
.srch-desc{{font-size:12px;color:var(--dim);line-height:1.65;margin-bottom:14px}}
.srch-input-wrap{{position:relative;margin-bottom:14px}}
.srch-input{{width:100%;background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:10px 14px 10px 36px;font-size:14px;font-family:inherit;outline:none;transition:border-color .15s}}
.srch-input:focus{{border-color:var(--accent)}}
.srch-input-icon{{position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--dim);font-size:14px;pointer-events:none}}
.srch-section-lbl{{font-size:10px;font-weight:700;letter-spacing:.08em;color:var(--dim);text-transform:uppercase;margin-bottom:7px}}
.srch-themes{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}}
.srch-theme-btn{{font-size:12px;padding:5px 12px;border-radius:3px;border:1px solid var(--border);background:#fff;color:var(--muted);cursor:pointer;font-family:inherit;white-space:nowrap}}
.srch-theme-btn:hover{{border-color:var(--accent);color:var(--accent)}}
.srch-theme-btn.on{{background:#245d86;border-color:#245d86;color:#fff;font-weight:600}}
.srch-filters{{display:flex;flex-direction:column;gap:8px;margin-bottom:12px}}
.srch-filter-row{{display:flex;flex-wrap:wrap;align-items:center;gap:6px}}
.srch-filter-lbl{{font-size:10px;font-weight:700;color:var(--dim);letter-spacing:.05em;min-width:60px;flex-shrink:0}}
.srch-chip{{font-size:12px;padding:3px 10px;border-radius:3px;border:1px solid var(--border);background:#fff;color:var(--dim);cursor:pointer;font-family:inherit;white-space:nowrap}}
.srch-chip:hover{{border-color:var(--muted);color:var(--text)}}
.srch-chip.on{{background:#245d86;border-color:#245d86;color:#fff;font-weight:600}}
.srch-meta{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px}}
.srch-count{{font-size:11px;color:var(--dim)}}
.srch-clear-btn{{font-size:11px;padding:4px 12px;border-radius:99px;border:1px solid var(--border);background:transparent;color:var(--dim);cursor:pointer;font-family:inherit;transition:all .15s}}
.srch-clear-btn:hover{{border-color:var(--muted);color:var(--text)}}
.srch-card{{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:12px 14px;margin-bottom:8px;cursor:pointer;transition:border-color .15s;text-decoration:none;display:block}}
.srch-card:hover{{border-color:#3a3a38}}
.srch-card-meta{{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-bottom:6px}}
.srch-card-title{{font-size:13px;font-weight:600;color:var(--text);line-height:1.4;margin-bottom:5px}}
.srch-card-summary{{font-size:11px;color:var(--muted);line-height:1.6;margin-bottom:6px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.srch-card-tags{{display:flex;flex-wrap:wrap;gap:4px}}
.srch-more-btn{{font-size:12px;padding:7px 20px;border-radius:99px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;font-family:inherit;transition:all .15s}}
.srch-more-btn:hover{{border-color:var(--accent);color:var(--accent)}}
.srch-arc-details{{margin-top:28px;border-top:1px solid var(--border);padding-top:16px}}
.srch-arc-summary{{font-size:11px;color:var(--dim);cursor:pointer;list-style:none;display:flex;align-items:center;gap:6px;padding:4px 0;user-select:none}}
.srch-arc-summary::-webkit-details-marker{{display:none}}
.srch-arc-summary::marker{{display:none}}
.srch-arc-summary::before{{content:"▶";font-size:9px}}
details[open] .srch-arc-summary::before{{content:"▼"}}
.srch-empty{{font-size:12px;color:var(--dim);padding:20px 0;text-align:center}}
.about-wrap{{max-width:720px;margin:0 auto;padding:1rem 0 3rem}}
.about-hero{{margin-bottom:2.5rem}}
.about-hero-name{{font-size:28px;font-weight:700;color:#202830;margin-bottom:4px;letter-spacing:-.01em}}
.about-hero-role{{font-size:12px;color:var(--dim);margin-bottom:1.2rem;letter-spacing:.03em}}
.about-hero-lead{{font-size:14px;color:#475361;line-height:1.85;border-left:3px solid var(--accent);padding-left:14px}}
.about-section{{margin-bottom:2.5rem}}
.about-section-lbl{{font-size:11px;font-weight:700;letter-spacing:.1em;color:var(--dim);text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)}}
.about-axes{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:8px}}
@media(max-width:600px){{.about-axes{{grid-template-columns:1fr}}}}
.about-axis{{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:12px 14px}}
.about-axis-label{{font-size:11px;font-weight:700;margin-bottom:6px}}
.about-axis-desc{{font-size:11px;color:var(--dim);line-height:1.6}}
.about-text{{font-size:14px;color:#566473;line-height:1.85}}
.about-layers{{display:flex;flex-direction:column;gap:6px;margin:1rem 0}}
.about-layer{{background:#f6f7f8;border-radius:10px;padding:10px 14px;font-size:13px}}
.about-layer-n{{font-size:11px;font-weight:700;color:var(--accent);margin-right:6px}}
.about-layer-name{{font-weight:500;color:#202830}}
.about-layer-desc{{font-size:12px;color:var(--dim);margin-top:2px}}
.focus-strip{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px}}
.focus-card{{display:block;background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:12px 14px;text-decoration:none}}
.focus-card:hover{{border-color:var(--accent)}}
.focus-card strong{{display:block;font-size:13px;color:var(--text);margin-bottom:2px}}
.focus-card span{{font-size:11px;color:var(--dim);line-height:1.5}}
@media(max-width:680px){{body{{font-size:14px}}.pane{{padding:18px 14px}}.hdr{{padding:14px}}.tab-bar{{padding:0 6px}}.card{{padding:15px}}.ct{{font-size:16px}}.focus-strip{{grid-template-columns:1fr}}}}
</style>
{ga_snippet()}
</head>
<body>
<header class="hdr">
  <a href="./" class="hdr-home" aria-label="ホームに戻る">
    <h1 class="ht">Cyber Defense Notes</h1>
  </a>
  <span class="hs">脆弱性診断・管理とAIエージェントの情報ノート</span>
  <span class="hu">更新: {updated} JST</span>
</header>

<div class="tab-bar">
  <a href="#today"   class="tab">本日のニュース</a>
  <a href="#trend"   class="tab">攻撃・インシデント動向</a>
  <a href="#engineering" class="tab">診断技術・評価</a>
  <a href="#weekly"  class="tab">週次レポート</a>
  <a href="#columns" class="tab">コラム</a>
  <a href="#archive" class="tab">記事検索</a>
  <a href="#about"   class="tab">About</a>
</div>

<div class="pane" id="pane-today">
  <div class="focus-strip" aria-label="注目領域">
    <a class="focus-card" href="?tag=脆弱性#archive"><strong>脆弱性・CVE</strong><span>本日 {vuln_count}件 · 悪用状況、パッチ、露出管理</span></a>
    <a class="focus-card" href="#engineering"><strong>診断技術・評価</strong><span>ハーネス、検知性能、修正案の検証</span></a>
    <a class="focus-card" href="?tag=AI×セキュリティ#archive"><strong>AIエージェント</strong><span>MCP、権限、情報漏えい、監査</span></a>
  </div>
  <div id="today-impl-box" style="display:none;background:#f2f6fa;border-left:3px solid #245d86;border-radius:4px;padding:12px 16px;margin-bottom:16px">
    <div style="font-size:10px;font-weight:700;color:#245d86;letter-spacing:.05em;text-transform:uppercase;margin-bottom:6px">本日の示唆</div>
    <div id="today-impl-text" style="font-size:12px;line-height:1.8;color:#475361"></div>
    <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-top:8px">
      <a href="#trend" style="font-size:11px;color:#245d86;text-decoration:none">→ 攻撃・インシデント動向で詳しく見る</a>
      {weekly_today_link}
      {related_column_link}
    </div>
  </div>
  <p class="plabel">{today} のニュース（{len(articles)}件）</p>
  {today_html}
</div>

<div class="pane" id="pane-archive">
  <p class="plabel">記事検索</p>
  <p class="srch-desc">過去記事をテーマ・文脈・カテゴリから探せます。脆弱性、攻撃・インシデント、診断技術・評価の調査に活用できます。</p>
  <div id="srch-url-notice" class="srch-url-notice" style="display:none">適用中の条件：<span id="srch-url-label"></span></div>
  <div class="srch-input-wrap">
    <span class="srch-input-icon">🔍</span>
    <input type="search" id="srch-input" class="srch-input" placeholder="キーワードを入力（例：診断ハーネス、CVE、修正評価）" autocomplete="off">
  </div>
  <div class="srch-section-lbl">テーマから探す</div>
  <div class="srch-themes" id="srch-themes"></div>
  <div class="srch-filters">
    <div class="srch-filter-row">
      <span class="srch-filter-lbl">文脈</span>
      <div id="srch-ctx"></div>
    </div>
    <div class="srch-filter-row">
      <span class="srch-filter-lbl">カテゴリ</span>
      <div id="srch-cat"></div>
    </div>
    <div class="srch-filter-row">
      <span class="srch-filter-lbl">CDC関連度</span>
      <div id="srch-cdc"></div>
    </div>
    <div class="srch-filter-row">
      <span class="srch-filter-lbl">期間</span>
      <div id="srch-period"></div>
    </div>
  </div>
  <div class="srch-meta">
    <span id="srch-count" class="srch-count"></span>
    <button class="srch-clear-btn" onclick="clearSearch()">条件をクリア</button>
  </div>
  <div id="srch-results"></div>
  <div id="srch-more-wrap" style="display:none;text-align:center;margin:14px 0">
    <button id="srch-more-btn" class="srch-more-btn">さらに表示</button>
  </div>
  <details class="srch-arc-details">
    <summary class="srch-arc-summary">日付別に見る</summary>
    <div style="margin-top:12px">
      {archive_rows if archive_rows else '<p class="empty">蓄積中...</p>'}
    </div>
  </details>
</div>

{watch_html}
{engineering_html}


{weekly_pane_html}

{columns_pane_html}

<div class="pane" id="pane-about">
  <p class="plabel">About</p>
  <div class="about-wrap">

    <!-- Hero -->
    <div class="about-hero">
      <div class="about-hero-name">このサイトについて</div>

      <p class="about-hero-lead">脆弱性診断・脆弱性管理・AIエージェントの安全性を中心に、日々の業務で読む情報を整理するノートです。企業インシデント、政策・地政学、市場の変化も追います。</p>
    </div>

    <!-- 3つの観点軸 -->
    <div class="about-section">
      <div class="about-section-lbl">情報収集の重点</div>
      <div class="about-axes">
        <div class="about-axis">
          <div class="about-axis-label" style="color:#245d86">脆弱性管理・診断</div>
          <div class="about-axis-desc">発見、評価、診断、修正、再診断、継続管理。SAST/SCA/DAST、Web・API・クラウド診断に加え、ハーネス設計と診断・修正性能の評価を追います。</div>
        </div>
        <div class="about-axis">
          <div class="about-axis-label" style="color:#E24B4A">Security for AI</div>
          <div class="about-axis-desc">AIシステム・LLM・エージェントへの攻撃と防御。プロンプトインジェクション、モデル汚染、エージェントハイジャック。</div>
        </div>
        <div class="about-axis">
          <div class="about-axis-label" style="color:#1D9E75">インシデント・政策・市場</div>
          <div class="about-axis-desc">企業被害、情報漏えい、国家支援型攻撃、経済安全保障、日本の制度・市場。</div>
        </div>
      </div>
    </div>

    <div class="about-section"><div class="about-section-lbl">情報の扱い</div><div class="about-text"><p>国内の公的情報・一次情報を優先し、海外の関連ニュースも日本語で整理します。最大15件とし、関連性の低い情報で件数を埋めません。過去記事とコラムは引き続き閲覧できます。</p><p>追加情報は収集した抜粋に基づく自動生成です。不明な項目は不明と表示します。対応判断では元の公表資料をご確認ください。</p></div></div>

  </div>
</div>

<footer style="text-align:center;font-size:10px;color:var(--dim);padding:20px;border-top:1px solid var(--border);margin-top:16px">
  <p style="margin-bottom:2px;font-size:11px;font-weight:600;color:var(--dim)">Cyber Defense Notes</p>
  <p>各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。<br>日本語要約・タグ・示唆はLLMにより自動生成されており、誤りや不正確な情報を含む可能性があります。重要な判断には必ず元記事をご確認ください。</p>
  <p style="margin-top:4px">Powered by Gemini API + GitHub Actions</p>
</footer>

<script>
const ANA = {ana_json};
const TAX = {tax_json};
const IMP_COLORS = {{"高":"#E24B4A","中":"#BA7517","低":"#639922"}};
const MAIN_COLORS = {{"attack":"#E24B4A","vuln":"#BA7517","ai_sec":"#245d86","ai_risk":"#7F77DD","policy":"#1D9E75","incident":"#D85A30","biz_tech":"#639922"}};
const LAYER_COLORS = {{"デバイス/エッジ":"#639922","ネットワーク":"#245d86","クラウド/サーバー":"#1D9E75","アプリ/API":"#BA7517","データ/AI":"#7F77DD","ガバナンス/規制":"#566473"}};
const SEARCH_DATA = {search_json};

function showTab(id) {{
  var valid = ['today','archive','trend','engineering','weekly','columns','about'];
  if (id === 'popular' || valid.indexOf(id) < 0) id = 'today';
  document.querySelectorAll('.pane').forEach(function(p) {{ p.classList.remove('on'); }});
  document.querySelectorAll('.tab-bar .tab').forEach(function(t) {{
    t.classList.remove('on');
    t.removeAttribute('aria-current');
  }});
  var pane = document.getElementById('pane-' + id);
  if (pane) pane.classList.add('on');
  var tab = document.querySelector('.tab-bar a[href="#' + id + '"]');
  if (tab) {{ tab.classList.add('on'); tab.setAttribute('aria-current', 'page'); }}
}}

function initTab() {{
  var h = location.hash.replace('#','') || 'today';
  showTab(h);
}}

window.addEventListener('hashchange', function() {{
  var h = location.hash.replace('#','') || 'today';
  showTab(h);
  if (typeof gtag !== 'undefined') {{
    gtag('event', 'page_view', {{
      page_path: location.pathname + location.hash,
      page_title: document.title
    }});
  }}
}});

// すぐ実行（load待ちしない）
if (document.readyState === 'loading') {{
  document.addEventListener('DOMContentLoaded', initTab);
}} else {{
  initTab();
}}

function escapeHtml(s) {{
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}}

function renderKwCloud(containerId, data) {{
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!data || !data.length) {{ el.innerHTML='<p class="empty">データ蓄積中...</p>'; return; }}
  const top = data.slice(0, 15);
  const max = top[0][1] || 1;
  el.innerHTML = top.map(([kw, cnt]) => {{
    const esc  = escapeHtml(kw);
    const t    = Math.sqrt(cnt / max);
    const size = Math.round(52 + t * 36);
    const bgOp = (0.2 + t * 0.65).toFixed(2);
    const fs   = kw.length > 8 ? 9 : kw.length > 5 ? 10 : 11;
    return `<div class="kw-bubble" style="width:${{size}}px;height:${{size}}px;background:rgba(55,138,221,${{bgOp}});font-size:${{fs}}px" title="${{cnt}}件">` +
           `<span class="kw-bubble-word">${{esc}}</span>` +
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
  data.dates.forEach(d => {{ html += `<div class="hm-th">${{escapeHtml(d)}}</div>`; }});
  data.rows.forEach(row => {{
    const color = LAYER_COLORS[row.layer] || '#245d86';
    const [r,g,b] = hexToRgb(color);
    const layerEsc = escapeHtml(row.layer);
    html += `<div class="hm-lb" title="${{layerEsc}}">${{layerEsc}}</div>`;
    row.counts.forEach(cnt => {{
      const bg  = cnt === 0 ? '#f2f4f6' : `rgba(${{r}},${{g}},${{b}},${{Math.max(0.18, cnt/max).toFixed(2)}})`;
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
    const esc = escapeHtml(label);
    return `<div class="bar-row">
      <span class="bl" title="${{esc}}">${{esc}}</span>
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
  var cleaned = text.replace(/★[^\\n]*/g, '').trim();
  var sections = cleaned.split(/(?=【[^】]+】)/);
  var summary = '';
  var rest = [];
  sections.forEach(function(sec) {{
    sec = sec.trim();
    if (!sec) return;
    if (sec.indexOf('【今日の結論】') === 0) {{ summary = sec; }}
    else {{ rest.push(sec); }}
  }});
  if (!summary && sections.length > 0) {{
    summary = sections[0].trim();
    rest = sections.slice(1).map(function(s) {{ return s.trim(); }}).filter(Boolean);
  }}
  function renderSec(s) {{
    s = escapeHtml(s);
    return s
      .replace(/【([^】]+)】\\n?/g,
        '<span style="display:block;font-size:'+fs+';font-weight:700;color:#245d86;letter-spacing:.04em;margin-top:'+mt+';margin-bottom:2px">【$1】</span>')
      .replace(/\\n/g, '<br>');
  }}
  var html = renderSec(summary);
  if (rest.length > 0) {{
    html += '<details class="imp-detail"><summary class="imp-detail-toggle"></summary>'
      + rest.map(renderSec).join('<br>')
      + '</details>';
  }}
  el.innerHTML = html;
  box.style.display = '';
}}

function initDashboard() {{
  if (ANA.today_implication) {{
    renderImplication(ANA.today_implication, 'today-impl-text', 'today-impl-box', true);
  }}
  return;

  document.getElementById('s-total').textContent = ANA.total_articles;
  document.getElementById('s-days').textContent  = ANA.total_days;
  document.getElementById('s-spike').textContent = ANA.spikes.length;

  const spikeEl = document.getElementById('spike-list');
  if (ANA.spikes.length) {{
    spikeEl.innerHTML = ANA.spikes.map(s =>
      `<div class="spike-item">
        <span class="spike-name">${{escapeHtml(s.sub)}}</span>
        <span class="spike-badge">今週 ${{s.cnt_7}}件 急増</span>
      </div>`
    ).join('');
  }} else {{
    spikeEl.innerHTML = '<p class="empty">データ蓄積中... 1週間以上のデータが揃うと表示されます</p>';
  }}

  renderBars('main-bars-7',
    ANA.main_7.map(([k,v,l]) => [l,v]),
    label => {{ const k = ANA.main_7.find(([_,__,l])=>l===label)?.[0]; return MAIN_COLORS[k]||'#245d86'; }}
  );

  // 重要度バー
  const impData = [["高", impCount["高"]], ["中", impCount["中"]], ["低", impCount["低"]]].filter(([,v])=>v>0);
  renderBars('imp-bars', impData, label => IMP_COLORS[label]||'#888');

  // 影響レイヤーバー
  if (ANA.layer_7 && ANA.layer_7.length) {{
    renderBars('layer-bars', ANA.layer_7, label => LAYER_COLORS[label]||'#245d86');
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
    const color = MAIN_COLORS[k] || '#245d86';
    const btn = document.createElement("button");
    btn.className = "sf-btn" + (i===0 ? " on" : "");
    btn.dataset.key = k;
    if (i===0) {{ btn.style.borderColor=color; btn.style.color=color; btn.style.background=color+"22"; }}
    btn.textContent = label;
    btn.addEventListener("click", (function(key,c){{ return function(){{ selectMain(key,this,c); }}; }})(k,color));
    filterEl.appendChild(btn);
  }});
  selectMain(mainKeys[0], filterEl.querySelector('.sf-btn.on'), MAIN_COLORS[mainKeys[0]]||'#245d86');
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

function navigateCard(id) {{
  if (!id) return;
  location.href = '/ai-security-news/article/' + id + '.html';
}}
function toggleKw(id, btn) {{
  var el = document.getElementById(id);
  if (!el) return;
  var open = btn.dataset.open === '1';
  el.style.display = open ? 'none' : '';
  btn.dataset.open = open ? '0' : '1';
  btn.setAttribute('aria-expanded', open ? 'false' : 'true');
  btn.textContent = open ? 'タグを表示' : 'タグを隠す';
}}

// ── 記事検索 ──────────────────────────────────────────────────
const SRCH_THEMES = [
  {{id:'engineering', label:'診断技術・評価', kws:[]}},
  {{id:'agent',  label:'AIエージェント',  kws:['aiエージェント','agentic','agent','自律','ツール実行','mcp']}},
  {{id:'llmsec', label:'LLMセキュリティ', kws:['llm','生成ai','プロンプトインジェクション','ジェイルブレイク','モデル汚染','データポイズニング']}},
  {{id:'s4ai',   label:'Security for AI', kws:['security for ai','aiシステム','rag','mcp','モデル','プロンプト','aiガバナンス','ai権限']}},
  {{id:'ai4s',   label:'AI for Security', kws:['ai for security','soc','siem','edr','mdr','脅威ハンティング','アラート','インシデント対応']}},
  {{id:'soc',    label:'SOC/CDC',          kws:['soc','cdc','mdr','mssp','tier','エスカレーション','ciso報告','監査','復旧','サービス企画']}},
  {{id:'itdr',   label:'Identity/ITDR',   kws:['identity','itdr','id管理','非人間型id','認証','認可','権限','iam','entra','okta','active directory']}},
  {{id:'vuln',   label:'脆弱性管理',       kws:['脆弱性','cve','kev','エクスプロイト','パッチ','exposure','ctem','攻撃可能状態']}},
  {{id:'gov',    label:'AIガバナンス',     kws:['aiガバナンス','aiリスク','規制','nist','eu ai法','コンプライアンス','監査']}},
];
const SRCH_CTX = [
  {{id:'all',  label:'すべて',           match:null}},
  {{id:'s4ai', label:'Security for AI', match:['Security for AI']}},
  {{id:'ai4s', label:'AI for Security', match:['AI for Security']}},
  {{id:'soc',  label:'SOC/CDC',          match:['SOC運用変化','MDR/MSSP設計','サービス企画','CISO報告','顧客課題']}},
  {{id:'itdr', label:'Identity/ITDR',   match:['Identity/ITDR']}},
  {{id:'exp',  label:'Exposure管理',     match:['Exposure管理']}},
  {{id:'ciso', label:'CISO報告',         match:['CISO報告']}},
];
const SRCH_CAT = [
  {{id:'all',      label:'すべて'}},
  {{id:'ai_sec',   label:'AI×セキュリティ'}},
  {{id:'ai_risk',  label:'AIリスク'}},
  {{id:'vuln',     label:'脆弱性'}},
  {{id:'attack',   label:'攻撃・脅威'}},
  {{id:'incident', label:'インシデント'}},
  {{id:'policy',   label:'規制・政策'}},
  {{id:'biz_tech', label:'ビジネス・技術動向'}},
];
const SRCH_CDC = [
  {{id:'all',label:'すべて'}},
  {{id:'2',  label:'中以上'}},
  {{id:'3',  label:'高のみ'}},
];
const SRCH_PERIOD = [
  {{id:'all',label:'すべて'}},
  {{id:'7',  label:'直近7日'}},
  {{id:'30', label:'直近30日'}},
  {{id:'90', label:'直近90日'}},
];

var srchState = {{query:'',theme:null,ctx:'all',cat:'all',cdc:'all',period:'all'}};
var srchOffset = 0;
var SRCH_PAGE = 30;
var srchFiltered = [];

// 記事ページの cdc_context 値 → 記事検索の文脈フィルター ID マッピング
const CTX_MAP = {{
  'SOC運用変化':   'soc',
  'MDR/MSSP設計':  'soc',
  'サービス企画':   'soc',
  '顧客課題':       'soc',
  'CISO報告':      'ciso',
  'Identity/ITDR': 'itdr',
  'Exposure管理':  'exp',
  'Security for AI': 's4ai',
  'AI for Security': 'ai4s',
}};

function applyUrlParams() {{
  var params = new URLSearchParams(location.search);
  var labels = [];

  var q = params.get('q');
  if (q) {{
    srchState.query = q;
    var inp = document.getElementById('srch-input');
    if (inp) inp.value = q;
    labels.push(q);
  }}

  var ctx = params.get('context');
  if (ctx) {{
    var ctxId = CTX_MAP[ctx];
    if (!ctxId) {{
      var found = SRCH_CTX.find(function(c) {{ return c.label === ctx; }});
      if (found) ctxId = found.id;
    }}
    if (ctxId && ctxId !== 'all') {{
      srchState.ctx = ctxId;
      var ctxEl = document.getElementById('srch-ctx');
      if (ctxEl) {{
        ctxEl.querySelectorAll('.srch-chip').forEach(function(b) {{
          b.classList.toggle('on', b.dataset.val === ctxId);
        }});
      }}
      labels.push(ctx);
    }}
  }}

  var tag = params.get('tag');
  if (tag) {{
    srchState.query = tag;
    var inp2 = document.getElementById('srch-input');
    if (inp2) inp2.value = tag;
    labels.push(tag);
  }}

  var theme = params.get('theme');
  if (theme) {{
    var themeFound = SRCH_THEMES.find(function(t) {{ return t.id === theme || t.label === theme; }});
    if (themeFound) {{
      srchState.theme = themeFound.id;
      var themeEl = document.getElementById('srch-themes');
      if (themeEl) {{
        themeEl.querySelectorAll('.srch-theme-btn').forEach(function(b) {{
          b.classList.toggle('on', b.dataset.theme === themeFound.id);
        }});
      }}
      labels.push(themeFound.label);
    }}
  }}

  if (labels.length > 0) {{
    var notice = document.getElementById('srch-url-notice');
    var lbl = document.getElementById('srch-url-label');
    if (notice && lbl) {{
      lbl.textContent = labels.join(' ＋ ');
      notice.style.display = '';
    }}
  }}
}}

function safeArtHref(id) {{
  if (!id || !/^[a-zA-Z0-9_-]{{1,64}}$/.test(id)) return '#';
  return '/ai-security-news/article/' + id + '.html';
}}

function buildSrchChips(containerId, items, stateKey) {{
  var el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = items.map(function(item) {{
    return '<button class="srch-chip' + (item.id==='all'?' on':'') + '" data-val="' + escapeHtml(item.id) + '">' + escapeHtml(item.label) + '</button>';
  }}).join('');
  el.querySelectorAll('.srch-chip').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      el.querySelectorAll('.srch-chip').forEach(function(b) {{ b.classList.remove('on'); }});
      this.classList.add('on');
      srchState[stateKey] = this.dataset.val;
      runSearch();
    }});
  }});
}}

function initSearch() {{
  var themeEl = document.getElementById('srch-themes');
  if (themeEl) {{
    themeEl.innerHTML = SRCH_THEMES.map(function(t) {{
      return '<button class="srch-theme-btn" data-theme="' + escapeHtml(t.id) + '">' + escapeHtml(t.label) + '</button>';
    }}).join('');
    themeEl.querySelectorAll('.srch-theme-btn').forEach(function(btn) {{
      btn.addEventListener('click', function() {{
        var tid = this.dataset.theme;
        if (srchState.theme === tid) {{
          srchState.theme = null;
          this.classList.remove('on');
        }} else {{
          srchState.theme = tid;
          themeEl.querySelectorAll('.srch-theme-btn').forEach(function(b) {{ b.classList.remove('on'); }});
          this.classList.add('on');
        }}
        runSearch();
      }});
    }});
  }}
  buildSrchChips('srch-ctx',    SRCH_CTX,    'ctx');
  buildSrchChips('srch-cat',    SRCH_CAT,    'cat');
  buildSrchChips('srch-cdc',    SRCH_CDC,    'cdc');
  buildSrchChips('srch-period', SRCH_PERIOD, 'period');
  var inputEl = document.getElementById('srch-input');
  if (inputEl) {{
    inputEl.addEventListener('input', function() {{
      srchState.query = this.value;
      runSearch();
    }});
  }}
  var moreBtn = document.getElementById('srch-more-btn');
  if (moreBtn) moreBtn.addEventListener('click', showSrchMore);
  applyUrlParams();
  runSearch();
}}

function runSearch() {{
  var q = (srchState.query || '').toLowerCase().trim();
  var activeTheme = srchState.theme
    ? SRCH_THEMES.find(function(t) {{ return t.id === srchState.theme; }})
    : null;

  var results = SEARCH_DATA.filter(function(a) {{
    if (srchState.period !== 'all') {{
      var cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - parseInt(srchState.period, 10));
      if ((a.date || '') < cutoff.toISOString().slice(0, 10)) return false;
    }}
    if (srchState.ctx !== 'all') {{
      var ctxF = SRCH_CTX.find(function(f) {{ return f.id === srchState.ctx; }});
      if (ctxF && ctxF.match) {{
        var ctx = a.cdc_context || [];
        if (!ctxF.match.some(function(m) {{ return ctx.indexOf(m) >= 0; }})) return false;
      }}
    }}
    if (srchState.cat !== 'all' && a.tag_main_id !== srchState.cat) return false;
    if (activeTheme && activeTheme.id === 'engineering' && !(a.engineering_topics || []).length) return false;
    if (srchState.cdc === '2' && (a.cdc_relevance || 0) < 2) return false;
    if (srchState.cdc === '3' && (a.cdc_relevance || 0) < 3) return false;
    return true;
  }});

  if (!q && !activeTheme) {{
    results.sort(function(a, b) {{ return (b.date || '').localeCompare(a.date || ''); }});
  }} else {{
    var scored = results.map(function(a) {{
      var score = 0;
      if (q) {{
        if ((a.title_ja || '').toLowerCase().indexOf(q) >= 0) score += 5;
        if ((a.related_keywords || []).some(function(k) {{ return k.toLowerCase().indexOf(q) >= 0; }})) score += 4;
        if ((a.tag_subs || []).some(function(s) {{ return s.toLowerCase().indexOf(q) >= 0; }})) score += 3;
        if ((a.cdc_context || []).some(function(c) {{ return c.toLowerCase().indexOf(q) >= 0; }})) score += 3;
        if ((a.tag_main_label || '').toLowerCase().indexOf(q) >= 0) score += 3;
        if ((a.summary_ja || '').toLowerCase().indexOf(q) >= 0) score += 2;
        if ((a.insight || '').toLowerCase().indexOf(q) >= 0) score += 1;
        if ((a.source_name || '').toLowerCase().indexOf(q) >= 0) score += 1;
        if ((a.engineering_topics || []).some(function(t) {{ return t.toLowerCase().indexOf(q) >= 0; }})) score += 4;
      }}
      if (activeTheme) {{
        if (activeTheme.id === 'engineering') score += (a.engineering_topics || []).length * 3;
        var allText = [
          a.title_ja, a.summary_ja, a.insight, a.tag_main_label,
          (a.tag_subs || []).join(' '),
          (a.cdc_context || []).join(' '),
          (a.related_keywords || []).join(' ')
        ].join(' ').toLowerCase();
        var matches = activeTheme.kws.filter(function(kw) {{ return allText.indexOf(kw) >= 0; }}).length;
        score += matches * 2;
      }}
      score += (a.cdc_relevance || 0) * 0.1;
      return {{a: a, score: score}};
    }});
    results = scored
      .filter(function(x) {{ return x.score > 0; }})
      .sort(function(x, y) {{
        return x.score !== y.score
          ? y.score - x.score
          : (y.a.date || '').localeCompare(x.a.date || '');
      }})
      .map(function(x) {{ return x.a; }});
  }}

  srchFiltered = results;
  srchOffset = 0;
  renderSrchPage();
}}

function renderSrchPage() {{
  var countEl   = document.getElementById('srch-count');
  var resultsEl = document.getElementById('srch-results');
  var moreWrap  = document.getElementById('srch-more-wrap');
  if (!resultsEl) return;
  var total = srchFiltered.length;
  if (countEl) countEl.textContent = total + '件';
  if (total === 0) {{
    resultsEl.innerHTML = '<p class="srch-empty">該当する記事がありません</p>';
    if (moreWrap) moreWrap.style.display = 'none';
    return;
  }}
  var page = srchFiltered.slice(0, SRCH_PAGE);
  resultsEl.innerHTML = page.map(renderSrchCard).join('');
  srchOffset = page.length;
  if (moreWrap) moreWrap.style.display = srchFiltered.length > srchOffset ? '' : 'none';
}}

function showSrchMore() {{
  var resultsEl = document.getElementById('srch-results');
  var moreWrap  = document.getElementById('srch-more-wrap');
  if (!resultsEl) return;
  var next = srchFiltered.slice(srchOffset, srchOffset + SRCH_PAGE);
  resultsEl.innerHTML += next.map(renderSrchCard).join('');
  srchOffset += next.length;
  if (moreWrap) moreWrap.style.display = srchFiltered.length > srchOffset ? '' : 'none';
}}

function renderSrchCard(a) {{
  var href  = safeArtHref(a.id);
  var title = escapeHtml(a.title_ja || '(タイトルなし)');
  var smry  = a.summary_ja || '';
  var smryEsc = escapeHtml(smry.length > 120 ? smry.slice(0, 120) + '…' : smry);
  var cdcRel   = a.cdc_relevance || 0;
  var cdcColor = cdcRel >= 3 ? '#E24B4A' : cdcRel >= 2 ? '#BA7517' : '#566473';
  var cdcLabel = cdcRel >= 3 ? '高' : cdcRel >= 2 ? '中' : '低';
  var mc = MAIN_COLORS[a.tag_main_id] || '#245d86';
  var ml = escapeHtml(a.tag_main_label || '');
  var subTags = (a.tag_subs || []).slice(0, 3).map(function(s) {{
    return '<span class="tag-sub">' + escapeHtml(s) + '</span>';
  }}).join('');
  var ctxTags = (a.cdc_context || []).slice(0, 2).map(function(c) {{
    return '<span class="cdc-badge">' + escapeHtml(c) + '</span>';
  }}).join('');
  var engTags = (a.engineering_topics || []).slice(0, 2).map(function(t) {{
    return '<span class="tag-sub">' + escapeHtml(t) + '</span>';
  }}).join('');
  return '<a href="' + href + '" class="srch-card">' +
    '<div class="srch-card-meta">' +
      '<span class="dt">' + escapeHtml(a.date || '') + '</span>' +
      (a.source_name ? '<span class="src">' + escapeHtml(a.source_name) + '</span>' : '') +
      '<span class="imp" style="color:' + cdcColor + ';border-color:' + cdcColor + '55">CDC: ' + cdcLabel + '</span>' +
    '</div>' +
    '<div class="srch-card-title">' + title + '</div>' +
    (smryEsc ? '<div class="srch-card-summary">' + smryEsc + '</div>' : '') +
    '<div class="srch-card-tags">' +
      (ml ? '<span class="tag-main" style="background:' + mc + '20;color:' + mc + ';border-color:' + mc + '44">' + ml + '</span>' : '') +
      (srchState.theme === 'engineering' ? engTags : subTags + ctxTags) +
    '</div>' +
  '</a>';
}}

function clearSearch() {{
  srchState.query  = '';
  srchState.theme  = null;
  srchState.ctx    = 'all';
  srchState.cat    = 'all';
  srchState.cdc    = 'all';
  srchState.period = 'all';
  var inp = document.getElementById('srch-input');
  if (inp) inp.value = '';
  document.querySelectorAll('.srch-theme-btn').forEach(function(b) {{ b.classList.remove('on'); }});
  document.querySelectorAll('.srch-chip').forEach(function(b) {{
    b.classList.toggle('on', b.dataset.val === 'all');
  }});
  var notice = document.getElementById('srch-url-notice');
  if (notice) notice.style.display = 'none';
  if (location.search) history.replaceState(null, '', location.pathname + location.hash);
  runSearch();
}}

document.addEventListener('DOMContentLoaded', initSearch);
</script>

</body>
</html>"""


def build_article_page(article, all_articles, taxonomy, columns=None):
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
    cdc_contexts = a.get("cdc_context", [])[:3]
    try:
        cdc_relevance = max(0, min(3, int(a.get("cdc_relevance", 0))))
    except (ValueError, TypeError):
        cdc_relevance = 0
    cdc_rel_label = {1: "低", 2: "中", 3: "高"}.get(cdc_relevance, "")

    # 記事のCDC contextと一致するコラムを抽出
    art_cdc_set = set(cdc_contexts)
    matched_cols = []
    for col in (columns or []):
        col_cdcs = col_cdc_set(col.get("tags", []))
        if col_cdcs & art_cdc_set:
            matched_cols.append(col)
    matched_cols_html = ""
    if matched_cols and cdc_relevance >= 1:
        col_items = []
        for col in matched_cols[:2]:
            cslug = col.get("slug", "")
            ctitle = col.get("title", "")
            cdate = col.get("date", "")
            col_items.append(
                f'<a href="../columns/{cslug}.html" class="rel-item">'
                f'<div class="rel-meta"><span class="rel-date">{html_escape(cdate)}</span>'
                f'<span style="font-size:10px;padding:1px 6px;border-radius:99px;background:#1a2e1a;border:1px solid #2a5a2a;color:#6add8a">著者執筆</span></div>'
                f'<div class="rel-title">{html_escape(ctitle)}</div></a>'
            )
        matched_cols_html = (
            f'<section class="ap-section">'
            f'<h3 class="ap-sec-title">このテーマで書かれたコラム</h3>'
            f'<div class="rel-list">{"".join(col_items)}</div>'
            f'</section>'
        )

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
                f'{imp_badge(r_imp)}<span class="rel-src">{html_escape(r_src)}</span></div>'
                f'<div class="rel-title">{html_escape(r_title)}</div></a>'
            )
        related_html = f"""<section class="ap-section">
  <h3 class="ap-sec-title">関連記事：同じ「{html_escape(main_label)}」の最近の記事</h3>
  <div class="rel-list">{"".join(related_items)}</div>
</section>"""

    subs_html = "".join(tag_sub_badge(s) for s in subs)

    # 「このテーマをもっと探す」チップ選定（最大5個・20字以内・重複排除）
    _explore_chips = []  # list of (label, attr_type)
    _explore_seen = set()

    def _add_explore(label, attr_type):
        clean = (label or "").strip()
        if not clean or len(clean) > 20:
            return
        norm = clean.lower()
        if norm in _explore_seen or len(_explore_chips) >= 5:
            return
        _explore_seen.add(norm)
        _explore_chips.append((clean, attr_type))

    for ctx in cdc_contexts:              # 優先1: cdc_context
        _add_explore(ctx, "context")
    for s in subs:                        # 優先2: tag_subs
        _add_explore(s, "tag")
    _add_explore(main_label, "tag")       # 優先3: tag_main_label
    for kw in a.get("related_keywords", [])[:6]:  # 優先4: related_keywords
        _add_explore(kw, "keyword")

    explore_html = ""
    if _explore_chips:
        chips_parts = []
        for label, attr_type in _explore_chips:
            enc = _url_quote(label, safe="")
            if attr_type == "context":
                href = html_escape(f"../?context={enc}#archive")
                data_attr = f'data-search-context="{html_escape(label)}"'
            elif attr_type == "tag":
                href = html_escape(f"../?tag={enc}#archive")
                data_attr = f'data-search-tag="{html_escape(label)}"'
            else:
                href = html_escape(f"../?q={enc}#archive")
                data_attr = f'data-search-keyword="{html_escape(label)}"'
            chips_parts.append(
                f'<a href="{href}" class="explore-chip" {data_attr}>{html_escape(label)}</a>'
            )
        explore_html = (
            f'<section class="ap-section">'
            f'<h3 class="ap-sec-title">このテーマをもっと探す</h3>'
            f'<p class="explore-desc">この記事に近いテーマの記事を、記事検索タブで探せます。'
            f'（関連記事は下の「関連記事」セクションで直接読めます）</p>'
            f'<div class="explore-chips">{"".join(chips_parts)}</div>'
            f'<a href="../#archive" class="explore-cta">記事検索で関連テーマを見る →</a>'
            f'</section>'
        )

    # 構造化データで使用する公開URL
    site_url = f"https://ayudle.github.io/ai-security-news/article/{aid}.html"

    jsonld_str = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title_ja,
        "description": summary_ja[:200],
        "datePublished": pub,
        "url": site_url,
        "image": "https://ayudle.github.io/ai-security-news/og-image.png",
        "publisher": {
            "@type": "Organization",
            "name": "Cyber Defense Notes",
            "url": "https://ayudle.github.io/ai-security-news/",
        },
        "author": {
            "@type": "Person",
            "name": "Cyber Defense Notes",
        },
    }, ensure_ascii=False, indent=2).replace('</', '<\\/')

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html_escape(title_ja)} | Cyber Defense Notes</title>
<meta name="description" content="{html_escape(summary_ja[:120])}">
<meta property="og:title" content="{html_escape(title_ja)}">
<meta property="og:description" content="{html_escape(summary_ja[:120])}">
<meta property="og:url" content="{site_url}">
<meta property="og:type" content="article">
<meta property="og:image" content="https://ayudle.github.io/ai-security-news/og-image.png">
<link rel="canonical" href="{site_url}">
<link rel="icon" type="image/png" href="../favicon.png">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<script type="application/ld+json">
{jsonld_str}
</script>
<style>
:root{{--bg:#ffffff;--text:#202830;--dim:#566473;--border:#d9dfe5;--accent:#245d86;--card:#f6f7f8;--insight-bg:#f2f6fa;--insight-border:#245d86}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);line-height:1.7}}
header{{border-bottom:1px solid var(--border);padding:16px 24px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}}
.logo{{font-size:18px;font-weight:700;margin:0;color:#202830}}
.logo-link{{text-decoration:none;color:inherit}}
.logo-link:hover .logo{{color:var(--accent)}}
.meta-top{{font-size:11px;color:var(--dim)}}
.back{{display:inline-block;padding:8px 16px;margin:12px 24px 0;color:var(--accent);text-decoration:none;font-size:13px}}
.back:hover{{text-decoration:underline}}
.sub-nav{{display:flex;flex-wrap:wrap;gap:16px;padding:10px 24px 12px;border-bottom:1px solid var(--border);font-size:13px}}
.sub-nav a{{color:var(--accent)}}
.ap{{max-width:720px;margin:0 auto;padding:16px 24px 60px}}
.ap-head{{border-bottom:1px solid var(--border);padding-bottom:24px;margin-bottom:24px}}
.ap-meta{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px;color:var(--dim);margin-bottom:12px}}
.ap-tier{{display:inline-block;padding:2px 8px;border-radius:4px;background:var(--card);color:var(--accent);font-weight:600}}
.ap-src{{color:var(--text)}}
.ap-title{{font-size:26px;font-weight:700;color:#202830;margin:8px 0;line-height:1.4}}
.ap-section{{margin-bottom:32px}}
.ap-sec-title{{font-size:11px;font-weight:700;letter-spacing:.1em;color:var(--dim);text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)}}
.ap-body{{font-size:15px;line-height:1.85;color:var(--text)}}
.insight-box{{background:var(--insight-bg);border-left:3px solid var(--insight-border);padding:16px 20px;border-radius:4px;margin-top:12px}}
.insight-lbl{{display:block;font-size:11px;font-weight:700;color:var(--accent);margin-bottom:8px;letter-spacing:.05em}}
.insight-body{{font-size:14px;line-height:1.75;color:var(--text)}}
.imp-box{{padding:12px 16px;background:var(--card);border-radius:4px;margin-top:12px;font-size:13px;color:var(--dim)}}
.cdc-box{{padding:12px 16px;background:#f2f6fa;border:1px solid #d9dfe5;border-radius:4px;margin-top:12px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}}
.cdc-rel-lbl{{font-size:11px;font-weight:700;color:#245d86;margin-right:4px}}
.cdc-badge-ap{{font-size:11px;padding:2px 8px;border-radius:4px;background:#eef1f4;border:1px solid #d9dfe5;color:#245d86}}
.tags-box{{display:flex;flex-wrap:wrap;gap:6px}}
.tag-main{{display:inline-block;padding:4px 10px;border-radius:4px;font-size:12px;font-weight:600}}
.tag-sub{{display:inline-block;padding:4px 10px;border-radius:4px;font-size:12px;background:var(--card);color:var(--text);border:1px solid var(--border)}}
.orig-box{{background:var(--card);padding:16px;border-radius:4px;font-size:13px}}
.orig-box > div{{margin-bottom:6px}}
.orig-box .lbl{{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}}
.orig-en{{font-style:italic;color:var(--dim);margin-top:8px;font-size:12px;line-height:1.6}}
.actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}}
.btn{{display:inline-block;padding:10px 16px;border-radius:4px;text-decoration:none;font-size:13px;font-weight:500;cursor:pointer;border:none;font-family:inherit}}
.btn-primary{{background:var(--accent);color:#202830}}
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
.explore-desc{{font-size:12px;color:var(--dim);line-height:1.65;margin-bottom:10px}}
.explore-chips{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}}
.explore-chip{{font-size:11px;padding:4px 12px;border-radius:99px;border:1px solid var(--border);background:transparent;color:var(--dim);text-decoration:none;transition:border-color .15s,color .15s}}
.explore-chip:hover{{border-color:var(--accent);color:var(--accent)}}
.explore-cta{{font-size:13px;color:var(--accent);text-decoration:none;display:inline-block;margin-top:2px}}
.explore-cta:hover{{text-decoration:underline}}
footer{{text-align:center;font-size:10px;color:var(--dim);padding:20px;border-top:1px solid var(--border);margin-top:16px}}
</style>
{ga_snippet()}
</head>
<body>
<header>
  <a href="../" class="logo-link"><h1 class="logo">Cyber Defense Notes</h1></a>
</header>

<a href="../#today" class="back">← ニュース一覧に戻る</a>
<nav class="sub-nav">
  <a href="../#today">今日のニュース</a>
  <a href="../#trend">攻撃・インシデント動向</a>
  <a href="../#weekly">週次レポート</a>
  <a href="../#columns">コラム</a>
  <a href="../#archive">記事検索</a>
</nav>

<article class="ap">
  <div class="ap-head">
    <div class="ap-meta">
      <span class="ap-tier">{tier_label(source_tier)}</span>
      <span class="ap-src">{html_escape(source_name)}</span>
      <span>{pub}</span>
      {imp_badge(imp)}
    </div>
    <h1 class="ap-title">{html_escape(title_ja)}</h1>
  </div>

  <section class="ap-section">
    <h3 class="ap-sec-title">要約</h3>
    <div class="ap-body">{html_escape(summary_ja)}</div>
  </section>

  {business_details(article)}

  {"<section class='ap-section'><h3 class='ap-sec-title'>実務上の示唆</h3><div class='insight-box'><div class='insight-body'>" + html_escape(insight) + "</div></div></section>" if insight else ""}

  {"<section class='ap-section'><h3 class='ap-sec-title'>重要度判定の理由</h3><div class='imp-box'>" + html_escape(imp_reason) + "</div></section>" if imp_reason else ""}

  <section class="ap-section">
    <h3 class="ap-sec-title">タグ</h3>
    <div class="tags-box">
      {tag_main_badge(main_id, main_label)}
      {subs_html}
    </div>
  </section>

  {"<section class='ap-section'><h3 class='ap-sec-title'>CDC観点</h3><div class='cdc-box'>" + (f"<span class='cdc-rel-lbl'>CDC関連度：{cdc_rel_label}</span>" if cdc_rel_label else "") + "".join(f"<span class='cdc-badge-ap'>{html_escape(ctx)}</span>" for ctx in cdc_contexts) + "</div></section>" if cdc_relevance >= 1 and cdc_contexts else ""}

  {matched_cols_html}

  <section class="ap-section">
    <h3 class="ap-sec-title">元記事情報</h3>
    <div class="orig-box">
      <div class="lbl">原題</div>
      <div>{html_escape(title_en)}</div>
      <div class="lbl" style="margin-top:10px">ソース・公開日</div>
      <div>{html_escape(source_name)} / {pub}</div>
      <div class="orig-en">{html_escape(summary_en[:300])}</div>
    </div>
    <div class="actions">
      <a href="{_safe_url(url)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary">元記事を読む（外部サイト）</a>
      <button onclick="navigator.clipboard.writeText('{site_url}').then(()=>alert('URLをコピーしました'))" class="btn btn-secondary">URLをコピー</button>
    </div>
  </section>

  {explore_html}

  {related_html}
</article>

<footer>
  各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。<br>日本語要約・タグ・示唆はLLMにより自動生成されており、誤りや不正確な情報を含む可能性があります。重要な判断には必ず元記事をご確認ください。<br>
  <p style="margin-top:4px">Powered by Gemini API + GitHub Actions</p>
</footer>

</body>
</html>"""


def build_archive_page(day_data, date):
    """アーカイブページ（記事一覧のみ）を生成する"""
    articles = day_data.get("articles", [])
    n = len(articles)
    articles_html = "\n".join(article_card(a) for a in articles) if articles \
                    else '<p class="empty">この日の記事はありませんでした。</p>'
    arc_url   = f'https://ayudle.github.io/ai-security-news/archive/{date}.html'
    ogp_image = 'https://ayudle.github.io/ai-security-news/og-image.png'
    arc_title = f'{date} のニュース | Cyber Defense Notes'
    arc_desc  = f'Cyber Defense Notes の {date} のAI×セキュリティ/SOC/CDC関連記事アーカイブ。'
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{html_escape(arc_title)}</title>
<meta name="description" content="{html_escape(arc_desc)}">
<link rel="canonical" href="{arc_url}">
<meta property="og:title" content="{html_escape(arc_title)}">
<meta property="og:description" content="{html_escape(arc_desc)}">
<meta property="og:url" content="{arc_url}">
<meta property="og:type" content="website">
<meta property="og:image" content="{ogp_image}">
<link rel="icon" type="image/png" href="../favicon.png">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#0f0f0d;--card:#f6f7f8;--card2:#f2f4f6;--text:#202830;--muted:#566473;--dim:#566473;--border:#d9dfe5;--accent:#245d86;--r:10px}}
body{{font-family:-apple-system,"Helvetica Neue",sans-serif;background:var(--bg);color:var(--text);line-height:1.7;font-size:14px}}
a{{color:inherit;text-decoration:none}}
.hdr{{border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.ht{{font-size:15px;font-weight:700;color:#202830;margin:0}}
.back{{display:inline-block;padding:8px 16px;margin:12px 24px;color:var(--accent);text-decoration:none;font-size:13px}}
.back:hover{{text-decoration:underline}}
.content{{max-width:860px;margin:0 auto;padding:16px 24px}}
.plabel{{font-size:10px;font-weight:700;letter-spacing:.08em;color:var(--dim);text-transform:uppercase;margin-bottom:12px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:14px 16px;margin-bottom:10px;cursor:pointer;transition:border-color .15s}}
.card:hover{{border-color:#3a3a38}}
.cm{{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-bottom:8px}}
.tier{{background:#eef1f4;color:#245d86;font-size:10px;padding:2px 7px;border-radius:99px;font-weight:600}}
.src,.dt{{font-size:10px;color:var(--dim)}}
.dt{{margin-left:auto}}
.imp{{font-size:10px;padding:2px 6px;border-radius:99px;border:1px solid}}
.ct{{font-size:14px;font-weight:600;margin-bottom:6px;line-height:1.45}}
.ct a:hover{{color:var(--accent)}}
.tags{{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}}
.tag-main{{font-size:10px;padding:2px 8px;border-radius:99px;border:1px solid;font-weight:600}}
.tag-sub{{font-size:10px;padding:2px 7px;border-radius:99px;background:#f2f4f6;border:1px solid #d9dfe5;color:var(--muted)}}
.tags-meta{{margin-top:3px}}
.tag-layer{{font-size:9px;padding:1px 6px;border-radius:99px;background:#eef1f4;border:1px solid #d9dfe5;color:#245d86}}
.tag-kw{{font-size:9px;padding:1px 5px;border-radius:99px;background:#f2f4f6;border:1px solid #d9dfe5;color:#566473}}
.cf{{font-size:10px;color:var(--dim)}}
.cf a{{color:var(--accent)}}
.orig{{font-style:italic;margin-left:4px}}
.empty{{font-size:12px;color:var(--dim);padding:1rem 0}}
.insight{{background:#0d1e36;border-left:3px solid var(--accent);border-radius:0 6px 6px 0;padding:7px 10px;margin-bottom:8px;font-size:11px;color:#245d86;line-height:1.55}}
.ins-lbl{{display:block;font-size:9px;font-weight:700;color:var(--accent);letter-spacing:.06em;margin-bottom:2px;text-transform:uppercase}}
.insight-snippet{{font-size:12px;color:#9ca3af;line-height:1.55;margin-bottom:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.cdc-badges{{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin:4px 0}}
.cdc-lbl{{font-size:9px;font-weight:700;color:#245d86;letter-spacing:.06em;text-transform:uppercase;margin-right:2px}}
.cdc-badge{{font-size:9px;padding:1px 6px;border-radius:99px;background:#f2f6fa;border:1px solid #d9dfe5;color:#245d86}}
.kw-fold{{margin-top:2px}}
.kw-btn{{font-size:11px;background:transparent;border:1px solid var(--border);color:var(--muted);border-radius:99px;padding:4px 10px;cursor:pointer;margin-top:4px;font-family:inherit;transition:color .15s,border-color .15s;min-height:26px}}
.kw-btn:hover{{color:var(--text);border-color:var(--muted)}}
.kw-btn[aria-expanded="true"]{{background:var(--card2)}}
</style>
{ga_snippet()}
</head>
<body>
<header class="hdr">
  <span class="ht">Cyber Defense Notes</span>
</header>

<a href="/ai-security-news/#today" class="back">← トップページに戻る</a>

<div class="content">
  <p class="plabel">{date} のニュース（{n}件）</p>
  {articles_html}
</div>

<footer style="text-align:center;font-size:10px;color:var(--dim);padding:20px;border-top:1px solid var(--border);margin-top:16px">
  <p>各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。<br>日本語要約・タグ・示唆はLLMにより自動生成されており、誤りや不正確な情報を含む可能性があります。重要な判断には必ず元記事をご確認ください。</p>
  <p style="margin-top:4px">Powered by Gemini API + GitHub Actions</p>
</footer>

<script>
function navigateCard(id) {{
  if (!id) return;
  location.href = '/ai-security-news/article/' + id + '.html';
}}
function toggleKw(id, btn) {{
  var el = document.getElementById(id);
  if (!el) return;
  var open = btn.dataset.open === '1';
  el.style.display = open ? 'none' : '';
  btn.dataset.open = open ? '0' : '1';
  btn.setAttribute('aria-expanded', open ? 'false' : 'true');
  btn.textContent = open ? 'タグを表示' : 'タグを隠す';
}}
</script>

</body>
</html>"""


LAYER_COLORS_WEEKLY = {
    "デバイス/エッジ":   "#639922",
    "ネットワーク":       "#245d86",
    "クラウド/サーバー": "#1D9E75",
    "アプリ/API":         "#BA7517",
    "データ/AI":          "#7F77DD",
    "ガバナンス/規制":   "#566473",
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


def build_weekly_html(weekly_data, article_lookup=None):
    """週次レポートの standalone HTML ページを生成する"""
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
    # 重要トピック HTML
    lookup = article_lookup or {}
    topics_html = ""
    for i, t in enumerate(top_topics):
        title   = t.get("title", "")
        summary = t.get("summary", "")
        aids    = t.get("article_ids", [])

        # deduplicate by title+source+date
        seen_keys: set = set()
        items = []
        for aid in aids:
            a_data = lookup.get(aid)
            if a_data:
                a_title = a_data.get("title_ja") or a_data.get("title", "")
                a_src   = a_data.get("source_name", "")
                a_pub   = a_data.get("published", "")[:10]
                dk = f"{a_title}|{a_src}|{a_pub}"
                if dk in seen_keys:
                    continue
                seen_keys.add(dk)
                meta = " / ".join(filter(None, [html_escape(a_src), a_pub]))
                items.append(
                    f'<a href="../article/{aid}.html" class="wr-ref">'
                    f'<span class="wr-ref-title">→ {html_escape(a_title)}</span>'
                    f'<span class="wr-ref-meta">{meta}</span></a>'
                )
            else:
                if aid in seen_keys:
                    continue
                seen_keys.add(aid)
                items.append(
                    f'<a href="../article/{aid}.html" class="wr-ref">'
                    f'<span class="wr-ref-title">[{aid[:8]}]</span></a>'
                )

        n = len(items)
        if n == 0:
            refs_html = ""
        elif n <= 3:
            refs_html = f'<div class="wr-refs wr-refs-open">{"".join(items)}</div>'
        else:
            list_id    = f"wr-refs-{i}"
            scroll_sty = ' style="max-height:280px;overflow-y:auto"' if n >= 10 else ""
            refs_html  = (
                f'<button class="wr-toggle" aria-expanded="false" '
                f'aria-controls="{list_id}">関連ニュース {n}件を表示</button>'
                f'<div class="wr-refs" id="{list_id}" hidden{scroll_sty}>{"".join(items)}</div>'
            )

        topics_html += (
            f'<div class="wr-topic">'
            f'<div class="wr-topic-title">{html_escape(title)}</div>'
            f'<div class="wr-topic-summary">{html_escape(summary)}</div>'
            f'{refs_html}</div>'
        )
    if not topics_html:
        topics_html = '<p style="font-size:12px;color:#566473">データなし</p>'

    # 6階層トレンド HTML
    layers_html = ""
    for l in layer_trends:
        lname  = l.get("layer_name", "")
        ltext  = l.get("trend_text", "")
        lcolor = LAYER_COLORS_WEEKLY.get(lname, "#245d86")
        layers_html += (
            f'<div style="display:flex;gap:12px;padding:10px 0;'
            f'border-bottom:1px solid #d9dfe5;align-items:flex-start">'
            f'<div style="min-width:90px;font-size:11px;font-weight:700;'
            f'color:{lcolor};padding-top:2px;flex-shrink:0">{html_escape(lname)}</div>'
            f'<div style="font-size:13px;color:#566473;line-height:1.65">{html_escape(ltext)}</div></div>'
        )
    if not layers_html:
        layers_html = '<p style="font-size:12px;color:#566473">データなし</p>'

    # キーワード変動 HTML
    kw_html = ""
    kw_changes = [k for k in kw_changes if not _is_noise_kw(k.get("keyword", ""))]
    if kw_changes:
        max_abs = max((abs(k.get("change", 0)) for k in kw_changes), default=1)
        for k in kw_changes[:8]:
            kw      = k.get("keyword", "")
            this_w  = k.get("this_week_count", 0)
            last_w  = k.get("last_week_count", 0)
            change  = k.get("change", 0)
            bar_pct = round(abs(change) / max(max_abs, 1) * 100)
            pct_abs = abs(round(change / max(last_w, 1) * 100))
            color   = "#E24B4A" if change > 0 else "#566473"
            sign    = "+" if change >= 0 else ""
            kw_html += (
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
                f'<div style="width:80px;font-size:11px;color:#202830;white-space:nowrap;'
                f'overflow:hidden;text-overflow:ellipsis">{html_escape(kw)}</div>'
                f'<div style="flex:1;height:5px;background:#d9dfe5;border-radius:3px;overflow:hidden">'
                f'<div style="width:{bar_pct}%;height:100%;background:{color};border-radius:3px"></div></div>'
                f'<div style="font-size:10px;color:{color};width:55px;text-align:right">'
                f'{sign}{change}件({sign}{pct_abs}%)</div>'
                f'<div style="font-size:10px;color:#566473;width:40px;text-align:right">'
                f'今週{this_w}件</div></div>'
            )
    else:
        kw_html = '<p style="font-size:12px;color:#566473">先週比データがまだありません</p>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>週次レポート {pss}〜{pes} | Cyber Defense Notes</title>
<meta name="description" content="Cyber Defense Notes 週次レポート（{pss}〜{pes}）。{total}件の記事を分析したSOC/CDC設計実務者向けダイジェスト。">
<meta property="og:title" content="Cyber Defense Notes 週次レポート {pss}〜{pes}">
<meta property="og:description" content="{html_escape(exec_sum[:120])}">
<meta property="og:url" content="{site_url}">
<meta property="og:type" content="article">
<meta property="og:image" content="https://ayudle.github.io/ai-security-news/og-image.png">
<link rel="canonical" href="{site_url}">
<link rel="icon" type="image/png" href="../favicon.png">
<style>
:root{{--bg:#ffffff;--text:#202830;--dim:#566473;--border:#d9dfe5;--accent:#245d86;--card:#f6f7f8}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);line-height:1.7}}
header{{border-bottom:1px solid var(--border);padding:16px 24px;display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}}
.logo{{font-size:18px;font-weight:700}}
.back{{display:inline-block;padding:8px 16px;margin:16px 24px;color:var(--accent);text-decoration:none;font-size:13px}}
.back:hover{{text-decoration:underline}}
.wp{{max-width:720px;margin:0 auto;padding:16px 24px 60px}}
.wp-head{{border-bottom:1px solid var(--border);padding-bottom:20px;margin-bottom:24px}}
.wp-period{{font-size:12px;color:var(--dim);margin-bottom:6px}}
.wp-title{{font-size:22px;font-weight:700;color:#202830;line-height:1.4}}
.wp-meta{{font-size:11px;color:var(--dim);margin-top:8px}}
.sec{{margin-bottom:32px}}
.sec-title{{font-size:11px;font-weight:700;letter-spacing:.1em;color:var(--dim);text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)}}
.actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:24px}}
.btn{{display:inline-block;padding:10px 16px;border-radius:4px;text-decoration:none;font-size:13px;font-weight:500;cursor:pointer;border:none;font-family:inherit;background:var(--card);color:var(--text);border:1px solid var(--border)}}
.btn:hover{{border-color:var(--accent)}}
footer{{text-align:center;font-size:10px;color:var(--dim);padding:20px;border-top:1px solid var(--border);margin-top:16px}}
.wr-topic{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:10px}}
.wr-topic-title{{font-size:14px;font-weight:600;color:#202830;margin-bottom:6px}}
.wr-topic-summary{{font-size:13px;color:#566473;line-height:1.7;margin-bottom:4px}}
.wr-toggle{{display:inline-block;margin-top:10px;padding:5px 10px;background:none;border:1px solid var(--border);border-radius:6px;color:var(--accent);font-size:12px;cursor:pointer;font-family:inherit}}
.wr-toggle:hover{{border-color:var(--accent)}}
.wr-toggle:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.wr-refs{{margin-top:8px}}
.wr-refs-open{{margin-top:10px}}
.wr-ref{{display:block;text-decoration:none;padding:5px 0;border-top:1px solid #d9dfe5}}
.wr-ref-title{{font-size:12px;color:#245d86}}
.wr-ref-meta{{font-size:10px;color:#566473;margin-left:8px}}
</style>
{ga_snippet()}
</head>
<body>
<header>
  <a href="/ai-security-news/" style="text-decoration:none;color:inherit">
    <div class="logo">Cyber Defense Notes</div>
  </a>
</header>

<a href="/ai-security-news/#weekly" class="back">← 週次レポート一覧に戻る</a>

<nav style="padding:8px 24px 10px;border-bottom:1px solid #d9dfe5;display:flex;flex-wrap:wrap;gap:16px;font-size:12px">
  <a href="/ai-security-news/#today"   style="color:#245d86;text-decoration:none">本日のニュース</a>
  <a href="/ai-security-news/#trend"   style="color:#245d86;text-decoration:none">攻撃・インシデント動向</a>
  <a href="/ai-security-news/#archive" style="color:#245d86;text-decoration:none">記事検索</a>
  <a href="/ai-security-news/#weekly"  style="color:#245d86;text-decoration:none">週次レポート一覧</a>
</nav>

<div class="wp">
  <div class="wp-head">
    <div class="wp-period">週次レポート</div>
    <h1 class="wp-title">週次ダイジェスト</h1>
    <div class="wp-meta">{pss}〜{pes}（{total}件の記事を分析）</div>
  </div>

  <section class="sec">
    <h3 class="sec-title">エグゼクティブサマリー</h3>
    <div style="background:#f2f6fa;border-left:3px solid #245d86;padding:14px 18px;border-radius:4px;font-size:14px;line-height:1.85;color:#202830">{html_escape(exec_sum)}</div>
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
    <div style="background:#f2f6fa;border-left:3px solid #245d8655;padding:14px 18px;border-radius:4px;font-size:14px;line-height:1.85;color:#475361">{html_escape(next_week)}</div>
  </section>

  <div class="actions">
    <button onclick="navigator.clipboard.writeText('{site_url}').then(function(){{alert('URLをコピーしました')}})" class="btn">URLをコピー</button>
  </div>
</div>

<footer>
  各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載しています。<br>
  日本語要約・タグ・示唆はLLMにより自動生成されており、誤りや不正確な情報を含む可能性があります。重要な判断には必ず元記事をご確認ください。<br>
  <p style="margin-top:4px">Powered by Gemini API + GitHub Actions</p>
</footer>
<script>
document.querySelectorAll('.wr-toggle').forEach(function(btn){{
  btn.addEventListener('click',function(){{
    var expanded=btn.getAttribute('aria-expanded')==='true';
    var list=document.getElementById(btn.getAttribute('aria-controls'));
    expanded=!expanded;
    btn.setAttribute('aria-expanded',expanded?'true':'false');
    list.hidden=!expanded;
    btn.textContent=btn.textContent.replace(
      expanded?'を表示':'を非表示',
      expanded?'を非表示':'を表示'
    );
  }});
}});
</script>
</body>
</html>"""


def main():
    if not os.path.exists(DATA_PATH):
        print(f"[ERROR] {DATA_PATH} なし"); return
    with open(DATA_PATH,"r",encoding="utf-8") as f:
        data = json.load(f)
    weekly_list = load_weekly_list()
    columns = load_columns()
    os.makedirs("docs", exist_ok=True)
    with open(OUT_PATH,"w",encoding="utf-8") as f:
        f.write(build_html(data, weekly_list, columns))
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
        html = build_article_page(a, unique_articles, taxonomy, columns=columns)
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
    article_lookup = {a["id"]: a for a in unique_articles if a.get("id")}
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
            f.write(build_weekly_html(wd, article_lookup))
    print(f'週次レポート: {len(weekly_list)}件')

    # コラムページ生成
    os.makedirs("docs/columns", exist_ok=True)
    for col in columns:
        cslug = col.get('slug','')
        if not cslug:
            continue
        col_html = build_column_page(col, all_articles=unique_articles, all_columns=columns)
        with open(f"docs/columns/{cslug}.html", "w", encoding="utf-8") as f:
            f.write(col_html)
    print(f'コラム: {len(columns)}件')

    # sitemap.xml 生成
    site_url = 'https://ayudle.github.io/ai-security-news'
    sitemap_urls = [
        {'loc': f'{site_url}/', 'priority': '1.0', 'changefreq': 'daily'},
    ]
    # コラム（著者執筆の独自コンテンツ・最優先）
    for col in columns:
        cslug = col.get('slug','')
        cdate = col.get('date','')
        if cslug:
            sitemap_urls.append({
                'loc': f'{site_url}/columns/{cslug}.html',
                'priority': '0.9',
                'changefreq': 'monthly',
                'lastmod': cdate,
            })
    # 週次レポート
    for w in weekly_list:
        wpe = w.get("period", {}).get("end", "")
        if wpe:
            sitemap_urls.append({
                'loc': f'{site_url}/weekly/{w["date"]}.html',
                'priority': '0.8',
                'changefreq': 'monthly',
                'lastmod': wpe,
            })
    # 個別記事ページ
    for a in unique_articles:
        aid = a.get('id')
        pub = a.get('published', '')[:10]
        if aid:
            sitemap_urls.append({
                'loc': f'{site_url}/article/{aid}.html',
                'priority': '0.7',
                'changefreq': 'weekly',
                'lastmod': pub
            })
    # 日別アーカイブ
    for day in data.get('history', []):
        d = day.get('date', '')
        if d:
            sitemap_urls.append({
                'loc': f'{site_url}/archive/{d}.html',
                'priority': '0.5',
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

    # 保存済みの古いHTMLも共通テーマへ移行する。記事とURLは保持する。
    for path in glob.glob('docs/**/*.html', recursive=True):
        with open(path, encoding='utf-8') as f:
            page = f.read()
        href = 'assets/site.css' if path == 'docs/index.html' else '../assets/site.css'
        link = f'<link rel="stylesheet" href="{href}">'
        if link not in page:
            page = page.replace('</head>', link + '\n</head>')
        page = '\n'.join(line.rstrip() for line in page.split('\n'))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(page)

if __name__ == "__main__":
    main()
