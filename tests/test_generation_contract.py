import unittest
from seoscout.generate import validate_markdown, _build_repair_prompt


class GenerationContractTests(unittest.TestCase):
    def test_requires_citation_and_metadata_without_body_h1(self):
        doc = 'export const metadata = { title: "Example" }\n\n## Answer\n' + 'A sourced answer. ' * 20
        self.assertFalse(validate_markdown(doc)[0])
        doc += '\n[Official evidence](https://store.steampowered.com/app/1942280/)'
        self.assertTrue(validate_markdown(doc)[0])
        self.assertFalse(validate_markdown(doc+'\n# Duplicate H1')[0])

    def test_repair_preserves_sources_and_editorial_brief(self):
        prompt = 'Verified fact X. Source: https://official.example/evidence. Scope: only X.'
        repaired = _build_repair_prompt(prompt, {'keyword':'Example'}, 'bad draft', 'missing citation')
        self.assertIn(prompt, repaired)
        self.assertIn('missing citation', repaired)
