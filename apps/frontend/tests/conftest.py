"""Pytest configuration for integration tests with real PostgreSQL database.

This module provides fixtures for connecting to the test PostgreSQL instance
exposed through the cluster gateway at ollyscale-db.ollyscale.test:5432
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.storage.postgres_orm import PostgresStorage


@pytest.fixture(scope="session")
def postgres_connection_string():
    """Get PostgreSQL connection string from environment or Kubernetes secret.

    Set POSTGRES_PASSWORD environment variable to skip cluster access.
    Example: POSTGRES_PASSWORD=password poetry run pytest ...
    """
    # Use external gateway endpoint (kafka-listener port 9094)
    host = os.getenv("POSTGRES_HOST", "ollyscale-db.ollyscale.test")
    port = os.getenv("POSTGRES_PORT", "9094")
    user = os.getenv("POSTGRES_USER", "ollyscale")
    database = os.getenv("POSTGRES_DB", "ollyscale")

    # Get password from environment or Kubernetes secret
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        try:
            import subprocess

            result = subprocess.run(
                ["kubectl", "get", "secret", "ollyscale-db-app", "-n", "ollyscale", "-o", "jsonpath={.data.password}"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            import base64

            password = base64.b64decode(result.stdout).decode("utf-8")
        except Exception as e:
            pytest.skip(f"Cluster not available and POSTGRES_PASSWORD not set: {e}")

    # SSL mode for TLS connection through gateway
    sslmode = os.getenv("POSTGRES_SSLMODE", "require")

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}?sslmode={sslmode}"


@pytest_asyncio.fixture
async def postgres_engine(postgres_connection_string):
    """Create async SQLAlchemy engine for tests."""
    engine = create_async_engine(
        postgres_connection_string,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def postgres_session(postgres_engine):
    """Create async database session for tests."""
    async with AsyncSession(postgres_engine) as session:
        yield session


@pytest_asyncio.fixture
async def postgres_storage(postgres_connection_string):
    """Create PostgresStorage instance connected to test database."""
    storage = PostgresStorage(postgres_connection_string)
    await storage.connect()

    yield storage

    await storage.close()


@pytest_asyncio.fixture
async def clean_database(postgres_session):
    """Clean test data from database before/after tests."""
    # Clean before test
    await postgres_session.execute("TRUNCATE TABLE spans_fact, logs_fact, metrics_fact CASCADE")
    await postgres_session.commit()

    yield

    # Clean after test
    await postgres_session.execute("TRUNCATE TABLE spans_fact, logs_fact, metrics_fact CASCADE")
    await postgres_session.commit()
