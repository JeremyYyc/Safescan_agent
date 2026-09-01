import unittest

from app.workflow.pdf_graph import normalize, render


class PdfWorkflowTests(unittest.TestCase):
    def test_pdf_normalization_is_deterministic_and_does_not_require_a_model(self):
        original = {"title": "Fixture", "regions": []}

        result = normalize({"report": original})

        self.assertEqual(result["report"]["title"], "Fixture")
        self.assertEqual(result["report"]["regions"], [])
        self.assertEqual(result["report"]["recommendations"], {})
        self.assertEqual(original, {"title": "Fixture", "regions": []})

    def test_normalized_report_renders_to_pdf_bytes(self):
        report = normalize({"report": {"title": "Fixture", "regions": []}})["report"]

        result = render({"report": report})

        self.assertTrue(result["pdf_bytes"].startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
