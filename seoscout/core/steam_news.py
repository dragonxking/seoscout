"""Official announcement fallback for Steam community app/news pages."""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlencode


def steam_news_endpoint(url: str):
    parsed = urlsplit(url)
    if parsed.hostname != 'steamcommunity.com':
        return None
    match = re.fullmatch(r'/app/(\d+)(?:/allnews)?/?', parsed.path)
    if not match:
        return None
    appid = int(match.group(1))
    query = urlencode({'appid': appid, 'count': 20, 'maxlength': 0,
                       'feeds': 'steam_community_announcements', 'format': 'json'})
    return appid, 'https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?' + query


def official_news_text(payload: dict, appid: int) -> str:
    news = payload.get('appnews', {})
    if news.get('appid') != appid:
        return ''
    blocks = []
    for item in news.get('newsitems', []):
        # The API can contain third-party news; hosting on Steam does not make it official.
        if item.get('feedname') != 'steam_community_announcements':
            continue
        body = item.get('contents', '').strip()
        if not body:
            continue
        date = datetime.fromtimestamp(item['date'], timezone.utc).isoformat()
        blocks.append(f"Title: {item['title']}\nPublished UTC: {date}\n"
                      f"Source: {item['url']}\nAuthor: {item.get('author', '')}\n\n{body}")
    return '\n\n---\n\n'.join(blocks)
