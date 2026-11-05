import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from seoscout.core.models import WebItem, YouTubeItem
from seoscout.core.relevance import topic_matches, assess, rank_items, blocked_domain, limit_video_duration, is_official_source
from seoscout.core.config import Config
from seoscout.search import filter_keywords_for_retry, load_existing_results, search_with_retry
from seoscout.cli import _derive_project
from seoscout.search import load_reference_videos, supplement_videos, merge_results
from seoscout.core.relevance import canonical_url
from seoscout.core.web import Web

TOPIC = 'Brotato Primal Dread'

class SearchRelevanceTests(unittest.TestCase):
    def test_punctuation_and_split_topic_without_other_dlc(self):
        for title in ['Brotato: Primal Dread DLC Launch Trailer',
                      'Brotato - Primal Dread',
                      "I BROKE TIME in Brotato's NEW DLC | Primal Dread",
                      'Brotato 4 NEW Characters Revealed in Primal Dread DLC']:
            self.assertTrue(topic_matches(title, TOPIC), title)
        self.assertFalse(topic_matches('Brotato: Abyssal Terrors', TOPIC))
        self.assertFalse(topic_matches('Bloodwing guide', 'Broodwing'))

    def test_longtail_rejects_topic_only_but_marks_official_background(self):
        args = ('Brotato: Primal Dread', '', 'https://example.com/overview', TOPIC+' droid', TOPIC)
        self.assertEqual(assess(*args)[2], 'topic_only')
        self.assertFalse(assess(*args)[0])
        self.assertEqual(assess(args[0], '', 'https://store.steampowered.com/app/4498220', *args[3:])[2], 'official_background')
        self.assertTrue(assess('Brotato: Primal Dread Droid build', '', args[2], *args[3:])[0])

    def test_reddit_requested_explicitly(self):
        kw = TOPIC+' release date reddit'
        self.assertFalse(blocked_domain('https://www.reddit.com/r/brotato/', {'reddit.com'}, kw))
        self.assertTrue(blocked_domain('https://www.reddit.com/r/brotato/', {'reddit.com'}, TOPIC+' items'))
        self.assertFalse(blocked_domain('https://notreddit.com/', {'reddit.com'}))
        self.assertFalse(assess(TOPIC, '', 'https://steamdb.info/', kw, TOPIC)[0])

    def test_commerce_cheats_and_custom_blocked_words(self):
        for title, url in [(TOPIC+' PS5 Key', 'https://www.allkeyshop.com/'),
                           (TOPIC+' MOD APK', 'https://example.com/')]:
            self.assertFalse(assess(title, '', url, TOPIC+' ps5', TOPIC)[0])
        self.assertFalse(assess(TOPIC+' excluded', '', 'https://example.com', TOPIC, TOPIC, ['excluded'])[0])

    def test_flame_plural_and_launch_date_alias(self):
        self.assertTrue(assess('Brotato insane mage in the new DLC', TOPIC+' endless flamethrowers',
                              'https://youtube.com/watch?v=123456789ab', TOPIC+' flamethrower', TOPIC)[0])
        self.assertTrue(assess(TOPIC+' Xbox launch date', '', 'https://example.com/',
                              TOPIC+' xbox release date', TOPIC)[0])

    def test_steam_user_content_is_not_official_background(self):
        self.assertFalse(is_official_source('https://steamcommunity.com/app/1942280/discussions/0/123/'))
        self.assertFalse(is_official_source('https://steamcommunity.com/sharedfiles/filedetails/?id=123'))
        self.assertFalse(is_official_source('https://steamcommunity.com/app/1942280/'))
        self.assertTrue(is_official_source('https://steamcommunity.com/app/1942280/announcements/'))
        self.assertTrue(is_official_source('https://steamcommunity.com/games/1942280/announcements/detail/123'))

    def test_canonical_urls_preserve_content_identifiers(self):
        self.assertEqual(canonical_url('https://store.steampowered.com/app/4498220/Brotato_Primal_Dread/?l=french&curator_clanid=1'),
                         'https://store.steampowered.com/app/4498220/')
        self.assertEqual(canonical_url('https://steamcommunity.com/app/1942280/discussions/0/123/?l=dutch&ctp=3'),
                         'https://steamcommunity.com/app/1942280/discussions/0/123/?ctp=3')
        self.assertNotEqual(canonical_url('https://store.steampowered.com/app/4498220/'),
                            canonical_url('https://store.steampowered.com/app/1942280/'))

    def test_official_fallback_is_bounded_and_keeps_keyword_intent(self):
        item=WebItem(TOPIC+' playtest','https://store.steampowered.com/news/app/1942280/view/1',
                     'store.steampowered.com','', selection_reason='intent_match')
        async def scenario():
            with patch.object(Web,'_search_single',new=AsyncMock(side_effect=[[],[item]])) as search:
                found=await Web().search_batch([TOPIC+' playtest'], TOPIC)
                self.assertEqual(search.await_count,2)
                self.assertEqual(search.await_args_list[1].args[0],TOPIC+' playtest')
                self.assertIn('site:steamcommunity.com',search.await_args_list[1].kwargs['query'])
                self.assertEqual(found[TOPIC+' playtest'],[item])
        asyncio.run(scenario())

    def test_official_web_mode_retains_competitor_as_deselected(self):
        class Response:
            status=200
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def json(self):
                return {'organic':[
                    {'title':TOPIC+' droid','link':'https://example.com/guide','snippet':'Droid'},
                    {'title':TOPIC,'link':'https://store.steampowered.com/app/4498220/','snippet':''}]}
        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            def post(self,*args,**kwargs): return Response()
        async def scenario():
            with patch('seoscout.core.web.aiohttp.ClientSession',return_value=Session()), \
                 patch.object(Config,'OFFICIAL_WEB_ONLY',True,create=True), \
                 patch.object(Config,'BLOCKED_DOMAINS',set()), \
                 patch.object(Config,'get_proxy_url_for_stage',return_value=None), \
                 patch('seoscout.core.web.asyncio.sleep',new=AsyncMock()):
                found=await Web()._search_single(TOPIC+' droid',asyncio.Semaphore(1),TOPIC)
                self.assertEqual(sum(i.selected for i in found),1)
                other=next(i for i in found if i.domain=='example.com')
                self.assertEqual(other.selection_reason,'nonofficial_web_source')
                self.assertFalse(other.selected)
        asyncio.run(scenario())

    def test_ranking_specific_before_background_and_official_before_commerce(self):
        items = [WebItem(TOPIC, 'https://example.com/', 'example.com', ''),
                 WebItem(TOPIC+' droid', 'https://store.steampowered.com/news/', 'store.steampowered.com', ''),
                 WebItem(TOPIC, 'https://store.epicgames.com/', 'store.epicgames.com', '')]
        ranked = rank_items(items, TOPIC+' droid', TOPIC)
        self.assertEqual([i.selection_reason for i in ranked], ['intent_match','official_background','topic_only'])
        self.assertEqual(WebItem(**ranked[0].to_dict()), ranked[0])

    def test_all_deselected_retries(self):
        old = {'x': {'youtube': {'items':[]}, 'web': {'items':[{'selected':False}]}}}
        self.assertEqual(filter_keywords_for_retry([{'keyword':'x'}], old), (['x'], ['x']))
        calls = []
        async def search(kws):
            calls.append(kws)
            return {'x':[WebItem('x','https://example.com','example.com','',selected=len(calls)>1)]}
        result = asyncio.run(search_with_retry(search, ['x'], 'Web', max_retries=2, retry_delay=0))
        self.assertEqual(len(calls),2)
        self.assertTrue(result['x'][0].selected)

    def test_stale_cache_and_stable_project(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'search_results.json'
            p.write_text(json.dumps({'search_signature':'old','keywords':[{'keyword':'x'}]}))
            with patch.object(Config,'OUT_DIR',directory):
                self.assertEqual(load_existing_results('new'),{})
            p.write_text(json.dumps({'topic_name':'Brotato: Primal Dread'}))
            self.assertEqual(_derive_project(str(p)),'brotato_primal_dread')

    def test_reviewed_sources_are_identified_and_copied_per_keyword(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'review.json'
            path.write_text(json.dumps({'topic':TOPIC,'videos':[
                {'video_id':'123456789ab','title':'A new DLC','description_excerpt':'Droid build',
                 'views':{'value':10},'relevance':{'status':'included'}},
                {'video_id':None,'title':'No URL','relevance':{'status':'included'}},
                {'video_id':'23456789abc','title':'Unreviewed','relevance':{'status':'needs_review'}}]}))
            seeds=load_reference_videos(path, TOPIC)
            self.assertEqual(len(seeds),1)
            first=supplement_videos([],seeds,TOPIC+' droid',TOPIC,[],5)
            second=supplement_videos([],seeds,TOPIC+' price',TOPIC,[],5)
            self.assertEqual(first[0].source,'reviewed_reference')
            self.assertEqual(second,[])
            self.assertTrue(first[0].selected)

    def test_long_specific_video_survives_short_irrelevant_trailer(self):
        videos=[YouTubeItem(TOPIC+' archaeologist','https://youtube.com/watch?v=123456789ab','123456789ab','c','1:10:00',4200,1),
                YouTubeItem(TOPIC+' trailer','https://youtube.com/watch?v=23456789abc','23456789abc','c','1:00',60,1)]
        ranked=limit_video_duration(rank_items(videos, TOPIC+' archaeologist',TOPIC),3600)
        self.assertTrue(ranked[0].selected)
        self.assertEqual(ranked[0].duration_seconds,4200)
        self.assertFalse(ranked[1].selected)

    def test_caption_terms_support_narrow_queries_without_copying_transcript(self):
        seed=YouTubeItem('Primal Dread gameplay','https://youtube.com/watch?v=123456789ab',
                         '123456789ab','c','1:00',60,1,snippet=TOPIC,source='reviewed_reference')
        seed._caption_segments=[{'start':1342,'text':'one speed for each fossil item equipped'}]
        results=supplement_videos([], [seed], TOPIC+' fossils', TOPIC, [], 5)
        self.assertTrue(results[0].selected)
        self.assertIn('1342s: fossil',results[0].snippet)
        self.assertNotIn('one speed for each',results[0].snippet)
        self.assertEqual(seed.snippet,TOPIC)

    def test_fresh_empty_results_replace_stale_hits(self):
        old={'x':{'youtube':{'count':1,'items':[{'selected':True}]},'web':{'count':0,'items':[]}}}
        result=merge_results([{'keyword':'x'}],old,{'x':[]},{})
        self.assertEqual(result[0]['youtube']['items'],[])

if __name__ == '__main__':
    unittest.main()
