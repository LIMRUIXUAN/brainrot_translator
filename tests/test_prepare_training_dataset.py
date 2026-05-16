import unittest

import pandas as pd

from scripts.prepare_training_dataset import (
    PreparedExample,
    build_hf_examples,
    prepare_examples_from_dataframe,
    recommend_dataset_strategy,
    sample_hf_examples_for_final_dataset,
)


class PrepareTrainingDatasetTests(unittest.TestCase):
    def test_local_glossary_rows_become_term_definitions(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"brainrot": "GOAT", "normal": "greatest of all time"},
                {"brainrot": "bestie", "normal": "best friend"},
            ]
        )

        prepared, rejected = prepare_examples_from_dataframe(
            dataframe,
            source_group="local_glossary",
            source_builder=lambda _: "local_glossary:test",
            local_glossary_mode=True,
        )

        self.assertFalse(rejected)
        self.assertEqual(len(prepared), 2)
        self.assertTrue(all(example.task_type == "term_definition" for example in prepared))
        self.assertTrue(prepared[0].input_text.startswith("Define this brainrot term in normal English: "))
        self.assertIn("means", prepared[0].target_text)

    def test_local_glossary_aliases_are_split_into_separate_terms(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"brainrot": "zaza, za", "normal": "slang for cannabis"},
                {"brainrot": "bruh/bru", "normal": "bro"},
            ]
        )

        prepared, rejected = prepare_examples_from_dataframe(
            dataframe,
            source_group="local_glossary",
            source_builder=lambda _: "local_glossary:test",
            local_glossary_mode=True,
        )

        self.assertFalse(rejected)
        prepared_inputs = {example.input_text for example in prepared}
        self.assertIn("Define this brainrot term in normal English: zaza", prepared_inputs)
        self.assertIn("Define this brainrot term in normal English: za", prepared_inputs)
        self.assertIn("Define this brainrot term in normal English: bruh", prepared_inputs)
        self.assertIn("Define this brainrot term in normal English: bru", prepared_inputs)

    def test_sensitive_local_definition_is_rejected_for_manual_review(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "zesty",
                    "normal": "flamboyant, effeminate, or otherwise using the stereotypical mannerisms of a gay man",
                }
            ]
        )

        prepared, rejected = prepare_examples_from_dataframe(
            dataframe,
            source_group="local_glossary",
            source_builder=lambda _: "local_glossary:test",
            local_glossary_mode=True,
        )

        self.assertFalse(prepared)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].reason, "sensitive_definition_manual_review")

    def test_hf_sources_below_keep_rate_are_excluded(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "text": "bro this recipe ate fr",
                    "standard_text": "This recipe was excellent.",
                    "source_dataset": "good/source",
                },
                {
                    "text": "nah this movie cooked me",
                    "standard_text": "This movie overwhelmed me.",
                    "source_dataset": "good/source",
                },
                {
                    "text": "he got that glitch aura rn",
                    "standard_text": "He seems off right now.",
                    "source_dataset": "good/source",
                },
                {
                    "text": "mood is busted beyond repair",
                    "standard_text": "In all honesty, everything came together remarkably well.",
                    "source_dataset": "bad/source",
                },
                {
                    "text": "brain.exe said nope",
                    "standard_text": "From what I can tell, this was quite remarkable.",
                    "source_dataset": "bad/source",
                },
                {
                    "text": "bro folded under pressure",
                    "standard_text": "He struggled under pressure.",
                    "source_dataset": "bad/source",
                },
            ]
        )

        accepted, rejected, summaries = build_hf_examples(
            dataframe,
            min_keep_rate=0.90,
            min_clean_rows=1,
        )

        accepted_sources = {example.source_group for example in accepted}
        self.assertEqual(accepted_sources, {"hf_parallel::good/source"})
        self.assertTrue(any(example.reason == "source_excluded_low_keep_rate" for example in rejected))

        summary_lookup = {summary.source_group: summary for summary in summaries}
        self.assertTrue(summary_lookup["hf_parallel::good/source"].accepted)
        self.assertFalse(summary_lookup["hf_parallel::bad/source"].accepted)

    def test_recommendation_and_sampling_prefer_minimum_hf_needed(self) -> None:
        local_examples = [
            PreparedExample(
                input_text=f"Define this brainrot term in normal English: term-{index}",
                target_text=f"Term-{index} means something.",
                task_type="term_definition",
                source="local_glossary:test",
                quality_label="repaired",
                reason="repaired_term_definition",
                raw_input=f"term-{index}",
                raw_target="something",
                row_index=index,
                score=100,
                source_group="local_glossary",
            )
            for index in range(175)
        ]
        hf_examples = [
            PreparedExample(
                input_text=f"Convert brainrot English to normal English: example-{index}",
                target_text=f"Normal sentence {index}.",
                task_type="sentence_translation",
                source="hf_parallel:test/source",
                quality_label="keep",
                reason="kept_sentence_translation",
                raw_input=f"example-{index}",
                raw_target=f"Normal sentence {index}.",
                row_index=index,
                score=120,
                source_group="hf_parallel::test/source",
            )
            for index in range(1200)
        ]

        recommendation = recommend_dataset_strategy(local_examples, hf_examples)
        sampled, notes = sample_hf_examples_for_final_dataset(hf_examples, local_count=175, random_seed=42)

        self.assertEqual(recommendation.strategy, "Use combined dataset")
        self.assertEqual(len(sampled), 825)
        self.assertTrue(any("reach 1000 total rows" in note for note in notes))


if __name__ == "__main__":
    unittest.main()
