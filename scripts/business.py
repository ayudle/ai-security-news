"""業務向け収集ルールと、根拠付き記事メタデータの契約。API呼び出しなし。"""
import re

FOCUS = {
    "脆弱性管理": ["vulnerability", "vulnerabilities", "cve", "cvss", "epss", "kev", "exploit", "patch", "zero-day", "脆弱性", "修正", "緩和策", "再診断", "パッチ", "exposure management"],
    "診断サービス": ["sast", "dast", "sca", "source code", "code scanning", "secret scanning", "penetration test", "pentest", "black box", "application security", "api security", "診断", "ソースコード", "シークレット検出"],
    "AIエージェント": ["prompt injection", "agentic", "ai agent", "mcp", "model context protocol", "security for ai", "ai for security", "llm security", "プロンプトインジェクション", "aiエージェント"],
    "企業インシデント": ["ransomware", "data breach", "credential theft", "cyberattack", "intrusion", "supply chain attack", "情報漏洩", "情報漏えい", "不正アクセス", "サイバー攻撃", "ランサムウェア", "個人情報流出"],
    "政策・地政学": ["nation-state", "state-sponsored", "espionage", "cyber policy", "cybersecurity regulation", "economic security", "経済安全保障", "国家支援", "サイバー政策", "能動的サイバー防御", "セキュリティ市場"],
}
LIFECYCLE = ["発見", "評価・優先順位付け", "診断", "修正・緩和", "再診断", "継続管理", "不明"]
ASSESSMENTS = ["ソースコード診断", "SAST", "SCA", "シークレット検出", "ブラックボックス診断", "DAST", "Web診断", "API診断", "クラウド診断", "モバイル診断", "ペネトレーションテスト", "AIエージェント評価", "不明"]
ENUMS = {
    "japan_relevance": ["直接関連", "関連あり", "不明"],
    "exploitation": ["悪用確認あり", "PoC公開のみ", "悪用未確認と明記", "不明"],
    "urgency": ["緊急", "早期評価", "情報収集", "不明"],
}

def matches(text, word):
    # 短い英字語は部分一致させない（SCA / MCP等の誤検知防止）。
    if word.isascii() and word.isalpha() and len(word) <= 4:
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text))
    return word in text

def relevance(title, summary, source):
    text = (title + " " + summary).lower()
    topics = [name for name, words in FOCUS.items() if any(matches(text, w) for w in words)]
    domestic = source.get("region") == "JP"
    score = len(topics) * 3 + (2 if domestic and topics else 0) + (1 if source.get("tier") == "A" and topics else 0)
    return topics, score

def metadata_schema():
    props = {key: {"type": "string", "enum": values} for key, values in ENUMS.items()}
    props.update({
        "products": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "lifecycle": {"type": "array", "items": {"type": "string", "enum": LIFECYCLE}, "maxItems": 3},
        "assessments": {"type": "array", "items": {"type": "string", "enum": ASSESSMENTS}, "maxItems": 4},
        "evidence": {"type": "string", "description": "提供された記事抜粋から根拠を短く記述。根拠がなければ不明"},
    })
    return {"type": "object", "properties": props, "required": list(props)}

def normalize_metadata(raw):
    raw = raw if isinstance(raw, dict) else {}
    out = {key: raw.get(key) if raw.get(key) in values else "不明" for key, values in ENUMS.items()}
    for key, allowed, limit in [("lifecycle", LIFECYCLE, 3), ("assessments", ASSESSMENTS, 4)]:
        values = raw.get(key, [])
        out[key] = list(dict.fromkeys(v for v in values if isinstance(v, str) and v in allowed))[:limit] if isinstance(values, list) else []
        out[key] = out[key] or ["不明"]
    products = raw.get("products", [])
    out["products"] = [p[:100] for p in products if isinstance(p, str) and p.strip()][:6] if isinstance(products, list) else []
    out["products"] = out["products"] or ["不明"]
    out["evidence"] = raw.get("evidence", "不明") if isinstance(raw.get("evidence"), str) else "不明"
    if not out["evidence"].strip() or out["evidence"] == "不明":
        return {**out, **{key: "不明" for key in ENUMS}, "products": ["不明"], "lifecycle": ["不明"], "assessments": ["不明"], "evidence": "不明"}
    return out
