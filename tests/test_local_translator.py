from __future__ import annotations

import unittest

from api.config import get_settings
from api.local_translator import MockLocalTranslator


class MockLocalTranslatorTests(unittest.TestCase):
    def test_exact_term_returns_reference_meaning(self) -> None:
        translator = MockLocalTranslator(get_settings().reference_dataset_path)
        result = translator.translate("skill issue")
        self.assertTrue(result.used_mock)
        self.assertIn("lack of ability", result.normal.lower())

    def test_unknown_text_still_returns_stub_output(self) -> None:
        translator = MockLocalTranslator(get_settings().reference_dataset_path)
        result = translator.translate("plain sentence")
        self.assertTrue(result.used_mock)
        self.assertEqual(result.normal, "plain sentence")
        self.assertNotIn("mock", result.normal.lower())
        self.assertNotIn("fallback", result.normal.lower())
        self.assertNotIn("offline translation", result.normal.lower())
