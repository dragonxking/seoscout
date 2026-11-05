#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 1: Search & collect metadata

Search YouTube and Web in parallel for each keyword,
output search_results.json for review.
"""

import asyncio
import argparse
import json
import os
import sys
import hashlib
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Windows UTF-8 compatibility
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from .core.config import Config
from .core.youtube import YouTube
from .core.web import Web
from .core.relevance import SEARCH_POLICY_VERSION
from .core.relevance import rank_items, topic_matches, limit_video_duration, intent_tokens, words, ALIASES
from .core.models import YouTubeItem
from .core.utils import load_keywords_from_json, save_json, ensure_dir


def load_existing_results(signature=None) -> Dict[str, Dict]:
    results_file = Path(Config.OUT_DIR) / "search_results.json"

    if not results_file.exists():
        return {}

    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if signature is not None and data.get('search_signature') != signature:
            print('♻️ Search policy or inputs changed; refreshing previous search results')
            return {}

        existing = {}
        for kw_data in data.get('keywords', []):
            keyword = kw_data['keyword']
            existing[keyword] = {
                'category': kw_data.get('category', ''),
                'youtube': kw_data.get('youtube', {'count': 0, 'items': []}),
                'web': kw_data.get('web', {'count': 0, 'items': []})
            }

        return existing
    except Exception as e:
        print(f"⚠️  Failed to load existing results: {e}")
        return {}


def filter_keywords_for_retry(
    all_keywords: List[Dict],
    existing_results: Dict[str, Dict]
) -> Tuple[List[str], List[str]]:
    youtube_retry = []
    web_retry = []

    for kw_dict in all_keywords:
        keyword = kw_dict['keyword']
        existing = existing_results.get(keyword, {})

        youtube_data = existing.get('youtube', {})
        if not any(i.get('selected', True) for i in youtube_data.get('items', [])):
            youtube_retry.append(keyword)

        web_data = existing.get('web', {})
        if not any(i.get('selected', True) for i in web_data.get('items', [])):
            web_retry.append(keyword)

    return youtube_retry, web_retry


def merge_results(
    all_keywords: List[Dict],
    existing_results: Dict[str, Dict],
    youtube_new: Dict[str, List],
    web_new: Dict[str, List]
) -> List[Dict]:
    merged = []

    for kw_dict in all_keywords:
        keyword = kw_dict['keyword']
        category = kw_dict.get('category', '')

        existing = existing_results.get(keyword, {})
        # Preserve category from existing or from input
        if not category:
            category = existing.get('category', '')

        existing_youtube = existing.get('youtube', {'count': 0, 'items': []})
        existing_web = existing.get('web', {'count': 0, 'items': []})

        new_youtube = youtube_new.get(keyword, [])
        new_web = web_new.get(keyword, [])

        final_youtube = {
            'count': len(new_youtube),
            'items': [item.to_dict() for item in new_youtube]
        } if keyword in youtube_new else existing_youtube

        final_web = {
            'count': len(new_web),
            'items': [item.to_dict() for item in new_web]
        } if keyword in web_new else existing_web

        merged.append({
            'keyword': keyword,
            'category': category,
            'youtube': final_youtube,
            'web': final_web
        })

    return merged


async def search_with_retry(
    search_func,
    keywords: List[str],
    source_name: str,
    max_retries: int = None,
    retry_delay: int = None
) -> Dict[str, List]:
    if not keywords:
        return {}

    if max_retries is None:
        max_retries = Config.SEARCH_MAX_RETRIES
    if retry_delay is None:
        retry_delay = Config.SEARCH_RETRY_DELAY

    results = {}
    failed_keywords = keywords.copy()

    for attempt in range(1, max_retries + 1):
        if not failed_keywords:
            break

        print(f"\n{source_name} attempt {attempt}: {len(failed_keywords)} keywords")

        batch_results = await search_func(failed_keywords)

        new_failed = []
        for keyword in failed_keywords:
            items = batch_results.get(keyword, [])
            if items or keyword not in results:
                results[keyword] = items
            usable = [i for i in items if (i.get('selected', True) if isinstance(i, dict) else i.selected)]
            if usable:
                results[keyword] = items
                print(f"  ✓ {keyword}: {len(usable)}/{len(items)} selected results")
            else:
                new_failed.append(keyword)
                if attempt < max_retries:
                    print(f"  ✗ {keyword}: no results, will retry")
                else:
                    print(f"  ✗ {keyword}: no results after {max_retries} retries")

        failed_keywords = new_failed

        if failed_keywords and attempt < max_retries:
            print(f"  Waiting {retry_delay}s before retry...")
            await asyncio.sleep(retry_delay)

    success_count = len(keywords) - len(failed_keywords)
    failed_count = len(failed_keywords)
    print(f"\n{source_name} search done:")
    print(f"  - Success: {success_count}")
    if failed_count > 0:
        print(f"  - Failed:  {failed_count} (after {max_retries} retries)")

    return results


def load_reference_videos(path, topic):
    """Only admit identified videos from an explicitly reviewed input dataset."""
    if not path:
        return []
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    if not topic_matches(raw.get('topic', raw.get('topic_name', '')), topic):
        raise ValueError('Reference dataset topic does not match the keyword topic')
    found = {}
    for item in raw.get('videos', []):
        vid = item.get('video_id')
        if not vid or not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            continue
        if item.get('relevance', {}).get('status') != 'included':
            continue
        snippet = item.get('description_excerpt') or ''
        # Reviewed snippets carry explicit dataset context, not invented text
        # attributed to the uploader. source distinguishes these from searches.
        snippet = f"{topic}. {snippet}"
        duration = item.get('duration') or ''
        seconds = 0
        try:
            for part in duration.split(':'):
                seconds = seconds * 60 + int(part)
        except ValueError:
            seconds = 0
        found[vid] = YouTubeItem(
            title=item['title'], url=f'https://www.youtube.com/watch?v={vid}', video_id=vid,
            channel=item.get('channel') or '', duration=duration, duration_seconds=seconds,
            view_count=(item.get('views') or {}).get('value') or 0,
            snippet=snippet, source='reviewed_reference')
        evidence_file = item.get('transcript_review', {}).get('evidence_file')
        if evidence_file:
            root = Path(path).resolve().parent
            evidence = (root / evidence_file).resolve()
            # Never follow dataset file references outside its own directory.
            if evidence.is_relative_to(root) and evidence.is_file() and evidence.stat().st_size <= 2_000_000:
                try:
                    captions = json.loads(evidence.read_text(encoding='utf-8'))
                    if captions.get('status') == 'success':
                        found[vid]._caption_segments = captions.get('segments', [])
                except (OSError, ValueError):
                    pass
    return list(found.values())


def supplement_videos(live, references, keyword, topic, exclude_terms, limit):
    from dataclasses import replace
    # Copy per keyword: relevance/selection fields must not leak between pages.
    seeds = []
    intent = intent_tokens(keyword, topic)
    for reference in references:
        seed = replace(reference)
        matches = []
        for segment in getattr(reference, '_caption_segments', []):
            tokens = {ALIASES.get(t,t) for t in words(segment.get('text', ''))}
            hit = intent & tokens
            if hit:
                # Store evidence coordinates and matched terms, not an entire
                # caption in every search-result record. Collection fetches body.
                matches.append(f"{segment.get('start',0)}s: {', '.join(sorted(hit))}")
            if len(matches) == 3:
                break
        if matches:
            seed.snippet += ' Reviewed caption matches: ' + '; '.join(matches)
        seeds.append(seed)
    seeds = rank_items(seeds, keyword, topic, exclude_terms)
    merged = {i.video_id: i for i in live}
    for item in seeds:
        if item.selected and (item.video_id not in merged or not merged[item.video_id].selected):
            merged[item.video_id] = item
    ranked = limit_video_duration(rank_items(list(merged.values()), keyword, topic, exclude_terms), Config.YOUTUBE_MAX_DURATION)
    # Bound the final extraction candidates; keep rejected live hits for review.
    return [i for i in ranked if i.selected][:limit] + [i for i in ranked if not i.selected]


async def run_search(project: str, keywords_file: str, refresh: bool = False, references_file=None, exclude_domains=(), official_web_only=False):
    """Run the collect step programmatically."""
    Config.init(project)

    print("=" * 70)
    print(f"  Step 1: Search [{project}]")
    print("=" * 70)

    if not Config.validate():
        print("\n⚠️  Config incomplete, continuing anyway")

    Config.print_summary()

    keywords = load_keywords_from_json(keywords_file)

    if not keywords:
        print("❌ No keywords found")
        return

    # Extract keyword strings and detect categories
    keyword_strings = [kw['keyword'] for kw in keywords]
    categories = set(kw['category'] for kw in keywords if kw['category'])

    # Read topic_name
    topic_name = ''
    exclude_terms = []
    try:
        with open(keywords_file, 'r', encoding='utf-8') as f:
            kw_raw = json.load(f)
        topic_name = kw_raw.get('topic_name', '')
        if topic_name:
            print(f"🏷️  Topic: {topic_name}")
        exclude_terms = [t.lower() for t in kw_raw.get('exclude_terms', [])]
        if exclude_terms:
            print(f"🚫 Exclude terms: {', '.join(exclude_terms)}")
    except Exception:
        pass

    print(f"📋 Keywords: {len(keywords)}")
    if categories:
        print(f"📂 Categories: {', '.join(sorted(categories))}")

    Config.BLOCKED_DOMAINS.update(kw_raw.get('blocked_domains', []))
    Config.BLOCKED_DOMAINS.update(d.strip().lower() for d in exclude_domains if d.strip())
    Config.OFFICIAL_SOURCE_DOMAINS = kw_raw.get('official_domains', [])
    Config.OFFICIAL_WEB_ONLY = official_web_only
    reference_videos = load_reference_videos(references_file, topic_name)
    if references_file:
        print(f'📚 Reviewed reference videos: {len(reference_videos)}')
    signature = hashlib.sha256(json.dumps({
        'policy': SEARCH_POLICY_VERSION, 'input': kw_raw,
        'blocked': sorted(Config.BLOCKED_DOMAINS),
        'youtube_limit': Config.YOUTUBE_INITIAL_RESULTS,
        'youtube_duration': Config.YOUTUBE_MAX_DURATION,
        'web_limit': Config.WEB_SEARCH_TOP_N,
        'official_web_only': official_web_only,
        'reference_hash': hashlib.sha256(Path(references_file).read_bytes()).hexdigest() if references_file else None,
        'reference_captions': [getattr(v, '_caption_segments', []) for v in reference_videos],
    }, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    existing_results = {} if refresh else load_existing_results(signature)
    youtube_retry, web_retry = filter_keywords_for_retry(keywords, existing_results)

    print(f"\n📊 Retry stats:")
    print(f"  - Total:          {len(keyword_strings)}")
    print(f"  - YouTube retry:  {len(youtube_retry)}")
    print(f"  - Web retry:      {len(web_retry)}")
    print(f"  - YouTube cached: {len(keyword_strings) - len(youtube_retry)}")
    print(f"  - Web cached:     {len(keyword_strings) - len(web_retry)}")

    yt = YouTube()
    web = Web()

    yt_results = {}
    web_results = {}

    if youtube_retry or web_retry:
        print("\n" + "=" * 70)
        print("  Starting search (with auto-retry)")
        print("=" * 70)

        async def yt_search_with_topic(kws):
            live = await yt.search_batch(kws, topic_name=topic_name, exclude_terms=exclude_terms)
            return {kw: supplement_videos(live.get(kw, []), reference_videos, kw, topic_name,
                                          exclude_terms, Config.YOUTUBE_INITIAL_RESULTS) for kw in kws}

        async def web_search_with_topic(kws):
            return await web.search_batch(kws, topic_name=topic_name, exclude_terms=exclude_terms)

        yt_results, web_results = await asyncio.gather(
            search_with_retry(yt_search_with_topic, youtube_retry, "YouTube"),
            search_with_retry(web_search_with_topic, web_retry, "Web")
        )
    else:
        print("\n✅ All keywords already have results, skipping search")

    keyword_data = merge_results(keywords, existing_results, yt_results, web_results)

    pending = {
        "version": "2.0",
        "created_at": datetime.now().isoformat(),
        "search_signature": signature,
        "search_policy_version": SEARCH_POLICY_VERSION,
        "reference_source": str(Path(references_file).resolve()) if references_file else None,
        "keywords": keyword_data
    }

    output_file = f"{Config.OUT_DIR}/search_results.json"
    ensure_dir(Config.OUT_DIR)
    if Path(output_file).exists():
        backup = Path(Config.OUT_DIR) / 'search_history'
        backup.mkdir(exist_ok=True)
        shutil.copy2(output_file, backup / f"search_results_{datetime.now():%Y%m%d_%H%M%S_%f}.json")
    pending['quality_summary'] = search_quality(keyword_data)
    save_json(pending, output_file + '.tmp')
    Path(output_file + '.tmp').replace(output_file)

    total_yt = sum(kw['youtube']['count'] for kw in keyword_data)
    total_web = sum(kw['web']['count'] for kw in keyword_data)

    print("\n" + "=" * 70)
    print("  ✅ Search complete")
    print("=" * 70)
    print(f"YouTube: {total_yt} videos")
    print(f"Web:    {total_web} pages")
    print(json.dumps(pending['quality_summary'], ensure_ascii=False, indent=2))
    print(f"Output: {output_file}")
    print("\nNext steps:")
    print("  1. Review search_results.json")
    print("  2. Set 'selected': false to exclude items")
    print(f"  3. After source review: seoscout collect --project {project}")
    print("=" * 70)


def search_quality(keywords):
    summary = {'keyword_count': len(keywords), 'missing_sources': [], 'background_only': []}
    for source in ('youtube', 'web'):
        items = [i for k in keywords for i in k[source]['items']]
        selected = [i for i in items if i.get('selected', True)]
        summary[source] = {'results': len(items), 'unique_urls': len({i['url'] for i in items}),
                           'selected': len(selected), 'selected_unique_urls': len({i['url'] for i in selected}),
                           'keywords_with_selected': sum(any(i.get('selected', True) for i in k[source]['items']) for k in keywords)}
    for k in keywords:
        chosen = [i for source in ('youtube', 'web') for i in k[source]['items'] if i.get('selected', True)]
        if not chosen:
            summary['missing_sources'].append(k['keyword'])
        elif all(i.get('selection_reason') == 'official_background' for i in chosen):
            summary['background_only'].append(k['keyword'])
    return summary


async def main():
    parser = argparse.ArgumentParser(description="Step 1: Search & collect metadata")
    parser.add_argument("--project", "--domain", required=True,
                        help="Project name for data isolation")
    parser.add_argument("--keywords", "--json", required=True,
                        help="Path to keywords JSON file")
    args = parser.parse_args()

    await run_search(args.project, args.keywords)


if __name__ == "__main__":
    asyncio.run(main())
