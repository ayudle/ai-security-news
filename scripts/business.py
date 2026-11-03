"""業務向け収集ルールと、根拠付き記事メタデータの契約。API呼び出しなし。"""
import re
from engineering import engineering_topics, engineering_score

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
ATTACK_LAYERS = ["外部公開資産", "デバイス・エンドポイント", "認証・ID", "インフラ・ネットワーク", "クラウド・コンテナ", "Web・API", "ソースコード・ソフトウェア供給網", "データ・AI・AIエージェント"]
EVIDENCE_STATUS = ["実被害確認", "悪用確認", "複数機関が観測", "PoCのみ", "研究報告のみ", "不明"]
TESTABILITY = ["適性あり", "条件付き", "他の診断方式が必要", "判断材料不足"]

def attack_schema():
    strings = ["initial_access", "observed_impact", "japan_observation", "assessment_preconditions", "test_scenario", "human_validation", "service_implication", "source_evidence"]
    props = {k: {"type": "string"} for k in strings}
    props.update({
        "evidence_status": {"type": "string", "enum": EVIDENCE_STATUS},
        "target_layers": {"type": "array", "items": {"type": "string", "enum": ATTACK_LAYERS}, "maxItems": 2},
        "attack_methods": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "weaknesses": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "cve_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "blackbox_testability": {"type": "string", "enum": TESTABILITY},
    })
    return {"type": "object", "properties": props, "required": list(props)}

def normalize_attack(raw):
    raw = raw if isinstance(raw, dict) else {}
    out = {k: str(raw.get(k, "不明"))[:300] if isinstance(raw.get(k), str) and raw.get(k, "").strip() else "不明" for k in ["initial_access", "observed_impact", "japan_observation", "assessment_preconditions", "test_scenario", "human_validation", "service_implication", "source_evidence"]}
    out["evidence_status"] = raw.get("evidence_status") if raw.get("evidence_status") in EVIDENCE_STATUS else "不明"
    out["blackbox_testability"] = raw.get("blackbox_testability") if raw.get("blackbox_testability") in TESTABILITY else "判断材料不足"
    for key, limit in [("target_layers", 2), ("attack_methods", 3), ("weaknesses", 3), ("cve_ids", 4)]:
        values = raw.get(key)
        out[key] = [v[:100] for v in values if isinstance(v, str) and v.strip()][:limit] if isinstance(values, list) else []
    out["target_layers"] = [v for v in out["target_layers"] if v in ATTACK_LAYERS]
    out["cve_ids"] = [v for v in out["cve_ids"] if re.fullmatch(r"CVE-\d{4}-\d{4,}", v, re.I)]
    if out["source_evidence"] == "不明":
        out["evidence_status"] = "不明"
        out["blackbox_testability"] = "判断材料不足"
    return out

def matches(text, word):
    # 短い英字語は部分一致させない（SCA / MCP等の誤検知防止）。
    if word.isascii() and word.isalpha() and len(word) <= 4:
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text))
    return word in text

def relevance(title, summary, source):
    text = (title + " " + summary).lower()
    topics = [name for name, words in FOCUS.items() if any(matches(text, w) for w in words)]
    technique_topics = engineering_topics(title, summary)
    if technique_topics:
        topics.append("診断技術・評価")
    domestic = source.get("region") == "JP"
    score = len(topics) * 3 + engineering_score(title, summary)
    score += (2 if domestic and topics else 0) + (1 if source.get("tier") == "A" and topics else 0)
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
