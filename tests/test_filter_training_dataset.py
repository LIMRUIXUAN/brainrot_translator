import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.filter_training_dataset import (
    DEFAULT_CLEANED_PATH,
    detect_text_columns,
    filter_training_dataframe,
    repair_term_definition,
    run_pipeline,
)


class FilterTrainingDatasetTests(unittest.TestCase):
    def test_detect_columns_prefers_standard_pair_columns(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"brainrot": "bro is cooked", "normal": "He is in trouble."},
                {"brainrot": "rizz", "normal": "Charisma or flirting ability."},
            ]
        )

        columns = detect_text_columns(dataframe)

        self.assertEqual(columns.input_column, "brainrot")
        self.assertEqual(columns.target_column, "normal")

    def test_term_definition_repair_keeps_origin_details(self) -> None:
        repaired_text, quality_label, reason = repair_term_definition(
            "six-seven (6-7)",
            'A nonsense word derived from the song "Doot Doot (6 7)" by Skrilla. Inspired multiple numerical meme variants. Originating from TikTok.',
        )

        self.assertEqual(quality_label, "repaired")
        self.assertEqual(reason, "repaired_term_definition_from_origin_notes")
        self.assertIn("Skrilla", repaired_text)
        self.assertIn("TikTok", repaired_text)
        self.assertIn("does not have a fixed literal meaning", repaired_text)
        self.assertNotIn("Inspired multiple", repaired_text)

    def test_phrase_definition_can_become_sentence_translation(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "You good?",
                    "normal": 'Derived from AAVE, this phrase is a short hand of the usual "Are you okay?" greeting.',
                }
            ]
        )

        cleaned, repaired, rejected, summary = filter_training_dataframe(dataframe)

        self.assertEqual(summary["cleaned_row_count"], 1)
        self.assertTrue(rejected.empty)
        self.assertEqual(cleaned.iloc[0]["task_type"], "sentence_translation")
        self.assertEqual(cleaned.iloc[0]["quality_label"], "repaired")
        self.assertEqual(cleaned.iloc[0]["target_text"], "Are you okay?")
        self.assertEqual(len(repaired), 1)

    def test_hallucinated_translation_is_rejected(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "He's financially cooked, joever for his wallet.",
                    "normal": "In all honesty, he's broke right now. The execution was notably poor. That level of quality is hard to come by.",
                }
            ]
        )

        cleaned, repaired, rejected, summary = filter_training_dataframe(dataframe)

        self.assertTrue(cleaned.empty)
        self.assertTrue(repaired.empty)
        self.assertEqual(summary["rejected_row_count"], 1)
        self.assertEqual(rejected.iloc[0]["reason"], "hallucinated_target")

    def test_plain_non_brainrot_row_is_rejected(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "Always on time!",
                    "normal": "I'm punctual.",
                }
            ]
        )

        cleaned, repaired, rejected, summary = filter_training_dataframe(dataframe)

        self.assertTrue(cleaned.empty)
        self.assertEqual(summary["rejected_row_count"], 1)
        self.assertEqual(rejected.iloc[0]["reason"], "input_not_brainrot_or_internet_style")

    def test_duplicate_rows_are_removed(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"brainrot": "rizz", "normal": "One's charm/ seduction skills. Derived from charisma."},
                {"brainrot": "rizz", "normal": "One's charm/ seduction skills. Derived from charisma."},
            ]
        )

        cleaned, repaired, rejected, summary = filter_training_dataframe(dataframe)

        self.assertEqual(summary["cleaned_row_count"], 1)
        self.assertEqual(summary["duplicate_count"], 1)
        self.assertEqual(summary["rejected_row_count"], 1)
        self.assertEqual(rejected.iloc[0]["reason"], "duplicate_exact_pair")

    def test_short_glossary_pair_becomes_term_definition(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "aura",
                    "normal": "An individual's current reputation or charisma. Cultivating aura is known as aura farming.",
                }
            ]
        )

        cleaned, repaired, rejected, summary = filter_training_dataframe(dataframe)

        self.assertEqual(summary["cleaned_row_count"], 1)
        self.assertTrue(rejected.empty)
        self.assertEqual(cleaned.iloc[0]["task_type"], "term_definition")
        self.assertTrue(cleaned.iloc[0]["target_text"].startswith("Aura"))

    def test_numbered_definition_becomes_term_definition(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "gyatt",
                    "normal": "1.) Someone's buttocks, specifically attractive ones 2.) Someone with large buttocks or an hourglass figure.",
                }
            ]
        )

        cleaned, repaired, rejected, summary = filter_training_dataframe(dataframe)

        self.assertEqual(summary["cleaned_row_count"], 1)
        self.assertTrue(rejected.empty)
        self.assertEqual(cleaned.iloc[0]["task_type"], "term_definition")
        self.assertNotIn("2.)", cleaned.iloc[0]["target_text"])
        self.assertIn("someone's buttocks", cleaned.iloc[0]["target_text"].lower())

    def test_cooked_definition_is_smoothed(self) -> None:
        repaired_text, quality_label, reason = repair_term_definition(
            "cooked (adjective)",
            'To "be cooked" is to be in trouble.',
        )

        self.assertEqual(quality_label, "repaired")
        self.assertEqual(reason, "repaired_term_definition")
        self.assertEqual(repaired_text, "Cooked (adjective) means to be in trouble.")

    def test_apostrophe_slang_sentence_is_kept(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "brainrot": "Chillin' with my squad tonight.",
                    "normal": "I'm going out with my friends tonight.",
                }
            ]
        )

        cleaned, repaired, rejected, summary = filter_training_dataframe(dataframe)

        self.assertEqual(summary["cleaned_row_count"], 1)
        self.assertTrue(rejected.empty)
        self.assertEqual(cleaned.iloc[0]["task_type"], "sentence_translation")

    def test_pipeline_writes_requested_files(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"brainrot": "rizz", "normal": "One's charm/ seduction skills. Derived from charisma."},
                {"brainrot": "bro keeps saying six-seven in class", "normal": "He keeps repeating the six-seven meme phrase in class."},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.csv"
            cleaned_path = temp_path / "cleaned.csv"
            repaired_path = temp_path / "repaired.csv"
            rejected_path = temp_path / "rejected.csv"
            dataframe.to_csv(input_path, index=False)

            cleaned, repaired, rejected, summary = run_pipeline(
                input_path=input_path,
                cleaned_path=cleaned_path,
                repaired_path=repaired_path,
                rejected_path=rejected_path,
            )

            self.assertTrue(cleaned_path.exists())
            self.assertTrue(repaired_path.exists())
            self.assertTrue(rejected_path.exists())
            self.assertEqual(summary["cleaned_row_count"], 2)
            self.assertEqual(cleaned.iloc[0]["quality_label"] in {"keep", "repaired"}, True)


if __name__ == "__main__":
    unittest.main()
