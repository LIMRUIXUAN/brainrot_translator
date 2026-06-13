from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from api.agent import BrainrotAgent
from api.config import get_settings


class BrainrotAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.agent = BrainrotAgent(get_settings())

    def test_reference_block_uses_local_slang_terms(self) -> None:
        block = self.agent.build_reference_block().lower()
        self.assertIn("skill issue", block)
        self.assertIn("ratio", block)
        self.assertIn("skibidi", block)

    async def test_highlight_timeout_uses_text_fallback(self) -> None:
        with patch.object(
            self.agent,
            "_execute_openrouter_call",
            AsyncMock(side_effect=httpx.TimeoutException("timed out")),
        ):
            result = await self.agent.analyze_highlighted_text("skill issue")

        self.assertTrue(result.is_brainrot)
        self.assertTrue(result.flagged_for_review)
        equivalent = (result.equivalent_text or "").lower()
        self.assertIn("possible meaning", equivalent)
        self.assertNotIn("mock", equivalent)
        self.assertNotIn("fallback", equivalent)

    async def test_non_brainrot_model_result_keeps_original_text(self) -> None:
        selected_text = "The meeting starts at 9 AM."
        model_payload = {
            "is_brainrot": False,
            "brainrot_text": None,
            "equivalent_text": "The scheduled meeting begins at nine in the morning.",
            "formal_explanation": "",
            "sentiment_label": "neutral",
            "sentiment_rationale": "Plain scheduling sentence.",
            "confidence_score": 0.92,
            "flagged_for_review": False,
            "model_used": "nvidia/nemotron-3.5-content-safety:free",
        }

        with patch.object(
            self.agent,
            "_execute_openrouter_call",
            AsyncMock(return_value=model_payload),
        ):
            result = await self.agent.analyze_highlighted_text(selected_text)

        self.assertFalse(result.is_brainrot)
        self.assertEqual(result.equivalent_text, selected_text)
        self.assertIn("No brainrot", result.formal_explanation or "")

    async def test_text_model_tier_selects_free_or_premium_model(self) -> None:
        calls = []

        async def fake_openrouter_call(*, payload, timeout_seconds, openrouter_api_key):
            calls.append((payload["model"], timeout_seconds))
            return {
                "is_brainrot": True,
                "brainrot_text": "he has rizz",
                "equivalent_text": "He has charisma.",
                "formal_explanation": "Rizz means charisma.",
                "sentiment_label": "positive",
                "sentiment_rationale": "Complimentary.",
                "confidence_score": 0.9,
                "flagged_for_review": False,
                "model_used": "",
            }

        with patch.object(self.agent, "_execute_openrouter_call", fake_openrouter_call):
            free = await self.agent.analyze_highlighted_text(
                "he has rizz",
                text_model_tier="free",
                openrouter_api_key="user-key",
            )
            premium = await self.agent.analyze_highlighted_text(
                "he has rizz",
                text_model_tier="premium",
                openrouter_api_key="user-key",
            )

        self.assertEqual(free.model_used, self.agent.settings.openrouter_text_free_model)
        self.assertEqual(premium.model_used, self.agent.settings.openrouter_text_premium_model)
        self.assertEqual(calls[0], (self.agent.settings.openrouter_text_free_model, 90.0))
        self.assertEqual(calls[1], (self.agent.settings.openrouter_text_premium_model, 30.0))

    async def test_image_timeout_returns_safe_fallback(self) -> None:
        with patch.object(
            self.agent,
            "_execute_openrouter_call",
            AsyncMock(side_effect=httpx.TimeoutException("timed out")),
        ):
            result = await self.agent.analyze_screenshot_media(
                image_base64="ZmFrZQ==",
                media_type="image/png",
                source_url="https://example.com/meme.png",
            )

        self.assertFalse(result.is_brainrot)
        self.assertTrue(result.flagged_for_review)
        self.assertEqual(result.confidence_score, 0.0)

