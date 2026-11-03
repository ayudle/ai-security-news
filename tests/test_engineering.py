import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from engineering import engineering_topics
from engineering_watch import render


class EngineeringFocusTest(unittest.TestCase):
    def test_examples_and_irrelevant_news(self):
        examples = [
            ("The Harness Is the Hard Part of Agentic Pentesting",
             "The harness controls scope, credentials and replayable proof in web-app penetration testing.",
             "診断ハーネス"),
            ("MetaVul: Agentic Harness Discovery for Vulnerability Detection",
             "Evaluator feedback improves pairwise vulnerability detection accuracy on a held-out set.",
             "診断性能の評価"),
            ("RiskyPy: Joint Security and Functionality Evaluation of LLM-Generated Code",
             "A benchmark uses functionality and vulnerability canaries to assess code generation.",
             "生成コードの安全性評価"),
            ("How Safe Are AI-Generated Patches?",
             "Security evaluation of automated program repair examines vulnerabilities introduced by patches.",
             "修正・再診断の評価"),
            ("Evaluating Agentic Black-Box Security Testing for Web APIs",
             "A dynamic application security testing benchmark measures false positives and replayable findings.",
             "診断性能の評価"),
        ]
        for title, abstract, expected in examples:
            with self.subTest(title=title):
                self.assertIn(expected, engineering_topics(title, abstract))
        self.assertEqual([], engineering_topics(
            "Enterprise suffers ransomware attack", "Security patches are available."))
        self.assertEqual([], engineering_topics(
            "AI coding assistant release", "New general-purpose agent features are available."))

    def test_renderer_escapes_article_input(self):
        article = {"id": "good-id", "title": "<img src=x onerror=alert(1)> vulnerability detection benchmark",
                   "summary": "Security testing accuracy and false positives.",
                   "title_ja": "<script>alert(1)</script>",
                   "summary_ja": "<b>unsafe</b>", "source_name": "<source>",
                   "engineering_topics": ["診断性能の評価"]}
        today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
        output = render([{"date": today, "articles": [article]}], lambda value: value)
        self.assertNotIn("<script>", output)
        self.assertNotIn("<b>unsafe</b>", output)
        self.assertIn("&lt;script&gt;", output)
        self.assertIn("&lt;source&gt;", output)


if __name__ == "__main__":
    unittest.main()
