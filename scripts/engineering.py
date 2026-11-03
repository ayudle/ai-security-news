"""診断技術・評価研究の候補をタイトルと抜粋から保守的に分類する。"""
import html
import re


TOPICS = (
    "診断ハーネス",
    "診断性能の評価",
    "修正・再診断の評価",
    "生成コードの安全性評価",
    "評価基盤・データセット",
)


def _text(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value or ""))).lower()


def _has(text, pattern):
    return bool(re.search(pattern, text, re.I))


def engineering_topics(title, summary):
    """単独の AI・評価・ハーネス語では採用しない。対象と方法の共起を要求する。"""
    text = _text(title) + " " + _text(summary)
    security = _has(text, r"vulnerab|security|pentest|penetration test|sast|dast|cwe[- ]?\d|脆弱性|診断|セキュリティ")
    diagnosis = _has(text, r"vulnerab(?:ility|ilities) (?:detect|scan|assess)|security (?:scan|test|assess)|static analysis|dynamic analysis|dynamic application security|black.box (?:security )?test|web application security test|api security test|sast|dast|pentest|penetration test|fuzz(?:ing|er)|脆弱性(?:検出|診断)|ソースコード診断|動的診断|ブラックボックス診断")
    evaluation = _has(text, r"evaluat|benchmark|accurac|precision|recall|false positive|false negative|ground truth|metric|coverage|reproducib|held.out|validat|性能|評価|精度|誤検知|見逃し|再現性|ベンチマーク|検証")
    repair_workflow = _has(text, r"patch (?:generat|correct|validat|evaluat|test)|automated program repair|vulnerability repair|security fix|remediation (?:generat|validat|evaluat)|retest|regression test|修正(?:案|コード|方針|検証|評価)|パッチ(?:生成|検証|評価)|自動修正|再診断")
    generated_code = _has(text, r"(?:ai|llm)[- ]generated code|generated code|code generation|生成コード|コード生成|自動生成コード")
    benchmark = _has(text, r"benchmark|dataset|ground truth|held.out|test set|canar(?:y|ies)|ベンチマーク|データセット|正解データ")

    found = []
    if diagnosis and _has(text, r"harness|scaffold|orchestrat|ハーネス"):
        found.append(TOPICS[0])
    if diagnosis and evaluation:
        found.append(TOPICS[1])
    if security and repair_workflow and _has(text, r"evaluat|validat|correct|functional|regress|retest|replay|検証|評価|正し|機能維持|回帰|再診断"):
        found.append(TOPICS[2])
    if security and generated_code and evaluation:
        found.append(TOPICS[3])
    if security and (diagnosis or generated_code or repair_workflow) and benchmark and evaluation:
        found.append(TOPICS[4])
    return found


def engineering_score(title, summary):
    topics = engineering_topics(title, summary)
    if not topics:
        return 0
    # タイトルに方法・評価対象がある記事を優先。日次の上限は変えない。
    title_signal = bool(engineering_topics(title, ""))
    return min(8, 4 + len(topics) + (2 if title_signal else 0))
