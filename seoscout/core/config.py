"""
Unified configuration management.

Loads all config from a .env file in the current working directory.
Data is stored under OUTPUT_DIR/<project_name>/ for isolation.
"""

import os
from dotenv import load_dotenv


class Config:
    """Unified configuration management"""

    # Paths — set by init()
    DATA_DIR = None
    OUT_DIR = None
    BASE_DIR = None
    CACHE_DIR = None
    LOG_DIR = None

    # ============================================================
    # API Keys (loaded from .env in init())
    # ============================================================
    SERPER_API_KEY = ""
    JINA_API_KEY = ""

    # ============================================================
    # Output
    # ============================================================
    OUTPUT_DIR = "./output"

    # ============================================================
    # Proxy configuration
    # ============================================================
    TUNNEL_HOST = ""
    TUNNEL_PORT = 18866
    TUNNEL_USER = ""
    TUNNEL_PASS = ""
    USE_PROXY = False

    TUNNEL_PROXY_FORMAT = "tagged"
    TUNNEL_CHANNEL_PREFIX = "channel"
    TUNNEL_TTL = 60

    USE_PROXY_FOR_SEARCH = ""
    USE_PROXY_FOR_EXTRACT = ""

    # ============================================================
    # YouTube configuration
    # ============================================================
    YOUTUBE_INITIAL_RESULTS = 2
    YOUTUBE_MAX_RESULTS = 1
    YOUTUBE_MAX_DURATION = 3600
    YOUTUBE_EXTRACT_TOP_K = 1

    YOUTUBE_SEARCH_WORKERS = 10
    YOUTUBE_EXTRACT_WORKERS = 15
    YOUTUBE_RETRIES = 3
    YOUTUBE_TIMEOUT = 180

    # ============================================================
    # Web configuration
    # ============================================================
    WEB_SEARCH_TOP_N = 10
    WEB_EXTRACT_TOP_K = 1
    WEB_EXTRACT_WORKERS = 20
    WEB_EXTRACT_RETRIES = 3
    WEB_SEARCH_CONCURRENCY = 5
    JINA_RPM = 200
    JINA_CONCURRENCY = 20

    # ============================================================
    # LLM API (generate + translate)
    # ============================================================
    LLM_API_KEY = ""
    LLM_API_BASE_URL = "https://api.apifast.tech/v1"
    LLM_MODEL = "gemini-2.5-flash"
    LLM_TEMPERATURE = 0.7
    LLM_MAX_TOKENS = 24576
    LLM_TIMEOUT = 300
    LLM_RETRY_ATTEMPTS = 2
    LLM_RETRY_DELAY = 5
    # Optional provider-specific thinking toggle; empty preserves provider defaults.
    LLM_THINKING = ""

    # ============================================================
    # Generate concurrency
    # ============================================================
    GENERATE_BATCH_SIZE = 100
    GENERATE_CONCURRENT_LIMIT = 10

    # ============================================================
    # Translate concurrency
    # ============================================================
    TRANSLATE_BATCH_SIZE = 10
    TRANSLATE_BATCH_DELAY = 1

    # ============================================================
    # General
    # ============================================================
    SEARCH_MAX_RETRIES = 3
    SEARCH_RETRY_DELAY = 2

    BLOCKED_DOMAINS = {"youtube.com", "youtu.be", "reddit.com", "discord.com"}

    _initialized = False

    @classmethod
    def init(cls, project: str):
        """
        Initialize config for a project.

        Args:
            project: Project name (e.g. "my-site"). Data will be stored
                     under OUTPUT_DIR/<project>/.
        """
        # Load .env from current working directory
        load_dotenv()

        # Sanitize project name
        project_dir = project.replace('.', '_').replace('/', '_')

        # Read output root
        cls.OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")

        # Set up project paths
        cls.DATA_DIR = os.path.join(cls.OUTPUT_DIR, project_dir)
        cls.OUT_DIR = os.path.join(cls.DATA_DIR, "out")
        cls.BASE_DIR = cls.OUT_DIR
        cls.CACHE_DIR = os.path.join(cls.OUT_DIR, "cache")
        cls.LOG_DIR = os.path.join(cls.DATA_DIR, "logs")

        os.makedirs(cls.OUT_DIR, exist_ok=True)
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
        os.makedirs(cls.LOG_DIR, exist_ok=True)

        # API Keys
        cls.SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
        cls.JINA_API_KEY = os.getenv("JINA_API_KEY", "")

        # Proxy
        cls.TUNNEL_HOST = os.getenv("TUNNEL_HOST", "")
        cls.TUNNEL_PORT = int(os.getenv("TUNNEL_PORT", "18866"))
        cls.TUNNEL_USER = os.getenv("TUNNEL_USER", "")
        cls.TUNNEL_PASS = os.getenv("TUNNEL_PASS", "")
        cls.USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"

        cls.TUNNEL_PROXY_FORMAT = os.getenv("TUNNEL_PROXY_FORMAT", "tagged").lower()
        cls.TUNNEL_CHANNEL_PREFIX = os.getenv("TUNNEL_CHANNEL_PREFIX", "channel")
        cls.TUNNEL_TTL = int(os.getenv("TUNNEL_TTL", "60"))

        cls.USE_PROXY_FOR_SEARCH = os.getenv("USE_PROXY_FOR_SEARCH", "").lower()
        cls.USE_PROXY_FOR_EXTRACT = os.getenv("USE_PROXY_FOR_EXTRACT", "").lower()

        # YouTube
        cls.YOUTUBE_INITIAL_RESULTS = int(os.getenv("YOUTUBE_INITIAL_SEARCH_RESULTS", "2"))
        cls.YOUTUBE_MAX_RESULTS = int(os.getenv("YOUTUBE_MAX_RESULTS_AFTER_FILTER", "1"))
        cls.YOUTUBE_MAX_DURATION = int(os.getenv("YOUTUBE_MAX_DURATION", "3600"))
        cls.YOUTUBE_EXTRACT_TOP_K = int(os.getenv("YOUTUBE_EXTRACT_TOP_K", "1"))

        cls.YOUTUBE_SEARCH_WORKERS = int(os.getenv("YOUTUBE_SEARCH_WORKERS", "10"))
        cls.YOUTUBE_EXTRACT_WORKERS = int(os.getenv("YOUTUBE_TRANSCRIPT_WORKERS", "15"))
        cls.YOUTUBE_RETRIES = int(os.getenv("YOUTUBE_TRANSCRIPT_RETRIES", "3"))
        cls.YOUTUBE_TIMEOUT = int(os.getenv("YOUTUBE_SEARCH_TIMEOUT", "180"))

        # Web
        cls.WEB_SEARCH_TOP_N = int(os.getenv("WEB_SEARCH_TOP_N", "10"))
        cls.WEB_EXTRACT_TOP_K = int(os.getenv("WEB_EXTRACT_TOP_K", "1"))
        cls.WEB_EXTRACT_WORKERS = int(os.getenv("JINA_CONCURRENCY", "20"))
        cls.WEB_EXTRACT_RETRIES = int(os.getenv("WEB_EXTRACT_RETRIES", "3"))
        cls.WEB_SEARCH_CONCURRENCY = int(os.getenv("WEB_SEARCH_CONCURRENCY", "5"))
        cls.JINA_RPM = int(os.getenv("JINA_RPM", "200"))
        cls.JINA_CONCURRENCY = int(os.getenv("JINA_CONCURRENCY", "20"))

        # General
        cls.SEARCH_MAX_RETRIES = int(os.getenv("SEARCH_MAX_RETRIES", "3"))
        cls.SEARCH_RETRY_DELAY = int(os.getenv("SEARCH_RETRY_DELAY", "2"))

        # LLM API (generate + translate)
        cls.LLM_API_KEY = os.getenv("LLM_API_KEY", "")
        cls.LLM_THINKING = os.getenv("LLM_THINKING", "").strip().lower()
        cls.LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "https://api.apifast.tech/v1")
        cls.LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        cls.LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        cls.LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "24576"))
        cls.LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "300"))
        cls.LLM_RETRY_ATTEMPTS = int(os.getenv("LLM_RETRY_ATTEMPTS", "2"))
        cls.LLM_RETRY_DELAY = int(os.getenv("LLM_RETRY_DELAY", "5"))

        # Generate concurrency
        cls.GENERATE_BATCH_SIZE = int(os.getenv("GENERATE_BATCH_SIZE", "100"))
        cls.GENERATE_CONCURRENT_LIMIT = int(os.getenv("GENERATE_CONCURRENT_LIMIT", "10"))

        # Translate concurrency
        cls.TRANSLATE_BATCH_SIZE = int(os.getenv("TRANSLATE_BATCH_SIZE", "10"))
        cls.TRANSLATE_BATCH_DELAY = int(os.getenv("TRANSLATE_BATCH_DELAY", "1"))

        cls.BLOCKED_DOMAINS = set(
            d.strip()
            for d in os.getenv("BLOCKED_DOMAINS",
                "youtube.com,youtu.be,reddit.com,discord.com").split(",")
            if d.strip()
        )

        cls._initialized = True

    @classmethod
    def get_proxy_url(cls) -> str:
        if not cls.USE_PROXY or not cls.TUNNEL_HOST:
            return None

        if cls.TUNNEL_PROXY_FORMAT == "tagged":
            channel = f"{cls.TUNNEL_CHANNEL_PREFIX}-default"
            return f"http://{cls.TUNNEL_USER}:{cls.TUNNEL_PASS}:{channel}:{cls.TUNNEL_TTL}@{cls.TUNNEL_HOST}:{cls.TUNNEL_PORT}"
        else:
            return f"http://{cls.TUNNEL_USER}:{cls.TUNNEL_PASS}@{cls.TUNNEL_HOST}:{cls.TUNNEL_PORT}"

    @classmethod
    def use_proxy_for_stage(cls, stage: str) -> bool:
        if stage == "search":
            if cls.USE_PROXY_FOR_SEARCH in ("true", "false"):
                return cls.USE_PROXY_FOR_SEARCH == "true"
            return cls.USE_PROXY
        elif stage == "extract":
            if cls.USE_PROXY_FOR_EXTRACT in ("true", "false"):
                return cls.USE_PROXY_FOR_EXTRACT == "true"
            return cls.USE_PROXY
        else:
            return cls.USE_PROXY

    @classmethod
    def get_proxy_url_for_stage(cls, stage: str) -> str:
        if not cls.use_proxy_for_stage(stage) or not cls.TUNNEL_HOST:
            return None

        if cls.TUNNEL_PROXY_FORMAT == "tagged":
            channel = f"{cls.TUNNEL_CHANNEL_PREFIX}-{stage}"
            return f"http://{cls.TUNNEL_USER}:{cls.TUNNEL_PASS}:{channel}:{cls.TUNNEL_TTL}@{cls.TUNNEL_HOST}:{cls.TUNNEL_PORT}"
        else:
            return f"http://{cls.TUNNEL_USER}:{cls.TUNNEL_PASS}@{cls.TUNNEL_HOST}:{cls.TUNNEL_PORT}"

    @classmethod
    def validate(cls) -> bool:
        errors = []

        if not cls.SERPER_API_KEY:
            errors.append("SERPER_API_KEY not set")

        if not cls.JINA_API_KEY:
            errors.append("JINA_API_KEY not set (optional, but recommended for higher rate limits)")

        if cls.USE_PROXY and not cls.TUNNEL_HOST:
            errors.append("USE_PROXY=true but TUNNEL_HOST not set")

        if errors:
            print("⚠️  Config warnings:")
            for error in errors:
                print(f"  - {error}")
            return False

        return True

    @classmethod
    def print_summary(cls):
        print("\n" + "=" * 70)
        print("  Configuration")
        print("=" * 70)
        print(f"Data dir:    {cls.DATA_DIR}")
        print(f"Output dir:  {cls.OUT_DIR}")
        print(f"\nYouTube:")
        print(f"  - Initial results: {cls.YOUTUBE_INITIAL_RESULTS}")
        print(f"  - Max results:     {cls.YOUTUBE_MAX_RESULTS}")
        print(f"  - Max duration:    {cls.YOUTUBE_MAX_DURATION}s")
        print(f"  - Extract top-k:   {cls.YOUTUBE_EXTRACT_TOP_K}")
        print(f"  - Search workers:  {cls.YOUTUBE_SEARCH_WORKERS}")
        print(f"  - Extract workers: {cls.YOUTUBE_EXTRACT_WORKERS}")
        print(f"\nWeb:")
        print(f"  - Search results:  {cls.WEB_SEARCH_TOP_N}")
        print(f"  - Search workers:  {cls.WEB_SEARCH_CONCURRENCY}")
        print(f"  - Extract top-k:   {cls.WEB_EXTRACT_TOP_K}")
        print(f"  - Jina RPM:        {cls.JINA_RPM}")
        print(f"  - Jina concurrency:{cls.JINA_CONCURRENCY}")
        print(f"\nGeneral:")
        print(f"  - Blocked domains: {len(cls.BLOCKED_DOMAINS)}")
        print(f"  - Use proxy:       {'yes' if cls.USE_PROXY else 'no'}")
        print(f"  - Search retries:  {cls.SEARCH_MAX_RETRIES}")
        print(f"\nLLM:")
        print(f"  - Model:           {cls.LLM_MODEL}")
        print(f"  - API base:        {cls.LLM_API_BASE_URL}")
        print(f"  - Max tokens:      {cls.LLM_MAX_TOKENS}")
        print(f"  - Gen batch size:  {cls.GENERATE_BATCH_SIZE}")
        print(f"  - Xlate batch:     {cls.TRANSLATE_BATCH_SIZE}")
        print("=" * 70 + "\n")
