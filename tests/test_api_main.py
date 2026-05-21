from __future__ import annotations

import base64
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.main import app
from api.schemas import HighlightedTextAnalysisResponse, ImageAnalysisResponse


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("openrouter_configured", payload)
        self.assertIn("local_text_model_available", payload)
        self.assertIn("local_text_model_loaded", payload)
        self.assertIn("local_quality_classifier_available", payload)
        self.assertIn("local_quality_classifier_loaded", payload)
        self.assertIn("database_configured", payload)

    def test_translate_requires_text_field(self) -> None:
        response = self.client.post("/translate", json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Missing 'text' field."})

    def test_translate_uses_mock_fallback_when_model_is_unavailable(self) -> None:
        with patch("api.main.get_model_components", return_value=None):
            response = self.client.post("/translate", json={"text": "skill issue"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["used_mock"])
        self.assertIn("lack of ability", payload["normal"].lower())

    def test_translate_uses_local_transformer_when_model_is_available(self) -> None:
        class FakeTokenizer:
            def __call__(self, text, **kwargs):
                self.prompt = text
                return {"input_ids": [[1, 2, 3]]}

            def decode(self, output, skip_special_tokens=True):
                return "This means the person lacks ability."

        class FakeModel:
            def generate(self, **kwargs):
                self.kwargs = kwargs
                return [[4, 5, 6]]

        tokenizer = FakeTokenizer()
        model = FakeModel()

        with patch("api.main.get_model_components", return_value=(tokenizer, model)):
            response = self.client.post("/translate", json={"text": "skill issue"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["used_mock"])
        self.assertEqual(payload["model_source"], "local_transformer")
        self.assertEqual(payload["normal"], "This means the person lacks ability.")
        self.assertIn("Convert brainrot English to normal English", tokenizer.prompt)
        self.assertEqual(model.kwargs["num_beams"], 4)
        self.assertFalse(model.kwargs["do_sample"])

    def test_highlighted_text_route_stages_low_confidence_review(self) -> None:
        mocked_result = HighlightedTextAnalysisResponse(
            is_brainrot=True,
            brainrot_text="skill issue",
            equivalent_text="This is your fault.",
            formal_explanation="The phrase blames the target's competence.",
            sentiment_label="negative",
            sentiment_rationale="It is dismissive and mocking.",
            confidence_score=0.52,
            flagged_for_review=False,
            model_used="deepseek/deepseek-v4-flash",
        )

        with patch("api.main._try_slang_json_lookup", return_value=None), \
             patch("api.main._try_db_text_lookup", return_value=None), \
             patch("api.main._try_local_model_text_analysis", return_value=None), \
             patch("api.main.save_cached_text", return_value=True), \
             patch("api.main.agent.analyze_highlighted_text", AsyncMock(return_value=mocked_result)), \
             patch("api.main.flag_text_for_review") as flag_mock:
                response = self.client.post(
                    "/api/v1/analyze-highlighted-text",
                    json={
                        "selected_text": "skill issue",
                        "page_url": "https://example.com",
                        "surrounding_text": "some context"
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["flagged_for_review"])
        flag_mock.assert_called_once()

    def test_highlighted_text_route_prefers_local_model_when_available(self) -> None:
        class FakeTokenizer:
            def __call__(self, text, **kwargs):
                return {"input_ids": [[1, 2, 3]]}

            def decode(self, output, skip_special_tokens=True):
                return "This sentence means the speaker has strong charisma."

        class FakeModel:
            def generate(self, **kwargs):
                return [[4, 5, 6]]

        agent_mock = AsyncMock()

        with patch("api.main._try_slang_json_lookup", return_value=None), \
             patch("api.main._try_db_text_lookup", return_value=None), \
             patch("api.main.get_model_components", return_value=(FakeTokenizer(), FakeModel())), \
             patch("api.main.get_quality_classifier_components", return_value=None), \
             patch("api.main.save_cached_text", return_value=True), \
             patch("api.main.agent.analyze_highlighted_text", agent_mock):
                response = self.client.post(
                    "/api/v1/analyze-highlighted-text",
                    json={"selected_text": "he has rizz"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["is_brainrot"])
        self.assertEqual(payload["model_used"], "local_transformer")
        self.assertIn("strong charisma", payload["equivalent_text"])
        self.assertEqual(payload["confidence_score"], 0.78)
        agent_mock.assert_not_called()

    def test_highlighted_text_route_uses_quality_classifier_confidence_when_available(self) -> None:
        import torch

        class FakeTranslationTokenizer:
            def __call__(self, text, **kwargs):
                return {"input_ids": [[1, 2, 3]]}

            def decode(self, output, skip_special_tokens=True):
                return "He has charm or romantic appeal."

        class FakeTranslationModel:
            def generate(self, **kwargs):
                return [[4, 5, 6]]

        class FakeQualityTokenizer:
            def __call__(self, text, **kwargs):
                self.text = text
                return {"input_ids": torch.tensor([[1, 2, 3]])}

        class FakeQualityModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.tensor(0.0))

            def forward(self, **kwargs):
                return type("Output", (), {"logits": torch.tensor([[0.1, 2.3]])})

        quality_tokenizer = FakeQualityTokenizer()

        with patch("api.main._try_slang_json_lookup", return_value=None), \
             patch("api.main.get_model_components", return_value=(FakeTranslationTokenizer(), FakeTranslationModel())), \
             patch("api.main.get_quality_classifier_components", return_value=(quality_tokenizer, FakeQualityModel())), \
             patch("api.main.save_cached_text", return_value=True):
                response = self.client.post(
                    "/api/v1/analyze-highlighted-text",
                    json={"selected_text": "he has rizz"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["model_used"], "local_transformer+quality_classifier")
        self.assertGreater(payload["confidence_score"], 0.89)
        self.assertIn("Source brainrot text: he has rizz", quality_tokenizer.text)

    def test_quality_classifier_confidence_is_capped_when_slang_leaks(self) -> None:
        import torch

        class FakeQualityTokenizer:
            def __call__(self, text, **kwargs):
                return {"input_ids": torch.tensor([[1, 2, 3]])}

        class FakeQualityModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.tensor(0.0))

            def forward(self, **kwargs):
                return type("Output", (), {"logits": torch.tensor([[0.1, 2.3]])})

        with patch("api.main.get_quality_classifier_components", return_value=(FakeQualityTokenizer(), FakeQualityModel())):
            from api.main import _score_translation_quality

            score, used_classifier = _score_translation_quality(
                "he has rizz",
                "He has rizz.",
                changed=True,
            )

        self.assertTrue(used_classifier)
        self.assertLessEqual(score, 0.45)

    def test_highlighted_text_route_leaves_plain_text_unchanged(self) -> None:
        plain_text = (
            "Description copied from interface: Map If the specified key is not already "
            "associated with a value, associates it with the given value."
        )
        agent_mock = AsyncMock()

        with patch("api.main._try_slang_json_lookup", return_value=None), \
             patch("api.main._try_db_text_lookup", return_value=None), \
             patch("api.main.save_cached_text", return_value=True), \
             patch("api.main.agent.analyze_highlighted_text", agent_mock):
                response = self.client.post(
                    "/api/v1/analyze-highlighted-text",
                    json={"selected_text": plain_text},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["is_brainrot"])
        self.assertEqual(payload["equivalent_text"], plain_text)
        self.assertEqual(payload["model_used"], "local_slang_filter")
        agent_mock.assert_not_called()

    def test_highlighted_text_cleans_surviving_slang_from_local_model_output(self) -> None:
        class FakeTokenizer:
            def __call__(self, text, **kwargs):
                return {"input_ids": [[1, 2, 3]]}

            def decode(self, output, skip_special_tokens=True):
                return (
                    "Drop another -100 aura for getting caught slipping when the "
                    "professor pulls up the source code."
                )

        class FakeModel:
            def generate(self, **kwargs):
                return [[4, 5, 6]]

        with patch("api.main._try_slang_json_lookup", return_value=None), \
             patch("api.main.get_model_components", return_value=(FakeTokenizer(), FakeModel())), \
             patch("api.main.get_quality_classifier_components", return_value=None), \
             patch("api.main.save_cached_text", return_value=True):
                response = self.client.post(
                    "/api/v1/analyze-highlighted-text",
                    json={
                        "selected_text": (
                            "Drop another -100 aura for getting caught slipping "
                            "when the professor pulls up the source code."
                        )
                    },
                )

        self.assertEqual(response.status_code, 200)
        equivalent = response.json()["equivalent_text"]
        self.assertIn("100 social reputation points", equivalent)
        self.assertIn("being caught making a mistake", equivalent)
        self.assertNotIn("caught slipping", equivalent.lower())

    def test_rejects_invalid_base64_payload(self) -> None:
        response = self.client.post(
            "/api/v1/analyze-screenshot-media",
            json={
                "image_base64": "%%%not-base64%%%",
                "media_type": "image/png",
                "source_url": "https://example.com/meme.png",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("base64", response.json()["detail"])

    def test_rejects_payloads_larger_than_five_mb(self) -> None:
        payload = base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode("ascii")
        response = self.client.post(
            "/api/v1/analyze-screenshot-media",
            json={
                "image_base64": payload,
                "media_type": "image/png",
                "source_url": "https://example.com/meme.png",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("5MB", response.json()["detail"])

    def test_low_confidence_image_results_are_staged_for_review(self) -> None:
        mocked_result = ImageAnalysisResponse(
            is_brainrot=True,
            brainrot_meaning="skill issue",
            equivalent_text="This is the recipient's fault.",
            formal_explanation="The meme frames the problem as self-inflicted incompetence.",
            confidence_score=0.52,
            flagged_for_review=False,
            model_used="google/gemini-3-flash-preview",
            used_frame_fallback=False,
        )

        with patch("api.main._try_db_image_lookup", return_value=None), \
             patch("api.main.save_cached_image", return_value=True), \
             patch("api.main.agent.analyze_screenshot_media", AsyncMock(return_value=mocked_result)), \
             patch("api.main.flag_image_for_review") as flag_mock:
                response = self.client.post(
                    "/api/v1/analyze-screenshot-media",
                    json={
                        "image_base64": base64.b64encode(b"fake-image").decode("ascii"),
                        "media_type": "image/png",
                        "source_url": "https://example.com/skill-issue.png",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["flagged_for_review"])
        flag_mock.assert_called_once()

    def test_analyze_image_alias_uses_same_response_shape(self) -> None:
        mocked_result = ImageAnalysisResponse(
            is_brainrot=True,
            brainrot_meaning="ratio",
            equivalent_text="Your point is being socially rejected.",
            formal_explanation="The meme signals collective public disapproval and social defeat.",
            confidence_score=0.91,
            flagged_for_review=False,
            model_used="google/gemini-3-flash-preview",
            used_frame_fallback=True,
        )

        with patch("api.main.agent.analyze_screenshot_media", AsyncMock(return_value=mocked_result)):
            response = self.client.post(
                "/api/v1/analyze-image",
                json={
                    "image_base64": base64.b64encode(b"fake-image").decode("ascii"),
                    "media_type": "image/gif",
                    "source_url": "https://example.com/ratio.gif",
                    "frame0_base64": base64.b64encode(b"frame-zero").decode("ascii"),
                    "frame0_media_type": "image/jpeg",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["used_frame_fallback"])
