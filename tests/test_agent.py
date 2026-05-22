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

        self.assertTrue(result.flagged_for_review)
        self.assertIn("mock", (result.equivalent_text or "").lower())

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

