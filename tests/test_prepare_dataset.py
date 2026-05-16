import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.prepare_dataset import (
    PROJECT_ROOT,
    PreparationStats,
    apply_quality_filters,
    build_training_ready_dataset,
    clean_and_filter_pairs,
    clean_text,
    classify_invalid_pair,
    extract_pairs_from_dataframe,
    quality_score_pair,
    should_use_paired_columns,
    simplify_glossary_definition_for_training,
    write_dataset_csv,
)


class PrepareDatasetTests(unittest.TestCase):
    def test_clean_text_normalizes_quotes_and_spacing(self) -> None:
        raw_text = "  “bro   is cooked”  \n\n fr  "

        cleaned = clean_text(raw_text)

        self.assertEqual(cleaned, '"bro is cooked" fr')

    def test_duplicate_and_empty_rows_are_removed(self) -> None:
        raw_pairs = [
            {"brainrot": "bro is cooked fr", "normal": "He is in serious trouble."},
            {"brainrot": "bro is cooked fr", "normal": "He is in serious trouble."},
            {"brainrot": "", "normal": "Missing input."},
            {"brainrot": "https://example.com", "normal": "https://example.com"},
            {"brainrot": "!!!", "normal": "??"},
        ]

        cleaned = clean_and_filter_pairs(raw_pairs, stats=PreparationStats())

        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned.iloc[0]["brainrot"], "bro is cooked fr")
        self.assertEqual(cleaned.iloc[0]["normal"], "He is in serious trouble.")

    def test_metadata_like_source_column_is_not_used_when_term_and_meaning_exist(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "source": "Wikipedia - Glossary of 2020s slang",
                    "term": "rizz",
                    "meaning": "Charisma or flirting ability.",
                },
                {
                    "source": "Wikipedia - Glossary of 2020s slang",
                    "term": "no cap",
                    "meaning": "No lie or seriously.",
                },
            ]
        )

        should_use_pair = should_use_paired_columns(
            dataframe=dataframe,
            input_column="source",
            output_column="meaning",
            term_column="term",
            meaning_column="meaning",
        )

        self.assertFalse(should_use_pair)

    def test_glossary_examples_are_not_used_as_sentence_translation_pairs(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "term": "yeet",
                    "meaning": "Throw forcefully.",
                    "example": "He yeeted the ball across the yard.",
                }
            ]
        )

        extracted_pairs, _ = extract_pairs_from_dataframe(
            dataframe=dataframe,
            source_path=PROJECT_ROOT / "data" / "processed" / "slang_terms.csv",
            stats=PreparationStats(),
        )

        self.assertEqual(len(extracted_pairs), 1)
        self.assertEqual(extracted_pairs[0]["brainrot"], "yeet")
        self.assertEqual(extracted_pairs[0]["normal"], "Throw forcefully.")

    def test_final_csv_has_required_columns(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"brainrot": "this food is bussin", "normal": "This food is very delicious."},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "brainrot_dataset.csv"
            write_dataset_csv(dataframe, output_path)
            loaded = pd.read_csv(output_path)

        self.assertEqual(list(loaded.columns), ["brainrot", "normal"])

    def test_glossary_rows_keep_short_terms_and_long_definitions(self) -> None:
        raw_pairs = [
            {
                "brainrot": "L",
                "normal": 'Short for "loss," used to indicate failure.',
                "source_file": "data/processed/slang_terms.csv",
            },
            {
                "brainrot": "Roman Empire",
                "normal": "A" * 700,
                "source_file": "data/processed/slang_terms.csv",
            },
        ]

        cleaned = clean_and_filter_pairs(raw_pairs, stats=PreparationStats())

        self.assertEqual(len(cleaned), 2)
        self.assertEqual(classify_invalid_pair("L", 'Short for "loss," used to indicate failure.', "data/processed/slang_terms.csv"), None)

    def test_clean_text_removes_info_icon_marker(self) -> None:
        cleaned = clean_text("sksksk ⓘ")

        self.assertEqual(cleaned, "sksksk")

    def test_quality_score_flags_hallucination_filler(self) -> None:
        assessment = quality_score_pair(
            brainrot="Forgot sunscreen and got burnt, my skin is literally cooked.",
            normal="It's remarkable how i got sunburned after forgetting sunscreen. The overall quality was noticeably high, I certainly wasn't expecting that outcome.",
            strict=True,
        )

        self.assertLess(assessment.score, 100)
        self.assertTrue(any(reason.startswith("hallucination_phrase:") for reason in assessment.reasons))

    def test_quality_filter_flags_bad_pairs_and_keeps_glossary_rows(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "i am in disbelief at how hard i managed to flop villain origin story type beat no cap",
                    "normal": "It's remarkable how i was cleaning my room when I realized I forgot my keys definitely something worth recognizing.",
                    "source_file": "data/processed/huggingface_parallel_dataset.csv",
                },
                {
                    "brainrot": "L",
                    "normal": 'Short for "loss," used to indicate failure.',
                    "source_file": "data/processed/slang_terms.csv",
                },
            ]
        )

        cleaned, flagged = apply_quality_filters(dataframe, stats=PreparationStats(), strict=True)

        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned.iloc[0]["brainrot"], "L")
        self.assertEqual(len(flagged), 1)
        self.assertIn("hallucination_phrase", flagged.iloc[0]["reason_flagged"])

    def test_quality_filter_flags_invented_details_with_small_overlap(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "BRO i am literally DECEASED my dentist has me on the floor and i cannot recover fr fr",
                    "normal": "I was genuinely pleased to see that my dentist told a joke nobody laughed at the kind of thing that stays with you for a while.",
                    "source_file": "data/processed/huggingface_parallel_dataset.csv",
                }
            ]
        )

        cleaned, flagged = apply_quality_filters(dataframe, stats=PreparationStats(), strict=True)

        self.assertTrue(cleaned.empty)
        self.assertEqual(len(flagged), 1)
        self.assertIn("hallucination_phrase", flagged.iloc[0]["reason_flagged"])

    def test_quality_filter_flags_broken_fragment_input(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": ', "beautiful mid").',
                    "normal": "Average, mediocre, not bad or not special.",
                    "source_file": "data/processed/slang_terms.csv",
                }
            ]
        )

        cleaned, flagged = apply_quality_filters(dataframe, stats=PreparationStats(), strict=True)

        self.assertTrue(cleaned.empty)
        self.assertEqual(len(flagged), 1)
        self.assertIn("broken_fragment", flagged.iloc[0]["reason_flagged"])

    def test_quality_filter_flags_definition_substitution_artifacts(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "He yeeted the ball across the yard.",
                    "normal": "He throw forcefullyed the ball across the yard.",
                    "source_file": "data/processed/huggingface_parallel_dataset.csv",
                    "source_dataset": "projolx/genz_brainrot_dataset",
                },
                {
                    "brainrot": "Beyonce is such a mom.",
                    "normal": "Beyonce is such a a woman I deeply admire.",
                    "source_file": "data/processed/huggingface_parallel_dataset.csv",
                    "source_dataset": "projolx/genz_brainrot_dataset",
                },
            ]
        )

        cleaned, flagged = apply_quality_filters(dataframe, stats=PreparationStats(), strict=True)

        self.assertTrue(cleaned.empty)
        self.assertEqual(len(flagged), 2)
        self.assertTrue(flagged["reason_flagged"].str.contains("definition_substitution").all())

    def test_quality_filter_flags_missed_hallucination_template_variant(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "i am in disbelief at how hard my piano managed to flop villain origin story type beat no cap",
                    "normal": "It genuinely struck me that my piano teacher tried to open a jar and failed which was honestly quite remarkable.",
                    "source_file": "data/processed/huggingface_parallel_dataset.csv",
                }
            ]
        )

        cleaned, flagged = apply_quality_filters(dataframe, stats=PreparationStats(), strict=True)

        self.assertTrue(cleaned.empty)
        self.assertEqual(len(flagged), 1)
        self.assertIn("hallucination_phrase", flagged.iloc[0]["reason_flagged"])

    def test_quality_filter_keeps_valid_short_slang_term(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "rizz",
                    "normal": "Charisma or flirting ability.",
                    "source_file": "data/processed/slang_terms.csv",
                }
            ]
        )

        cleaned, flagged = apply_quality_filters(dataframe, stats=PreparationStats(), strict=True)

        self.assertEqual(len(cleaned), 1)
        self.assertTrue(flagged.empty)

    def test_quality_filter_keeps_compact_glossary_terms_with_symbols(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "L+Ratio",
                    "normal": "Insult used primarily online. Combined form of the L and ratio slang terms.",
                    "source_file": "data/processed/slang_terms.csv",
                },
                {
                    "brainrot": "pushing P",
                    "normal": "A phrase meaning acting with integrity and style while maintaining success.",
                    "source_file": "data/processed/slang_terms.csv",
                },
            ]
        )

        cleaned, flagged = apply_quality_filters(dataframe, stats=PreparationStats(), strict=True)

        self.assertEqual(len(cleaned), 2)
        self.assertTrue(flagged.empty)

    def test_quality_filter_keeps_valid_sentence_pair_from_noisy_source(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "he called the teacher mom in front of everyone big yikes moment",
                    "normal": "He called his teacher Mom in front of the whole class.",
                    "source_file": "data/processed/huggingface_parallel_dataset.csv",
                    "source_dataset": "projolx/genz_brainrot_dataset",
                }
            ]
        )

        cleaned, flagged = apply_quality_filters(dataframe, stats=PreparationStats(), strict=True)

        self.assertEqual(len(cleaned), 1)
        self.assertTrue(flagged.empty)

    def test_glossary_definition_is_rewritten_for_training(self) -> None:
        decision = simplify_glossary_definition_for_training(
            brainrot="Gucci",
            normal="Meaning good, cool, fashionable, or excellent. Used to express approval or satisfaction for something. Originated from the luxury brand Gucci.",
        )

        self.assertEqual(decision.action, "rewrite")
        self.assertEqual(decision.training_normal, "good, cool, fashionable, or excellent.")

    def test_glossary_definition_without_stable_meaning_is_dropped_for_training(self) -> None:
        decision = simplify_glossary_definition_for_training(
            brainrot="six-seven (6-7)",
            normal='A nonsense word derived from the song "Doot Doot (6 7)" by Skrilla. Inspired multiple numerical meme variants. Originating from TikTok.',
        )

        self.assertEqual(decision.action, "drop")
        self.assertEqual(decision.reason, "glossary_no_stable_translation")

    def test_training_ready_builder_drops_sentence_level_dictionary_targets(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "This pizza is bussin'!",
                    "normal": "This pizza is used to say something is good. primarily used to describe food!",
                    "source_file": "data/processed/huggingface_parallel_dataset.csv",
                    "source_dataset": "ethan00alphayehah/brainrot-dataset",
                },
                {
                    "brainrot": "rizz",
                    "normal": "Charisma or flirting ability.",
                    "source_file": "data/processed/slang_terms.csv",
                    "source_dataset": "",
                },
            ]
        )

        training_ready, review = build_training_ready_dataset(dataframe, stats=PreparationStats())

        self.assertEqual(len(training_ready), 1)
        self.assertEqual(training_ready.iloc[0]["brainrot"], "rizz")
        dropped_row = review.loc[review["brainrot"] == "This pizza is bussin'!"].iloc[0]
        self.assertEqual(dropped_row["action"], "drop")
        self.assertIn("definition_style_target", dropped_row["reason"])

    def test_training_ready_builder_keeps_valid_used_to_be_translation(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "bro had the ultimate glow up from awkward to confident king",
                    "normal": "He used to be so awkward but now he's really confident.",
                    "source_file": "data/processed/huggingface_parallel_dataset.csv",
                    "source_dataset": "ethan00alphayehah/brainrot-dataset",
                }
            ]
        )

        training_ready, review = build_training_ready_dataset(dataframe, stats=PreparationStats())

        self.assertEqual(len(training_ready), 1)
        reviewed_row = review.iloc[0]
        self.assertEqual(reviewed_row["action"], "keep")


if __name__ == "__main__":
    unittest.main()
