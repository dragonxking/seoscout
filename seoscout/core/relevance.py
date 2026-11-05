"""Shared, deterministic search relevance; keep topic and page intent separate."""
import re
import unicodedata
from urllib.parse import unquote, urlparse, parse_qsl, urlencode, urlunparse

SEARCH_POLICY_VERSION = 5
OFFICIAL_DOMAINS = {'store.steampowered.com', 'steamcommunity.com',
                    'store.epicgames.com', 'gog.com', 'www.gog.com'}
ALIASES = {'archeologist': 'archaeologist', 'cooperative': 'coop',
           'multiplayer': 'coop', 'mech': 'mecha', 'mechanized': 'mecha',
           'mechanize': 'mecha', 'mutant': 'mutation', 'mutate': 'mutation',
           'mutations': 'mutation', 'reviews': 'review', 'characters': 'character',
           'weapons': 'weapon', 'items': 'item', 'bosses': 'boss',
           'builds': 'build', 'fossils': 'fossil', 'pets': 'pet',
           'updates': 'update', 'news': 'update', 'patch': 'update',
           'beta': 'playtest', 'survivors': 'survivor'}
ALIASES.update({'flamethrowers':'flamethrower','trailers':'trailer',
                'launch':'release','launches':'release','launching':'release',
                'released':'release','dates':'date'})
STOP = {'the', 'a', 'an', 'of', 'for', 'from', 'in', 'on', 'with', 'and',
        'is', 'it', 'to', 'how', 'new', 'dlc', 'official', 'guide', 'all',
        'game', 'games', 'do', 'does', 'will', 'when'}

def canonical_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    path = parsed.path
    query = [(k,v) for k,v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k not in {'srsltid','curator_clanid'}]
    if host == 'store.steampowered.com':
        match = re.match(r'^/app/(\d+)(?:/|$)', path)
        if match:
            path = f'/app/{match[1]}/'
            query = []
    if host == 'steamcommunity.com':
        query = [(k,v) for k,v in query if k != 'l']
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, parsed.params, urlencode(query), ''))

def words(text):
    text = unicodedata.normalize('NFKC', unquote(text)).casefold()
    text = re.sub(r'\bco[\s-]+op\b', 'coop', text)
    return re.findall(r'[^\W_]+', text, flags=re.UNICODE)

def topic_matches(text, topic):
    if not topic:
        return True
    tokens, target = words(text), words(topic)
    # Whole words avoid Bloodwing/Broodwing confusion. Allow punctuation and
    # intervening title words: "Brotato ... NEW DLC ... Primal Dread".
    return bool(target) and (all(t in tokens for t in target) or
                            ''.join(target) in tokens)

def is_official_source(url, official_domains=()):
    host = (urlparse(url).hostname or '').lower()
    if host == 'steamcommunity.com':
        return bool(re.match(r'^/(?:games/\d+/announcements(?:/|$)|app/\d+/(?:announcements|allnews)(?:/|$))', urlparse(url).path))
    return host in ((OFFICIAL_DOMAINS - {'steamcommunity.com'}) | set(official_domains))

def intent_tokens(keyword, topic):
    topic_words = set(words(topic))
    return {ALIASES.get(t, t) for t in words(keyword)
            if t not in topic_words and t not in STOP}

def assess(title, snippet, url, keyword, topic, exclude_terms=(), official_domains=()):
    text = f'{title} {snippet} {url}'
    host = (urlparse(url).hostname or '').lower()
    if any(term.casefold() in text.casefold() for term in exclude_terms):
        return False, 0, 'excluded_term'
    if re.search(r'\b(hack|exploit|pastebin|mod apk|auto farm|inf money)\b', text, re.I):
        return False, 0, 'unsafe_or_cheat_result'
    if 'tiktok.com/discover/' in url or not topic_matches(text, topic):
        return False, 0, 'topic_mismatch'
    intent = intent_tokens(keyword, topic)
    tokens = {ALIASES.get(t, t) for t in words(text)}
    official = is_official_source(url, official_domains)
    if 'reddit' in intent and host not in {'reddit.com', 'www.reddit.com', 'old.reddit.com'}:
        return False, 0, 'requires_reddit_source'
    # Do not let generic storefronts/prices masquerade as platform release proof.
    commercial = any(x in host for x in ('allkeyshop.', 'driffle.', 'g2a.', 'gg.deals', 'eneba.', 'cdkeys.'))
    if commercial:
        return False, 0, 'commercial_listing_not_reference'
    hits = len(intent & tokens)
    ratio = hits / len(intent) if intent else 1
    specific = not intent or ratio >= 0.6
    if intent == {'content'} or (intent == {'gameplay'} and 'trailer' not in tokens):
        specific = True
    # Related official overviews remain available as supporting material, but
    # never satisfy a specifically requested community destination.
    selected = specific or (official and 'reddit' not in intent)
    reason = 'intent_match' if specific else ('official_background' if official else 'topic_only')
    score = (100 if specific else 0) + int(ratio * 50) + (30 if official else 0)
    return selected, score, reason

def rank_items(items, keyword, topic, exclude_terms=(), official_domains=()):
    for item in items:
        item.selected, item.relevance_score, item.selection_reason = assess(
            item.title, getattr(item, 'snippet', ''), item.url, keyword, topic,
            exclude_terms, official_domains)
    return sorted(items, key=lambda i: (i.selected, i.relevance_score), reverse=True)

def limit_video_duration(items, max_duration):
    """Keep the shortest relevant fallback if all relevant videos are long."""
    chosen = [i for i in items if i.selected]
    under_limit = [i for i in chosen if (i.duration_seconds or 0) <= max_duration]
    fallback = min(chosen, key=lambda i: i.duration_seconds or 0) if chosen and not under_limit else None
    for item in chosen:
        if (item.duration_seconds or 0) > max_duration and item is not fallback:
            item.selected = False
            item.selection_reason = 'duration_limit'
    return sorted(items, key=lambda i: (i.selected, i.relevance_score), reverse=True)

def blocked_domain(url, blocked, keyword=''):
    host = (urlparse(url).hostname or '').lower()
    for domain in blocked:
        domain = domain.lower().removeprefix('www.')
        # A requested Reddit destination is intentional, not a generic web hit.
        if domain == 'reddit.com' and 'reddit' in words(keyword):
            continue
        if host == domain or host.endswith('.' + domain):
            return True
    return False
