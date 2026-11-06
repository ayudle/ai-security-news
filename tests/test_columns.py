import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_site import build_column_page, md_to_html


class ColumnRenderingTest(unittest.TestCase):
    def test_paper_links_are_clickable_and_escaped(self):
        html = md_to_html(
            '[<PentestEval>](https://arxiv.org/html/2512.14233v2?x=1&y=2) '
            '[unsafe](javascript:alert(1)) <script>alert(1)</script>'
        )
        self.assertIn('href="https://arxiv.org/html/2512.14233v2?x=1&amp;y=2"', html)
        self.assertIn('&lt;PentestEval&gt;</a>', html)
        self.assertNotIn('href="javascript:', html)
        self.assertNotIn('<script>', html)

    def test_column_has_no_authorship_claim(self):
        column = {
            "title": "診断の評価", "date": "2026-11-06", "slug": "diagnosis-eval",
            "description": "考察", "tags": [], "body_md": "考察本文",
        }
        html = build_column_page(column)
        self.assertNotIn('著者執筆', html)
        self.assertNotIn('AI支援', html)
        self.assertNotIn('LLMによる自動生成ではありません', html)


if __name__ == "__main__":
    unittest.main()
