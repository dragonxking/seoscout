import unittest
import asyncio
from unittest.mock import AsyncMock, patch
import aiohttp
from seoscout.core.steam_news import steam_news_endpoint, official_news_text
from seoscout.core.models import WebItem
from seoscout.core.config import Config
from seoscout.core.web import Web


class SteamNewsTests(unittest.TestCase):
    def test_endpoint_is_limited_to_official_app_news_pages(self):
        for url in ('https://steamcommunity.com/app/5335510/',
                    'https://steamcommunity.com/app/5335510/allnews/'):
            appid, endpoint = steam_news_endpoint(url)
            self.assertEqual(appid, 5335510)
            self.assertIn('maxlength=0', endpoint)
        self.assertIsNone(steam_news_endpoint('https://example.com/app/5335510/'))
        self.assertIsNone(steam_news_endpoint('https://steamcommunity.com/app/5335510/discussions/'))

    def test_third_party_news_is_excluded(self):
        payload = {'appnews': {'appid': 123, 'newsitems': [
            {'feedname': 'SteamDB', 'contents': 'not developer evidence'},
            {'feedname': 'steam_community_announcements', 'title': 'Patch',
             'contents': 'Verified patch body', 'date': 1792961246,
             'url': 'https://steamcommunity.com/official', 'author': 'Developer'},
        ]}}
        text = official_news_text(payload, 123)
        self.assertIn('Verified patch body', text)
        self.assertNotIn('not developer evidence', text)
        self.assertEqual(official_news_text(payload, 456), '')


class SteamFallbackFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_reader_connection_failure_reaches_fallback(self):
        item = WebItem('Official news', 'https://steamcommunity.com/app/123/allnews/',
                       'steamcommunity.com', '')
        web = Web()
        fallback = AsyncMock(return_value=(item, 'Official announcement body'))
        with patch('seoscout.core.web.load_cache', return_value=None), \
             patch.object(Config, 'WEB_EXTRACT_RETRIES', 1), \
             patch.object(web, '_steam_news_fallback', fallback), \
             patch('aiohttp.ClientSession.get', side_effect=aiohttp.ClientConnectionError()):
            result = await web._extract_single(item, asyncio.Semaphore(1), AsyncMock())
        self.assertEqual(result[1], 'Official announcement body')
        fallback.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
