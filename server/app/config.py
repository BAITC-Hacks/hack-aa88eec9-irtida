import os
import math
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv('DATABASE_URL', f'sqlite:///{ROOT / "data/career-quest.db"}'))
    demo_mode: bool = field(default_factory=lambda: os.getenv('DEMO_MODE', 'false').lower() == 'true')
    # TestClient uses a non-IP hostname. Never enable this through environment.
    allow_test_setup: bool = False
    cookie_secure: bool = field(default_factory=lambda: os.getenv('COOKIE_SECURE', 'false').lower() == 'true')
    provider: str = field(default_factory=lambda: os.getenv('AI_PROVIDER', 'rules'))
    openai_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', ''), repr=False)
    openai_model: str = field(default_factory=lambda: os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'))
    nvidia_key: str = field(default_factory=lambda: os.getenv('NVIDIA_API_KEY', ''), repr=False)
    nvidia_model: str = field(default_factory=lambda: os.getenv('NVIDIA_MODEL', 'meta/llama-3.3-70b-instruct'))
    timeout: float = field(default_factory=lambda: float(os.getenv('AI_TIMEOUT_SECONDS', '7')))
    per_minute: int = field(default_factory=lambda: int(os.getenv('AI_REQUESTS_PER_MINUTE', '6')))
    per_day: int = field(default_factory=lambda: int(os.getenv('AI_REQUESTS_PER_DAY', '300')))
    cloud_data_approved: bool = field(default_factory=lambda: os.getenv('AI_DATA_POLICY_APPROVED', '').lower() == 'true')
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: tuple(os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173').split(',')))

    def __post_init__(self):
        if self.provider not in {'rules', 'openai', 'nvidia'}:
            raise ValueError('AI_PROVIDER must be rules, openai or nvidia')
        if not self.database_url.startswith('sqlite:///'):
            raise ValueError('This starter currently supports SQLite only')
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError('AI_TIMEOUT_SECONDS must be a positive finite number')
        self.timeout = min(8.0, self.timeout)
        if self.per_minute < 0 or self.per_day < 0:
            raise ValueError('AI request limits must be nonnegative')
        self.allowed_origins = tuple(origin.strip() for origin in self.allowed_origins if origin.strip())
