import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.export_slang_terms_pairs import build_pairs


class ExportSlangTermsPairsTests(unittest.TestCase):
    def test_bar_variants_are_split_with_shared_meaning(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "term": "bar(s)",
                    "meaning": 'A lyric in a rap song that is considered excellent. A talented rapper may be said to "drop bars" or be "spitting bars", sometimes shortened to just "spitting".',
                }
            ]
        )

        pairs, summary = build_pairs(dataframe)

        self.assertEqual(summary["output_rows"], 4)
        self.assertEqual(
            pairs["brainrot"].tolist(),
            ["bar(s)", "drop bars", "spitting", "spitting bars"],
        )
        self.assertTrue((pairs["normal"] == "a lyric in a rap song that is considered excellent").all())

    def test_based_prefers_direct_meaning_over_origin_story(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "term": "based",
                    "meaning": 'Originated from rapper Lil B The BasedGod, who defined it as "...being yourself." More contemporary use has been to express approval of someone or agreeing with another\'s opinion. Similar to W.',
                }
            ]
        )

        pairs, _ = build_pairs(dataframe)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs.iloc[0]["brainrot"], "based")
        self.assertEqual(pairs.iloc[0]["normal"], "approval of someone or agreement with another's opinion")

    def test_phrase_variant_is_extracted_from_term_definition(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "term": "cook (verb)",
                    "meaning": 'To "cook" is to perform or do well. Often used in the phrase "let him cook".',
                }
            ]
        )

        pairs, _ = build_pairs(dataframe)

        self.assertEqual(pairs["brainrot"].tolist(), ["cook", "let him cook"])
        self.assertTrue((pairs["normal"] == "to perform or do well").all())

    def test_multi_sense_row_is_skipped(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "term": "bop",
                    "meaning": '(1) A derogatory term. (2) An exceptionally good song. (3) An acronym for "baddie on point".',
                }
            ]
        )

        pairs, summary = build_pairs(dataframe)

        self.assertTrue(pairs.empty)
        self.assertEqual(summary["skipped_multi_sense_or_unusable"], 1)

    def test_short_for_meaning_stays_gloss_not_origin(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "term": "finna",
                    "meaning": 'Short for "I am going to" or "I am about to". The term has its roots in Southern American English, where "fixing to" has been used to mean "getting ready to" since the 18th century. Often used interchangeably with "gonna".',
                }
            ]
        )

        pairs, _ = build_pairs(dataframe)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs.iloc[0]["brainrot"], "finna")
        self.assertEqual(pairs.iloc[0]["normal"], "going to or about to")

    def test_acronym_expansion_is_not_added_as_variant(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "term": "iykyk",
                    "meaning": 'Acronym for "If you know, you know". Used to describe inside jokes and niche references',
                }
            ]
        )

        pairs, _ = build_pairs(dataframe)

        self.assertEqual(pairs["brainrot"].tolist(), ["iykyk"])


if __name__ == "__main__":
    unittest.main()
