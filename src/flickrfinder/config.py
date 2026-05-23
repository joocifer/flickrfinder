from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    api_key: str
    api_secret: str
    host: str
    port: int
    data_dir: Path

    @property
    def originals_dir(self) -> Path:
        return self.data_dir / "originals"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "flickrfinder.db"


def load_config() -> Config:
    load_dotenv()
    api_key = os.environ.get("FLICKR_API_KEY", "").strip()
    api_secret = os.environ.get("FLICKR_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError(
            "FLICKR_API_KEY and FLICKR_API_SECRET must be set "
            "(copy .env.example to .env and fill them in). "
            "Get a key at https://www.flickr.com/services/apps/create/"
        )
    data_dir = Path(os.environ.get("FLICKRFINDER_DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        api_key=api_key,
        api_secret=api_secret,
        host=os.environ.get("FLICKRFINDER_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLICKRFINDER_PORT", "8765")),
        data_dir=data_dir,
    )
