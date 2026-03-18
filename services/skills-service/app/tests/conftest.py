"""
Fixtures for skills-service tests.

Sets DATABASE_URL to an in-memory SQLite before any service module is imported,
preventing the async engine from trying to connect to an unreachable MySQL host.
Also adds the app directory to sys.path so bare imports work.
"""

import os
import sys

# Override DB env vars BEFORE any service module is imported.
# config.py (Pydantic BaseSettings) requires DB_HOST, DB_USERNAME,
# DB_PASSWORD, DB_DATABASE — they have no defaults (fail-fast design).
# Individual test files patch database.engine after import, so the actual
# MySQL URL constructed by settings.DATABASE_URL is never used at runtime.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

# Prevent RabbitMQ consumer from trying to connect during tests.
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672")

# Add the app directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
