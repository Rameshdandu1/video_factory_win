"""PostgreSQL engine construction at the infrastructure boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Validated database configuration owned by the infrastructure layer."""

    url: str

    def __post_init__(self) -> None:
        if not self.url.startswith("postgresql+asyncpg://"):
            raise ValueError("database URL must use postgresql+asyncpg")

    @classmethod
    def from_environment(cls) -> DatabaseSettings:
        value = os.environ.get("DATABASE_URL")
        if value is None or not value.strip():
            raise RuntimeError("DATABASE_URL must be configured")
        return cls(value)


def create_database_engine(settings: DatabaseSettings) -> AsyncEngine:
    """Create a non-global async engine for an application composition root."""

    return create_async_engine(settings.url, pool_pre_ping=True)
