import unittest
from unittest.mock import patch

from seoscout.core.config import Config
from seoscout.core.llm_client import LLMClient


class ThinkingPayloadTests(unittest.TestCase):
    def test_default_preserves_provider_behavior(self):
        with patch.object(Config, 'LLM_THINKING', ''):
            payload = LLMClient().request_payload('Write a guide.')
        self.assertNotIn('thinking', payload)
        self.assertFalse(payload['stream'])

    def test_explicit_toggle_is_sent(self):
        for mode in ('enabled', 'disabled'):
            with self.subTest(mode=mode), patch.object(Config, 'LLM_THINKING', mode):
                self.assertEqual(LLMClient().request_payload('Write a guide.')['thinking'], {'type': mode})

    def test_invalid_toggle_is_rejected_before_network(self):
        with patch.object(Config, 'LLM_THINKING', 'unexpected'):
            with self.assertRaises(ValueError):
                LLMClient()


if __name__ == '__main__':
    unittest.main()
