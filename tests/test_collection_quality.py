import asyncio
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from seoscout.core.collection_quality import content_error, collection_is_current
from seoscout.core.models import WebItem
from seoscout.core.web import Web
from seoscout.core.config import Config
from seoscout.collect import run_collect


class CollectionQualityTests(unittest.TestCase):
    def test_collect_integration_writes_quality_and_empty_bundle(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Config, 'init'), patch.object(Config, 'OUT_DIR', directory):
            (Path(directory) / 'search_results.json').write_text(json.dumps({'keywords': [{
                'keyword': 'Example Game mechanics', 'category': 'guide',
                'youtube': {'items': []}, 'web': {'items': [{'title': 'Example Game',
                'url': 'https://example.org', 'domain': 'example.org', 'snippet': '', 'selected': True}]} }]}))
            with patch.object(Web, 'extract_batch', new=AsyncMock(return_value=[(
                WebItem(title='Example Game', url='https://example.org', domain='example.org', snippet=''),
                'Warning: Target URL returned error 403: Forbidden' * 10)])):
                asyncio.run(run_collect('example_game'))
            quality = json.loads((Path(directory) / 'collect_quality.json').read_text())
            self.assertEqual(quality['missing_sources'], ['Example Game mechanics'])
            self.assertEqual(quality['rejected_sources'][0]['reason'], 'upstream_http_error')
            self.assertEqual(quality['usable_unique_sources'], {'youtube': 0, 'web': 0})
    def test_http_200_reader_must_not_admit_upstream_403(self):
        body = 'Warning: Target URL returned error 403: Forbidden\n' + 'Blocked by network security. ' * 20
        self.assertEqual(content_error(body), 'upstream_http_error')
        self.assertEqual(content_error('Brotato Primal Dread official mechanics. ' * 20), '')

    def test_saved_file_requires_current_input_and_real_body(self):
        good = {'total_sources': 1, 'collect_signature': 'v2', 'sources': {
            'web': {'pages': [{'content': 'Brotato Primal Dread official mechanics. ' * 20}]}}}
        self.assertTrue(collection_is_current(good, 'v2'))
        self.assertFalse(collection_is_current(good, 'v3'))
        good['sources']['web']['pages'][0]['content'] = 'Warning: Target URL returned error 403: Forbidden' * 10
        self.assertFalse(collection_is_current(good, 'v2'))

    def test_batch_exception_preserves_item_and_other_results(self):
        one = WebItem(title='bad', url='https://example.org/1', domain='example.org', snippet='')
        two = WebItem(title='good', url='https://example.org/2', domain='example.org', snippet='')
        with patch.object(Web, '_extract_single', new=AsyncMock(side_effect=[RuntimeError('network'), (two, 'real body')])):
            result = asyncio.run(Web().extract_batch([one, two]))
        self.assertEqual(result, [(one, ''), (two, 'real body')])

    def test_empty_sources_never_count_as_current(self):
        self.assertFalse(collection_is_current({'total_sources': 0, 'collect_signature': 'v2'}, 'v2'))
