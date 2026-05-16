import unittest

import harvester


class HarvesterTransformTests(unittest.TestCase):
    def test_clean_text_removes_urls_emoji_and_normalizes_space(self) -> None:
        text = "hello   [world] https://example.com/path 😂\nfr"

        cleaned = harvester.clean_text(text, remove_brackets=True)

        self.assertEqual(cleaned, "hello world fr")

    def test_split_chunks_respects_max_chars(self) -> None:
        text = "First sentence. Second sentence is longer. Third sentence."

        chunks = harvester.split_chunks(text, max_chars=30)

        self.assertTrue(all(len(chunk) <= 30 for chunk in chunks))
        self.assertGreater(len(chunks), 1)

    def test_transform_all_deduplicates_cleaned_chunks(self) -> None:
        raw_items = [
            {
                "term": "rizz",
                "source": "urban_dict",
                "definition": "A very charismatic style of flirting.",
                "example": "They have rizz.",
                "raw_text": "Rizz means charisma. https://example.com",
            },
            {
                "term": "rizz",
                "source": "urban_dict",
                "definition": "A very charismatic style of flirting.",
                "example": "They have rizz.",
                "raw_text": "Rizz means charisma.",
            },
        ]

        transformed = harvester.transform_all(raw_items)

        self.assertEqual(len(transformed), 1)
        self.assertEqual(transformed[0]["raw_text"], "Rizz means charisma.")
        self.assertIn("embedding_id", transformed[0])
        self.assertIn("embed_text", transformed[0])

    def test_build_embed_text_formats_sources(self) -> None:
        reddit_text = harvester.build_embed_text(
            {"source": "reddit", "subreddit": "GenZ", "raw_text": "no cap this is wild"}
        )
        twitch_text = harvester.build_embed_text(
            {"source": "twitch", "channel": "xqc", "raw_text": "chat is cooked"}
        )

        self.assertEqual(reddit_text, "[r/GenZ] no cap this is wild")
        self.assertEqual(twitch_text, "[Twitch #xqc] chat is cooked")


if __name__ == "__main__":
    unittest.main()
