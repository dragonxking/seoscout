"""
YouTube 搜索和提取模块

支持并行搜索和字幕提取
"""

import asyncio
import subprocess
import json
import re
import sys
from typing import List, Dict, Tuple
from youtube_transcript_api import YouTubeTranscriptApi
import requests

from .config import Config
from .models import YouTubeItem
from .utils import format_duration, load_cache, save_cache


class YouTube:
    """YouTube 搜索和提取（支持并行）"""

    def __init__(self):
        self.config = Config

    async def search_batch(self, keywords: List[str], topic_name: str = '') -> Dict[str, List[YouTubeItem]]:
        """
        并行搜索多个关键词（带实时进度反馈）

        Args:
            keywords: 关键词列表
            topic_name: 主题名，用于过滤不相关视频（可选）

        Returns:
            {keyword: [YouTubeItem, ...]}
        """
        print(f"\n🔍 YouTube 搜索: {len(keywords)} 个关键词")
        if topic_name:
            print(f"   主题名过滤: \"{topic_name}\"")

        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(self.config.YOUTUBE_SEARCH_WORKERS)

        # 包装函数：搜索并返回 (keyword, result, error, retry_count)
        async def search_and_tag(keyword: str, index: int, total: int):
            retry_count = 0
            async with semaphore:
                # 开始搜索时立即打印
                print(f"  🔄 [{index}/{total}] 开始搜索: {keyword}")

                for attempt in range(self.config.YOUTUBE_RETRIES):
                    try:
                        # 使用 yt-dlp 搜索（传入 topic_name 优化查询）
                        videos = await self._ytdlp_search(keyword, topic_name=topic_name)

                        # 过滤时长
                        filtered = self._filter_by_duration(videos)

                        # 按主题名过滤
                        if topic_name:
                            filtered = self._filter_by_topic(filtered, topic_name)

                        # 转换为 YouTubeItem
                        items = [self._to_item(v) for v in filtered]

                        return (keyword, items, None, retry_count)

                    except Exception as e:
                        retry_count = attempt + 1
                        if attempt == self.config.YOUTUBE_RETRIES - 1:
                            return (keyword, [], e, retry_count)
                        await asyncio.sleep(2 ** attempt)

        # 创建所有任务
        tasks = [search_and_tag(kw, i+1, len(keywords)) for i, kw in enumerate(keywords)]

        # 实时处理完成的任务
        result_dict = {}
        completed = 0
        total = len(keywords)

        for coro in asyncio.as_completed(tasks):
            keyword, result, error, retry_count = await coro
            completed += 1

            if error:
                retry_info = f" (重试 {retry_count} 次)" if retry_count > 0 else ""
                print(f"  ✗ [{completed}/{total}] {keyword}: {error}{retry_info}")
                result_dict[keyword] = []
            else:
                retry_info = f" (重试 {retry_count} 次)" if retry_count > 0 else ""
                print(f"  ✓ [{completed}/{total}] {keyword}: {len(result)} 个视频{retry_info}")
                result_dict[keyword] = result

        return result_dict

    async def _search_single(self, keyword: str, semaphore, topic_name: str = '') -> List[YouTubeItem]:
        """
        搜索单个关键词

        Args:
            keyword: 关键词
            semaphore: 并发控制信号量
            topic_name: 主题名，用于过滤不相关视频

        Returns:
            YouTubeItem 列表
        """
        async with semaphore:
            for attempt in range(self.config.YOUTUBE_RETRIES):
                try:
                    # 使用 yt-dlp 搜索（传入 topic_name 优化查询）
                    videos = await self._ytdlp_search(keyword, topic_name=topic_name)

                    # 过滤时长
                    filtered = self._filter_by_duration(videos)

                    # 按主题名过滤
                    if topic_name:
                        filtered = self._filter_by_topic(filtered, topic_name)

                    # 转换为 YouTubeItem
                    items = [self._to_item(v) for v in filtered]

                    return items

                except Exception as e:
                    if attempt == self.config.YOUTUBE_RETRIES - 1:
                        raise Exception(f"搜索失败: {e}")
                    await asyncio.sleep(2 ** attempt)

    async def _ytdlp_search(self, keyword: str, topic_name: str = '') -> List[Dict]:
        """
        使用 yt-dlp 搜索视频

        Args:
            keyword: 关键词
            topic_name: 主题名（可选，用于优化搜索查询）

        Returns:
            视频信息列表
        """
        # 搜索策略：连写优先 → 大写+引号回退
        # 例如 "all firing best characters" → "Allfiring best characters"（连写）
        # 如果连写无结果 → '"All Firing" best characters'（大写+引号）
        search_keyword = keyword
        fallback_keyword = None
        if topic_name:
            import re
            topic_lower = topic_name.lower()
            topic_nospace = topic_name.replace(' ', '')
            # 连写形式：Allfiring
            topic_nospace_cased = topic_nospace[:1].upper() + topic_nospace[1:].lower()
            if topic_lower in keyword.lower():
                # 大写+引号形式作为 fallback："All Firing"
                topic_title_cased = topic_name.title()
                fallback_keyword = re.sub(
                    re.escape(topic_name),
                    f'"{topic_title_cased}"',
                    keyword,
                    flags=re.IGNORECASE
                )
                # 主搜索用连写形式
                search_keyword = re.sub(
                    re.escape(topic_name),
                    topic_nospace_cased,
                    keyword,
                    flags=re.IGNORECASE
                )

        search_query = f"ytsearch{self.config.YOUTUBE_INITIAL_RESULTS}:{search_keyword}"

        # 构建命令：用当前解释器运行 yt_dlp 模块，不依赖 PATH 上是否有 yt-dlp
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            search_query,
            "--skip-download",
            "--dump-json",
            "--no-warnings",
            "--ignore-errors",
            "--flat-playlist",  # 只获取基本信息，不获取格式列表（减少 98% 数据量）
        ]

        # 添加代理（搜索阶段）
        proxy_url = self.config.get_proxy_url_for_stage("search")
        if proxy_url:
            cmd.extend(["--proxy", proxy_url])

        # 执行命令
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.config.YOUTUBE_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise Exception("搜索超时")

        # 解析结果
        videos = []
        for line in stdout.decode().strip().split('\n'):
            if line:
                try:
                    data = json.loads(line)
                    videos.append({
                        'title': data.get('title', ''),
                        'video_id': data.get('id', ''),
                        'url': f"https://www.youtube.com/watch?v={data.get('id', '')}",
                        'channel': data.get('uploader', ''),
                        'duration': data.get('duration_string', ''),
                        'duration_seconds': data.get('duration', 0),
                        'view_count': data.get('view_count', 0)
                    })
                except json.JSONDecodeError:
                    continue

        if not videos:
            # 连写搜索无结果时，回退到大写+引号搜索
            if fallback_keyword and fallback_keyword != search_keyword:
                print(f"    🔄 连写搜索无结果，回退大写+引号: \"{fallback_keyword}\"")
                return await self._ytdlp_search(fallback_keyword, topic_name='')
            raise Exception("未找到任何视频")

        return videos

    def _duration_seconds(self, video: Dict) -> float:
        duration = video.get('duration_seconds')
        if duration is None:
            return float('inf')
        return duration

    def _filter_by_duration(self, videos: List[Dict]) -> List[Dict]:
        """
        根据时长过滤视频

        Args:
            videos: 视频列表

        Returns:
            过滤后的视频列表
        """
        if not videos:
            return []

        # 过滤掉超过最大时长的视频
        filtered = [
            v for v in videos
            if self._duration_seconds(v) <= self.config.YOUTUBE_MAX_DURATION
        ]

        # 如果过滤后有视频，返回所有过滤后的视频（不限制数量）
        if filtered:
            return filtered

        # 如果所有视频都超时长，返回时长最短的 1 个
        sorted_by_duration = sorted(
            videos,
            key=self._duration_seconds
        )
        return sorted_by_duration[:1]

    def _filter_by_topic(self, videos: List[Dict], topic_name: str) -> List[Dict]:
        """
        按主题名过滤视频标题，不相关的视频直接丢弃

        Args:
            videos: 视频列表
            topic_name: 主题名（如 "All Firing"）

        Returns:
            过滤后的视频列表
        """
        if not topic_name or not videos:
            return videos

        topic_lower = topic_name.lower()
        topic_nospace = topic_lower.replace(' ', '')
        kept = []
        filtered_out = []

        for v in videos:
            title = v.get('title', '')
            title_lower = title.lower()
            if topic_lower in title_lower or topic_nospace in title_lower:
                kept.append(v)
            else:
                filtered_out.append(v)
                print(f"    🗑️ 过滤: \"{title[:60]}\" (不含 \"{topic_name}\")")

        if not kept:
            print(f"    ⚠️ 所有视频均不含 \"{topic_name}\"，无相关视频")

        # 记录被过滤掉的视频到日志文件
        if filtered_out:
            self._log_filtered(topic_name, filtered_out, source="youtube")

        if not kept:
            return []

        return kept

    def _log_filtered(self, topic_name: str, items: list, source: str = "unknown"):
        """记录被过滤掉的条目到日志文件，便于后期审查"""
        import os
        from pathlib import Path

        log_dir = Path(Config.DATA_DIR) / "out" / "filter_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"filtered_{source}.jsonl"

        entry = {
            "topic_name": topic_name,
            "source": source,
            "filtered_count": len(items),
            "items": [{"title": v.get("title", ""), "url": v.get("url", "")} for v in items]
        }

        with open(log_file, "a", encoding="utf-8") as f:
            import json
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _to_item(self, video: Dict) -> YouTubeItem:
        """
        转换为 YouTubeItem

        Args:
            video: 视频信息字典

        Returns:
            YouTubeItem 对象
        """
        return YouTubeItem(
            title=video.get('title', ''),
            url=video.get('url', ''),
            video_id=video.get('video_id', ''),
            channel=video.get('channel', ''),
            duration=video.get('duration', ''),
            duration_seconds=video.get('duration_seconds', 0),
            view_count=video.get('view_count', 0),
            selected=True
        )

    async def extract_batch(self, items: List[YouTubeItem]) -> List[Tuple[YouTubeItem, str]]:
        """
        并行提取多个视频字幕

        Args:
            items: YouTubeItem 列表

        Returns:
            [(item, content), ...]
        """
        print(f"\n📥 YouTube 提取: {len(items)} 个视频")

        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(self.config.YOUTUBE_EXTRACT_WORKERS)

        # 并行提取
        tasks = [self._extract_single(item, semaphore) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计成功和失败
        success_count = sum(1 for _, content in results if content and not isinstance(content, Exception))
        failed_count = len(items) - success_count

        print(f"  ✓ 成功: {success_count}/{len(items)}")

        # 显示失败统计
        if failed_count > 0:
            print(f"  ✗ 失败: {failed_count}/{len(items)}")
            failed_items = [(item, content) for item, content in results if not content or isinstance(content, Exception)]
            if failed_items and failed_count <= 10:
                # 如果失败数量不多，列出所有失败项
                for item, _ in failed_items:
                    print(f"    - {item.video_id}: {item.title[:50]}...")
            elif failed_items:
                # 失败太多，只显示前5个
                print(f"    显示前5个失败项:")
                for item, _ in failed_items[:5]:
                    print(f"    - {item.video_id}: {item.title[:50]}...")

        return results

    async def _extract_single(self, item: YouTubeItem, semaphore) -> Tuple[YouTubeItem, str]:
        """
        提取单个视频字幕（带缓存）

        Args:
            item: YouTubeItem 对象
            semaphore: 并发控制信号量

        Returns:
            (item, content) 元组
        """
        async with semaphore:
            # 1. 检查缓存
            cache_data = load_cache(item.video_id, "youtube", title=item.title)
            if cache_data and cache_data.get("content"):
                print(f"  💾 缓存命中: {item.title[:50]}...")
                return (item, cache_data["content"])

            # 2. 缓存未命中，提取内容
            for attempt in range(self.config.YOUTUBE_RETRIES):
                try:
                    # 在线程池中运行同步代码
                    loop = asyncio.get_event_loop()
                    content = await loop.run_in_executor(
                        None,
                        self._get_transcript,
                        item.video_id
                    )

                    # 3. 保存到缓存
                    if content:
                        save_cache(item.video_id, "youtube", {
                            "title": item.title,
                            "url": item.url,
                            "video_id": item.video_id,
                            "content": content,
                            "source_type": "youtube"
                        }, title=item.title)

                    return (item, content)

                except Exception as e:
                    if attempt == self.config.YOUTUBE_RETRIES - 1:
                        # 最后一次重试失败，记录并返回空内容
                        print(f"    ✗ {item.video_id}: 重试{self.config.YOUTUBE_RETRIES}次后失败")
                        return (item, "")
                    await asyncio.sleep(2 ** attempt)

    def _get_transcript(self, video_id: str) -> str:
        """
        获取字幕（同步方法，带 IP 轮换重试）

        Args:
            video_id: 视频 ID

        Returns:
            字幕文本
        """
        import time, random

        use_proxy = self.config.use_proxy_for_stage("extract") and self.config.get_proxy_url_for_stage("extract")
        max_retries = self.config.YOUTUBE_RETRIES

        for attempt in range(max_retries):
            try:
                if use_proxy:
                    # 每次重试用不同的 channel 名，获取不同代理 IP
                    base_url = self.config.get_proxy_url_for_stage("extract")
                    # 替换 channel 名加随机后缀，确保每次分配不同 IP
                    unique_tag = f"yt-{video_id[:6]}-{attempt}-{random.randint(1000,9999)}"
                    proxy_url = base_url.replace("channel-extract", f"channel-{unique_tag}")

                    proxies = {"http": proxy_url, "https": proxy_url}
                    session = requests.Session()
                    session.proxies.update(proxies)
                    api = YouTubeTranscriptApi(http_client=session)
                else:
                    api = YouTubeTranscriptApi()

                # 尝试获取字幕（优先中文，然后英文）
                languages = ['zh-Hans', 'zh', 'en']
                try:
                    fetched_transcript = api.fetch(video_id, languages=languages)
                    return " ".join([snippet.text for snippet in fetched_transcript])
                except Exception as e:
                    # 如果指定语言失败，尝试获取任何可用字幕
                    fetched_transcript = api.fetch(video_id)
                    return " ".join([snippet.text for snippet in fetched_transcript])

            except Exception as e:
                error_name = type(e).__name__
                is_ip_blocked = error_name in ("RequestBlocked", "IpBlocked", "SSLError", "ProxyError")

                if is_ip_blocked and use_proxy and attempt < max_retries - 1:
                    # IP 被封，换 IP 重试
                    print(f"    🔄 {video_id}: {error_name}，换 IP 重试 ({attempt+1}/{max_retries})")
                    time.sleep(1)
                    continue
                else:
                    # 非 IP 问题或已达最大重试
                    if attempt == max_retries - 1:
                        print(f"    ⚠️ {video_id}: {error_name}（{max_retries}次重试后失败）")
                    else:
                        print(f"    ⚠️ {video_id}: {error_name}")
                    return ""

        return ""

