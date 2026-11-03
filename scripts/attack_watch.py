"""根拠付きの攻撃・インシデント動向。既存記事は推測で補完しない。"""
from datetime import datetime, timedelta, timezone
from html import escape
from collections import defaultdict
from business import ATTACK_LAYERS, normalize_attack, normalize_metadata

STATUSES = {"実被害確認", "悪用確認", "複数機関が観測", "PoCのみ", "研究報告のみ"}
RANK = {"実被害確認": 5, "悪用確認": 4, "複数機関が観測": 3, "PoCのみ": 2, "研究報告のみ": 1}
SERVICES = ["ブラックボックス診断", "Web診断", "API診断", "クラウド診断", "ソースコード診断", "SAST", "SCA", "シークレット検出", "モバイル診断", "AIエージェント評価", "ペネトレーションテスト"]

def val(value):
    return escape(str(value or "不明"))

def joined(values):
    return val("、".join(values) if values else "不明")

def link(item):
    return f'<a href="article/{val(item["id"])}.html">{val(item["title"])}</a>'

def render(history, safe_id):
    """直近14日の収集範囲だけを表示。古いレコードは未評価として除外。"""
    cutoff = datetime.now(timezone(timedelta(hours=9))).date() - timedelta(days=13)
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
            aid = safe_id(article.get("id", ""))
            if not aid or not isinstance(article.get("attack"), dict):
                continue
            attack = normalize_attack(article["attack"])
            if attack["evidence_status"] not in STATUSES:
                continue
            cve_key = tuple(attack["cve_ids"])
            identity = cve_key if cve_key else (article.get("url") or aid,)
            if identity in seen:
                continue
            seen.add(identity)
            business = normalize_metadata(article.get("business"))
            rows.append({"id": aid, "title": article.get("title_ja") or article.get("title", ""),
                         "date": day.get("date", ""), "source": article.get("source_name", ""),
                         "attack": attack, "business": business})
    rows.sort(key=lambda r: (RANK[r["attack"]["evidence_status"]], r["business"]["urgency"] == "緊急", r["business"]["japan_relevance"] == "直接関連", r["date"]), reverse=True)
    out = ['<div class="pane" id="pane-trend"><h2 class="watch-title">攻撃・インシデント動向</h2>',
           '<p class="watch-intro">収集範囲内の直近14日で確認できた情報です。市場全体の攻撃件数や流行を示すものではありません。事実と検討課題を分けて記載します。</p>']
    out.append('<section class="watch-section"><h3>現在確認されている攻撃・インシデント</h3>')
    if rows:
        for r in rows[:12]:
            a, b = r["attack"], r["business"]
            out.append('<article class="watch-item">'
                       f'<p class="watch-meta">{val(r["date"])} · {val(r["source"])} · {val(a["evidence_status"])}</p>'
                       f'<h4>{link(r)}</h4>'
                       f'<dl class="watch-facts"><div><dt>対象</dt><dd>{joined(a["target_layers"])} / {joined(b["products"])}</dd></div>'
                       f'<div><dt>攻撃・弱点</dt><dd>{joined(a["attack_methods"])} / {joined(a["weaknesses"])} / {joined(a["cve_ids"])}</dd></div>'
                       f'<div><dt>侵入経路</dt><dd>{val(a["initial_access"])}</dd></div>'
                       f'<div><dt>影響・国内</dt><dd>{val(a["observed_impact"])} / {val(a["japan_observation"])}</dd></div></dl>'
                       f'<p class="watch-source">根拠: {val(a["source_evidence"])}</p></article>')
    else:
        out.append('<p class="watch-empty">根拠付きで分類できた記事はまだありません。新しい日次更新から情報を蓄積します。過去記事は未評価です。</p>')
    out.append('</section><section class="watch-section"><h3>攻撃手法 × 対象レイヤー</h3>')
    by_layer = defaultdict(list)
    for r in rows:
        for layer in r["attack"]["target_layers"]:
            by_layer[layer].append(r)
    for layer in ATTACK_LAYERS:
        matches = by_layer.get(layer, [])[:3]
        if not matches:
            continue
        out.append(f'<div class="watch-layer"><h4>{val(layer)}</h4><ul>')
        for r in matches:
            a = r["attack"]
            out.append(f'<li>{link(r)}<span>攻撃: {joined(a["attack_methods"])} / 前提: {val(a["assessment_preconditions"])} / 弱点: {joined(a["weaknesses"])}</span></li>')
        out.append('</ul></div>')
    if not by_layer:
        out.append('<p class="watch-empty">対象レイヤーを根拠付きで分類できる記事はまだありません。</p>')
    out.append('</section><section class="watch-section"><h3>今後警戒する攻撃</h3><p class="watch-note">以下は確認済み事実からの検討課題です。発生を予測・断定するものではありません。</p>')
    candidates = [r for r in rows if r["attack"]["evidence_status"] in {"悪用確認", "PoCのみ"}]
    for r in candidates[:4]:
        a = r["attack"]
        out.append(f'<div class="watch-item"><h4>{link(r)}</h4><p>警戒対象: {joined(a["target_layers"])}に対する{joined(a["attack_methods"])}。期間・確度: 判断材料不足。日本への関連: {val(r["business"]["japan_relevance"])}。</p><p class="watch-source">根拠: {val(a["source_evidence"])} / 不明点: 今後の発生規模・時期</p></div>')
    if not candidates:
        out.append('<p class="watch-empty">予測に使える悪用確認・PoC情報がまだありません。</p>')
    out.append('</section><section class="watch-section"><h3>診断サービスへの示唆</h3>')
    service_rows = [r for r in rows if r["attack"]["service_implication"] != "不明"]
    for r in service_rows[:6]:
        a = r["attack"]
        out.append(f'<div class="watch-item"><h4>{link(r)}</h4><p>{val(a["service_implication"])}</p><p class="watch-source">関連診断: {joined(r["business"]["assessments"])} / 検証前提: {val(a["assessment_preconditions"])}</p></div>')
    if not service_rows:
        out.append('<p class="watch-empty">根拠付きの診断サービスへの示唆は蓄積中です。</p>')
    out.append('</section><section class="watch-section"><h3>LLM活用型ブラックボックス診断の検証候補</h3>')
    scenarios = [r for r in rows if r["attack"]["test_scenario"] != "不明"]
    for r in scenarios[:5]:
        a = r["attack"]
        out.append(f'<div class="watch-item"><h4>{link(r)}</h4><p>検証候補: {val(a["test_scenario"])}</p><p class="watch-source">適性: {val(a["blackbox_testability"])} / 人による確認: {val(a["human_validation"])}</p></div>')
    if not scenarios:
        out.append('<p class="watch-empty">根拠付きの検証候補は蓄積中です。</p>')
    out.append('</section><section class="watch-section"><h3>情報収集の不足領域</h3><p class="watch-note">掲載がない領域でも、攻撃やリスクが存在しないことを意味しません。</p><ul class="watch-gaps">')
    covered = {s for r in rows for s in r["business"]["assessments"]}
    for service in SERVICES:
        if service not in covered:
            out.append(f'<li>{val(service)}</li>')
    if len(covered) >= len(SERVICES):
        out.append('<li>この期間の診断領域には記事があります。情報源の偏りは継続確認が必要です。</li>')
    out.append('</ul></section></div>')
    return ''.join(out)
