from __future__ import annotations

import base64
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import httpx

import api.main as api_main
from api.schemas import HighlightedTextAnalysisResponse, ImageAnalysisResponse


USER_OPENROUTER_HEADERS = {"X-OpenRouter-API-Key": "user-key"}


def _pipeline_settings():
    return replace(
        api_main.settings,
        low_confidence_threshold=0.7,
        rate_limit_analyze_text="1000/minute",
        rate_limit_analyze_media="1000/minute",
    )


class TranslationPipelineIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.settings_patch = patch("api.main.settings", _pipeline_settings())
        self.settings_patch.start()
        self.app = api_main.create_app()
        self.transport = httpx.ASGITransport(app=self.app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.settings_patch.stop()

    async def test_slang_terms_json_hit_does_not_call_openrouter(self) -> None:
        openrouter = AsyncMock()

        with patch("api.main.agent.analyze_highlighted_text", openrouter), \
             patch("api.main._try_db_text_lookup", return_value=None):
            response = await self.client.post(
                "/api/v1/analyze-highlighted-text",
                json={"selected_text": "rizz", "page_url": "https://example.test"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["model_used"], "local_cache_slang_json")
        self.assertIn("charisma", payload["equivalent_text"].lower())
        openrouter.assert_not_awaited()

    async def test_local_model_hit_returns_local_model_result(self) -> None:
        class FakeTokenizer:
            def __call__(self, text, **kwargs):
                return {"input_ids": [[1, 2, 3]]}

            def decode(self, output, skip_special_tokens=True):
                return "He has strong charisma."

        class FakeModel:
            def generate(self, **kwargs):
                return [[4, 5, 6]]

        openrouter = AsyncMock()

        with patch("api.main._try_slang_json_lookup", return_value=None), \
             patch("api.main.get_model_components", return_value=(FakeTokenizer(), FakeModel())), \
             patch("api.main.get_quality_classifier_components", return_value=None), \
             patch("api.main.agent.analyze_highlighted_text", openrouter):
            response = await self.client.post(
                "/api/v1/analyze-highlighted-text",
                json={"selected_text": "he has rizz"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["model_used"], "local_transformer")
        self.assertEqual(payload["equivalent_text"], "He has strong charisma.")
        openrouter.assert_not_awaited()

    async def test_unknown_text_is_not_persisted_to_raw_text_cache(self) -> None:
        openrouter_result = HighlightedTextAnalysisResponse(
            is_brainrot=True,
            brainrot_text="new slang",
            equivalent_text="A clear translation from OpenRouter.",
            formal_explanation="Live model analysis.",
            sentiment_label="neutral",
            sentiment_rationale="Neutral wording.",
            confidence_score=0.91,
            flagged_for_review=False,
            model_used="deepseek/deepseek-v4-flash",
        )
        openrouter = AsyncMock(return_value=openrouter_result)

        with patch("api.main._try_slang_json_lookup", return_value=None), \
             patch("api.main._try_local_model_text_analysis", return_value=None), \
             patch("api.main.lookup_cached_text", return_value=None), \
             patch("api.main.agent.analyze_highlighted_text", openrouter):
            first = await self.client.post(
                "/api/v1/analyze-highlighted-text",
                json={"selected_text": "new slang"},
                headers=USER_OPENROUTER_HEADERS,
            )
            second = await self.client.post(
                "/api/v1/analyze-highlighted-text",
                json={"selected_text": "new slang"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 401)
        self.assertEqual(first.json()["model_used"], "deepseek/deepseek-v4-flash")
        openrouter.assert_awaited_once()

    async def test_low_confidence_local_result_triggers_openrouter_fallback(self) -> None:
        local_result = HighlightedTextAnalysisResponse(
            is_brainrot=True,
            brainrot_text="he has rizz",
            equivalent_text="he has rizz",
            formal_explanation="Low confidence local result.",
            sentiment_label="unclear",
            sentiment_rationale="Unclear.",
            confidence_score=0.2,
            flagged_for_review=True,
            model_used="local_transformer",
        )
        openrouter_result = HighlightedTextAnalysisResponse(
            is_brainrot=True,
            brainrot_text="he has rizz",
            equivalent_text="He has strong charisma.",
            formal_explanation="Live model refreshed a weak local result.",
            sentiment_label="positive",
            sentiment_rationale="Complimentary phrase.",
            confidence_score=0.93,
            flagged_for_review=False,
            model_used="deepseek/deepseek-v4-flash",
        )
        openrouter = AsyncMock(return_value=openrouter_result)

        with patch("api.main._try_slang_json_lookup", return_value=None), \
             patch("api.main._try_local_model_text_analysis", return_value=local_result), \
             patch("api.main.agent.analyze_highlighted_text", openrouter):
            response = await self.client.post(
                "/api/v1/analyze-highlighted-text",
                json={"selected_text": "he has rizz"},
                headers=USER_OPENROUTER_HEADERS,
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["model_used"], "deepseek/deepseek-v4-flash")
        self.assertEqual(payload["equivalent_text"], "He has strong charisma.")
        openrouter.assert_awaited_once()

    async def test_image_hash_cache_hit_does_not_call_openrouter(self) -> None:
        cached_result = ImageAnalysisResponse(
            is_brainrot=True,
            brainrot_meaning="The meme blames failure on lack of skill.",
            equivalent_text="This is a problem caused by lack of ability.",
            formal_explanation="Cached image interpretation.",
            confidence_score=0.88,
            flagged_for_review=False,
            model_used="cached:google/nvidia/nemotron-3.5-content-safety:free",
            used_frame_fallback=False,
        )
        openrouter = AsyncMock()

        with patch("api.main._try_db_image_lookup", return_value=cached_result), \
             patch("api.main.agent.analyze_screenshot_media", openrouter), \
             patch("api.main.save_cached_image") as save_mock:
            response = await self.client.post(
                "/api/v1/analyze-screenshot-media",
                json={
                    "image_base64": base64.b64encode(b"fake-image").decode("ascii"),
                    "media_type": "image/png",
                    "source_url": "https://example.test/meme.png",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model_used"], "cached:google/nvidia/nemotron-3.5-content-safety:free")
        openrouter.assert_not_awaited()
        save_mock.assert_not_called()

    async def test_mock_glossary_fallback_output_hides_implementation_terms(self) -> None:
        with patch("api.main.get_model_components", return_value=None):
            response = await self.client.post("/translate", json={"text": "skill issue"})

        self.assertEqual(response.status_code, 200)
        user_visible_output = response.json()["normal"].lower()
        self.assertNotIn("mock", user_visible_output)
        self.assertNotIn("fallback", user_visible_output)
        self.assertNotIn("offline translation", user_visible_output)


if __name__ == "__main__":
    unittest.main()
