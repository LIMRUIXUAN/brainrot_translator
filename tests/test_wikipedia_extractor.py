import unittest

from src.extract_wikipedia_slang import extract_slang_terms


class WikipediaExtractorTests(unittest.TestCase):
    def test_extracts_definition_list_records_and_removes_citations(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <h2>A</h2>
              <dl>
                <dt>rizz</dt>
                <dd>Charisma or flirting ability.<sup class="reference">[1]</sup></dd>
                <dt>no cap</dt>
                <dd>Used to mean no lie or seriously. Example: no cap, this is good.</dd>
              </dl>
              <h2>References</h2>
            </main>
          </body>
        </html>
        """

        records = extract_slang_terms(html, collected_at="2026-05-11")

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["term"], "no cap")
        self.assertEqual(records[0]["example"], "no cap, this is good.")
        self.assertEqual(records[1]["term"], "rizz")
        self.assertEqual(records[1]["meaning"], "Charisma or flirting ability.")


if __name__ == "__main__":
    unittest.main()
