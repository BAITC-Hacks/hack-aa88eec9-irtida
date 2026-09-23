import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv('DATABASE_URL', f'sqlite:///{ROOT / "data/career-quest.db"}'))
    demo_mode: bool = field(default_factory=lambda: os.getenv('DEMO_MODE', 'true').lower() == 'true')
    cookie_secure: bool = field(default_factory=lambda: os.getenv('COOKIE_SECURE', 'false').lower() == 'true')
    provider: str = field(default_factory=lambda: os.getenv('AI_PROVIDER', 'rules'))
    openai_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', ''))
    openai_model: str = field(default_factory=lambda: os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'))
    nvidia_key: str = field(default_factory=lambda: os.getenv('NVIDIA_API_KEY', ''))
    nvidia_model: str = field(default_factory=lambda: os.getenv('NVIDIA_MODEL', 'meta/llama-3.3-70b-instruct'))
    timeout: float = field(default_factory=lambda: min(8.0, max(0.1, float(os.getenv('AI_TIMEOUT_SECONDS', '7')))))
    per_minute: int = field(default_factory=lambda: int(os.getenv('AI_REQUESTS_PER_MINUTE', '6')))
    per_day: int = field(default_factory=lambda: int(os.getenv('AI_REQUESTS_PER_DAY', '300')))
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: tuple(os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173').split(',')))

    def __post_init__(self):
        if self.provider not in {'rules', 'openai', 'nvidia'}:
            raise ValueError('AI_PROVIDER must be rules, openai or nvidia')
        if not self.database_url.startswith('sqlite:///'):
            raise ValueError('This starter currently supports SQLite only')
