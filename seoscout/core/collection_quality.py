"""Content validity checks shared by collection and generation."""
import re

COLLECT_POLICY_VERSION = 2


def content_error(content, kind='web'):
    if not isinstance(content, str) or len(content.strip()) < (80 if kind == 'youtube' else 200):
        return 'empty_or_too_short'
    if re.search(r'Target URL returned error\s+[45]\d\d', content, re.I):
        return 'upstream_http_error'
    if re.search(r"you.ve been blocked by network security|verify you are human|just a moment\.\.\.", content, re.I):
        return 'access_challenge'
    return ''


def collection_is_current(data, signature):
    if data.get('collect_signature') != signature or data.get('total_sources', 0) == 0:
        return False
    return all(not content_error(source.get('content'), kind)
               for kind, key in [('youtube', 'videos'), ('web', 'pages')]
               for source in data.get('sources', {}).get(kind, {}).get(key, []))
