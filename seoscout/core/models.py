"""
数据模型

定义 YouTube 和 Web 搜索结果的数据结构
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class YouTubeItem:
    """YouTube 视频项"""
    title: str
    url: str
    video_id: str
    channel: str
    duration: str
    duration_seconds: int
    view_count: int
    selected: bool = True
    relevance_score: int = 0
    selection_reason: str = ''
    snippet: str = ''
    source: str = 'youtube_search'

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)


@dataclass
class WebItem:
    """Web 页面项"""
    title: str
    url: str
    domain: str
    snippet: str
    selected: bool = True
    relevance_score: int = 0
    selection_reason: str = ''
    original_url: str = ''

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)


@dataclass
class KeywordData:
    """单个关键词的搜索结果"""
    keyword: str
    youtube: Dict  # {"count": int, "items": List[YouTubeItem]}
    web: Dict      # {"count": int, "items": List[WebItem]}

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "keyword": self.keyword,
            "youtube": self.youtube,
            "web": self.web
        }


@dataclass
class PendingReview:
    """待审核的搜索结果"""
    version: str = "2.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    keywords: List[KeywordData] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "keywords": [kw.to_dict() for kw in self.keywords]
        }


@dataclass
class ExtractedContent:
    """提取的内容"""
    type: str  # "youtube" or "web"
    title: str
    url: str
    content: str

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)


@dataclass
class KeywordExtractedData:
    """单个关键词的提取结果"""
    keyword: str
    extracted_at: str
    sources: Dict  # {"youtube": {...}, "web": {...}}
    total_sources: int

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)
