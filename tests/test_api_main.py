from __future__ import annotations

import base64
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import api.main as api_main
from api import database
from api.main import app
from api.schemas import HighlightedTextAnalysisResponse, ImageAnalysisResponse, ReverseTranslateResponse


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
        self.assertIn("text_recheck_configured", payload)

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

    def test_reverse_translate_delegates_to_agent_when_local_model_unavailable(self) -> None:
        agent_mock = AsyncMock(
            return_value=ReverseTranslateResponse(
                reverse_text="bro got mad rizz",
                confidence_score=0.88,
                model_used="openrouter/test",
            )
        )

        with patch("api.main.get_model_components", return_value=None), \
             patch("api.main.agent.reverse_translate", agent_mock):
            response = self.client.post(
                "/api/v1/reverse-translate",
                json={"text": "He is very charming", "page_url": "sidepanel-direct-input"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["reverse_text"], "bro got mad rizz")
        self.assertEqual(payload["confidence_score"], 0.88)
        self.assertEqual(payload["model_used"], "openrouter/test")
        agent_mock.assert_awaited_once_with("He is very charming")

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
             patch("api.main.settings", replace(api_main.settings, low_confidence_threshold=0.7)), \
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

    def test_low_confidence_local_text_calls_openrouter_recheck(self) -> None:
        local_result = HighlightedTextAnalysisResponse(
            is_brainrot=True,
            brainrot_text="he has rizz",
            equivalent_text="He has rizz.",
            formal_explanation="Local model left slang in place.",
            sentiment_label="unclear",
            sentiment_rationale="Local model does not score sentiment.",
            confidence_score=0.45,
            flagged_for_review=True,
            model_used="local_transformer",
        )
        openrouter_result = HighlightedTextAnalysisResponse(
            is_brainrot=True,
            brainrot_text="he has rizz",
            equivalent_text="He has strong charisma.",
            formal_explanation="Rizz means charisma or romantic appeal.",
            sentiment_label="positive",
            sentiment_rationale="It praises social charm.",
            confidence_score=0.88,
            flagged_for_review=False,
            model_used="deepseek/deepseek-v4-flash",
        )
        agent_mock = AsyncMock(return_value=openrouter_result)

        with patch("api.main._try_slang_json_lookup", return_value=None), \
             patch("api.main._try_local_model_text_analysis", return_value=local_result), \
             patch("api.main.settings", replace(api_main.settings, low_confidence_threshold=0.7)), \
             patch("api.main.save_cached_text", return_value=True), \
             patch("api.main.agent.analyze_highlighted_text", agent_mock):
                response = self.client.post(
                    "/api/v1/analyze-highlighted-text",
                    json={"selected_text": "he has rizz"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["model_used"], "deepseek/deepseek-v4-flash")
        self.assertEqual(payload["equivalent_text"], "He has strong charisma.")
        agent_mock.assert_awaited_once()

    def test_manual_recheck_endpoint_bypasses_local_and_cache(self) -> None:
        openrouter_result = HighlightedTextAnalysisResponse(
            is_brainrot=True,
            brainrot_text="skill issue",
            equivalent_text="This is a problem caused by lack of ability.",
            formal_explanation="The phrase mocks competence.",
            sentiment_label="negative",
            sentiment_rationale="It blames the target.",
            confidence_score=0.91,
            flagged_for_review=False,
            model_used="deepseek/deepseek-v4-flash",
        )
        agent_mock = AsyncMock(return_value=openrouter_result)

        with patch("api.main._try_slang_json_lookup") as slang_mock, \
             patch("api.main._try_local_model_text_analysis") as local_mock, \
             patch("api.main._try_db_text_lookup") as db_mock, \
             patch("api.main.save_cached_text", return_value=True), \
             patch("api.main.agent.analyze_highlighted_text", agent_mock):
                response = self.client.post(
                    "/api/v1/recheck-highlighted-text",
                    json={
                        "selected_text": "skill issue",
                        "page_url": "https://example.com",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model_used"], "deepseek/deepseek-v4-flash")
        agent_mock.assert_awaited_once()
        slang_mock.assert_not_called()
        local_mock.assert_not_called()
        db_mock.assert_not_called()

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
             patch("api.main.settings", replace(api_main.settings, low_confidence_threshold=0.7)), \
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

    def test_image_route_does_not_update_text_frequency(self) -> None:
        mocked_result = ImageAnalysisResponse(
            is_brainrot=True,
            brainrot_meaning="skill issue",
            equivalent_text="This is the recipient's fault.",
            formal_explanation="The meme frames the problem as incompetence.",
            confidence_score=0.91,
            flagged_for_review=False,
            model_used="google/gemini-3-flash-preview",
            used_frame_fallback=False,
        )

        with patch("api.main._try_db_image_lookup", return_value=None), \
             patch("api.main.save_cached_image", return_value=True), \
             patch("api.main.agent.analyze_screenshot_media", AsyncMock(return_value=mocked_result)), \
             patch("api.main.increment_word_frequencies") as frequency_mock:
                response = self.client.post(
                    "/api/v1/analyze-screenshot-media",
                    json={
                        "image_base64": base64.b64encode(b"fake-image").decode("ascii"),
                        "media_type": "image/png",
                        "source_url": "https://example.com/skill-issue.png",
                    },
                )

        self.assertEqual(response.status_code, 200)
        frequency_mock.assert_not_called()

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

    def test_dashboard_word_frequency_endpoint_returns_items(self) -> None:
        with patch(
            "api.main.list_word_frequencies",
            return_value=[
                {"term": "rizz", "count": 3, "last_seen_at": "2026-05-22T00:00:00+00:00"},
                {"term": "skill issue", "count": 2, "last_seen_at": None},
            ],
        ) as list_mock:
            response = self.client.get("/api/v1/dashboard/word-frequency?limit=200")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["term"], "rizz")
        list_mock.assert_called_once_with(100)

    def test_text_cache_save_upserts_existing_lookup_key(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        database.Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

        first = {
            "is_brainrot": True,
            "brainrot_text": "skill issue",
            "equivalent_text": "You lack ability.",
            "formal_explanation": "Initial local result.",
            "sentiment_label": "negative",
            "sentiment_rationale": "Dismissive.",
            "confidence_score": 0.42,
            "model_used": "local_transformer",
        }
        second = {
            **first,
            "equivalent_text": "The problem is being blamed on lack of ability.",
            "confidence_score": 0.92,
            "model_used": "deepseek/deepseek-v4-flash",
        }

        with patch("api.database.get_session_factory", return_value=session_factory):
            self.assertTrue(database.save_cached_text("skill issue", first))
            self.assertTrue(database.save_cached_text("skill issue", second))
            cached = database.lookup_cached_text("skill issue")

        self.assertIsNotNone(cached)
        self.assertEqual(cached["equivalent_text"], second["equivalent_text"])
        self.assertEqual(cached["confidence_score"], 0.92)
        self.assertEqual(cached["model_used"], "deepseek/deepseek-v4-flash")

    def test_expired_cache_rows_are_deleted_on_lookup(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        database.Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
        expired_at = datetime.now(timezone.utc) - timedelta(hours=2)

        text_result = {
            "is_brainrot": True,
            "brainrot_text": "rizz",
            "equivalent_text": "charisma",
            "formal_explanation": "Rizz means charisma.",
            "sentiment_label": "positive",
            "sentiment_rationale": "Complimentary.",
            "confidence_score": 0.91,
            "model_used": "test",
        }
        image_result = {
            "is_brainrot": True,
            "brainrot_meaning": "ratio",
            "equivalent_text": "public rejection",
            "formal_explanation": "Ratio means social pushback.",
            "confidence_score": 0.88,
            "model_used": "test",
            "used_frame_fallback": False,
        }

        ttl_settings = replace(database.get_settings(), cache_ttl_hours=1)
        with patch("api.database.get_session_factory", return_value=session_factory), \
             patch("api.database.get_settings", return_value=ttl_settings):
            self.assertTrue(database.save_cached_text("rizz", text_result))
            self.assertTrue(database.save_cached_image("a" * 64, image_result))
            with session_factory() as session:
                text_row = session.query(database.CachedTextTranslation).first()
                image_row = session.query(database.CachedImageAnalysis).first()
                text_row.created_at = expired_at
                image_row.created_at = expired_at
                session.commit()

            self.assertIsNone(database.lookup_cached_text("rizz"))
            self.assertIsNone(database.lookup_cached_image("a" * 64))
            with session_factory() as session:
                self.assertEqual(session.query(database.CachedTextTranslation).count(), 0)
                self.assertEqual(session.query(database.CachedImageAnalysis).count(), 0)

    def test_word_frequency_helpers_increment_and_sort(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        database.Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

        with patch("api.database.get_session_factory", return_value=session_factory):
            self.assertTrue(database.increment_word_frequencies({"rizz": "rizz"}))
            self.assertTrue(
                database.increment_word_frequencies(
                    {"rizz": "rizz", "skill issue": "skill issue"},
                    page_url="https://example.com",
                )
            )
            items = database.list_word_frequencies(limit=10)

        self.assertEqual(items[0]["term"], "rizz")
        self.assertEqual(items[0]["count"], 2)
        self.assertEqual(items[1]["term"], "skill issue")
        self.assertEqual(items[1]["count"], 1)
