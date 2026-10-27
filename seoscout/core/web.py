"""
Web 搜索和提取模块

支持并行搜索和内容提取
"""

import asyncio
import aiohttp
import time
from typing import List, Dict, Tuple
from urllib.parse import urlparse

from .config import Config
from .models import WebItem
from .utils import is_blocked_domain, load_cache, save_cache, get_url_hash
from .cleaner import ContentCleaner
from .steam_news import steam_news_endpoint, official_news_text


class TokenBucket:
    """Token Bucket 速率限制器"""

    def __init__(self, rpm: int):
        """
        初始化速率限制器

        Args:
            rpm: 每分钟请求数
        """
        self.rpm = rpm
        self.tokens = rpm
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """获取令牌（阻塞直到有令牌可用）"""
        async with self.lock:
            while self.tokens < 1:
                await asyncio.sleep(0.1)
                self._refill()
            self.tokens -= 1

    def _refill(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self.last_update

        # 每秒补充 rpm/60 个令牌
        self.tokens = min(self.rpm, self.tokens + elapsed * (self.rpm / 60))
        self.last_update = now


class Web:
    """Web 搜索和提取（支持并行）"""

    def __init__(self):
        self.config = Config
        self.cleaner = ContentCleaner()  # 初始化内容清理器

    async def search_batch(self, keywords: List[str], topic_name: str = '') -> Dict[str, List[WebItem]]:
        """
        并行搜索多个关键词

        Args:
            keywords: 关键词列表
            topic_name: 主题名，用于过滤不相关结果（可选）

        Returns:
            {keyword: [WebItem, ...]}
        """
        print(f"\n🔍 Web 搜索: {len(keywords)} 个关键词")
        if topic_name:
            print(f"   主题名过滤: \"{topic_name}\"")

        # 创建信号量限制并发
        semaphore = asyncio.Semaphore(self.config.WEB_SEARCH_CONCURRENCY)

        # 并行搜索（带并发控制）
        tasks = [self._search_single(kw, semaphore, topic_name) for kw in keywords]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 构建结果字典
        result_dict = {}
        for keyword, result in zip(keywords, results):
            if isinstance(result, Exception):
                print(f"  ✗ {keyword}: {result}")
                result_dict[keyword] = []
            else:
                result_dict[keyword] = result
                print(f"  ✓ {keyword}: {len(result)} 个页面")

        return result_dict

    async def _search_single(self, keyword: str, semaphore, topic_name: str = '') -> List[WebItem]:
        """
        搜索单个关键词

        Args:
            keyword: 关键词
            semaphore: 并发控制信号量

        Returns:
            WebItem 列表
        """
        async with semaphore:
            # 添加小延迟避免触发速率限制
            await asyncio.sleep(0.3)

            try:
                # 调用 Serper API
                url = "https://google.serper.dev/search"
                headers = {
                    "X-API-KEY": self.config.SERPER_API_KEY,
                    "Content-Type": "application/json"
                }
                payload = {
                    "q": keyword,
                    "num": self.config.WEB_SEARCH_TOP_N
                }

                # 获取搜索阶段代理配置
                proxy_url = self.config.get_proxy_url_for_stage("search")

                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers, timeout=30, proxy=proxy_url) as response:
                        if response.status != 200:
                            raise Exception(f"Serper API 返回错误: {response.status}")

                        data = await response.json()
                        results = data.get("organic", [])

                # 过滤屏蔽域名
                filtered = [
                    r for r in results
                    if not is_blocked_domain(r.get('link', ''), self.config.BLOCKED_DOMAINS)
                ]

                # Web results are NOT filtered by topic_name
                # (only YouTube results are topic-filtered)

                # 转换为 WebItem
                items = []
                for r in filtered[:self.config.WEB_SEARCH_TOP_N]:
                    domain = urlparse(r.get('link', '')).netloc
                    items.append(WebItem(
                        title=r.get('title', ''),
                        url=r.get('link', ''),
                        domain=domain,
                        snippet=r.get('snippet', ''),
                        selected=True
                    ))

                return items

            except Exception as e:
                raise Exception(f"搜索失败: {e}")

    def _log_filtered(self, topic_name: str, items: list, source: str = "web"):
        """记录被过滤掉的条目到日志文件，便于后期审查"""
        import json
        from pathlib import Path

        log_dir = Path(self.config.DATA_DIR) / "out" / "filter_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"filtered_{source}.jsonl"

        entry = {
            "topic_name": topic_name,
            "source": source,
            "filtered_count": len(items),
            "items": [{"title": r.get("title", ""), "link": r.get("link", "")} for r in items]
        }

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    async def extract_batch(self, items: List[WebItem]) -> List[Tuple[WebItem, str]]:
        """
        并行提取多个页面内容

        Args:
            items: WebItem 列表

        Returns:
            [(item, content), ...]
        """
        print(f"\n📥 Web 提取: {len(items)} 个页面")

        # 创建信号量和速率限制器
        semaphore = asyncio.Semaphore(self.config.JINA_CONCURRENCY)
        rate_limiter = TokenBucket(self.config.JINA_RPM)

        # 并行提取
        tasks = [self._extract_single(item, semaphore, rate_limiter) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计成功和失败
        success_count = sum(1 for _, content in results if content and not isinstance(content, Exception))
        print(f"  ✓ 成功: {success_count}/{len(items)}")

        return results

    async def _extract_single(self, item: WebItem, semaphore, rate_limiter) -> Tuple[WebItem, str]:
        """
        提取单个页面内容（带缓存和重试）

        Args:
            item: WebItem 对象
            semaphore: 并发控制信号量
            rate_limiter: 速率限制器

        Returns:
            (item, content) 元组
        """
        async with semaphore:
            # 1. 检查缓存
            url_hash = get_url_hash(item.url)
            cache_data = load_cache(url_hash, "web", title=item.title)
            if cache_data and cache_data.get("content"):
                print(f"  💾 缓存命中: {item.title[:50]}...")
                return (item, cache_data["content"])

            # 2. 缓存未命中，提取内容（带重试）
            proxy_url = self.config.get_proxy_url_for_stage("extract")
            for attempt in range(self.config.WEB_EXTRACT_RETRIES):
                # 速率限制
                await rate_limiter.acquire()

                try:
                    # 使用 Jina Reader
                    jina_url = f"https://r.jina.ai/{item.url}"
                    headers = {}

                    if self.config.JINA_API_KEY:
                        headers["Authorization"] = f"Bearer {self.config.JINA_API_KEY}"

                    async with aiohttp.ClientSession() as session:
                        async with session.get(jina_url, headers=headers, timeout=30, proxy=proxy_url) as response:
                            # HTTP 错误处理
                            if response.status != 200:
                                if attempt < self.config.WEB_EXTRACT_RETRIES - 1:
                                    await asyncio.sleep(2 ** attempt)  # 指数退避：2s, 4s, 8s
                                    continue
                                break

                            content = await response.text()

                            # 内容长度检查
                            if len(content.strip()) < 500:
                                if attempt < self.config.WEB_EXTRACT_RETRIES - 1:
                                    await asyncio.sleep(2 ** attempt)
                                    continue
                                break

                            # 清理内容（移除导航链接、广告等）
                            cleaned_content = self.cleaner.clean(content)

                            # 3. 保存到缓存
                            save_cache(url_hash, "web", {
                                "title": item.title,
                                "url": item.url,
                                "domain": item.domain,
                                "content": cleaned_content,  # 保存清理后的内容
                                "source_type": "web"
                            }, title=item.title)

                            return (item, cleaned_content)

                except Exception as e:
                    if attempt == self.config.WEB_EXTRACT_RETRIES - 1:
                        # Exhausted reader attempts; try the limited official fallback below.
                        break
                    await asyncio.sleep(2 ** attempt)  # 指数退避

            # Jina may be unavailable even when the original official source is reachable.
            # Limit this fallback to Steam app news, with publisher announcements only.
            return await self._steam_news_fallback(item, url_hash, proxy_url)

    async def _steam_news_fallback(self, item: WebItem, url_hash: str, proxy_url=None):
        endpoint = steam_news_endpoint(item.url)
        if not endpoint:
            return (item, "")
        appid, api_url = endpoint
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=30, proxy=proxy_url) as response:
                    if response.status != 200:
                        return (item, "")
                    payload = await response.json(content_type=None)
            content = official_news_text(payload, appid)
            if not content:
                return (item, "")
            save_cache(url_hash, "web", {
                "title": item.title, "url": item.url, "domain": item.domain,
                "content": content, "source_type": "steam_official_news_api",
                "transport_url": api_url,
            }, title=item.title)
            print(f"  ✓ Steam official-news API fallback: {item.title}")
            return (item, content)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
            return (item, "")

