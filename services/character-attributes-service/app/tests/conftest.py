"""
Fixtures for character-attributes-service tests.

Adds the app directory to sys.path so bare imports work.
Stubs out aio_pika so that importing rabbitmq_consumer (from main.py)
does not fail when the package is not installed in the test environment.
"""

import sys
import os
from unittest.mock import MagicMock

# Stub aio_pika before any app imports so rabbitmq_consumer can be loaded
sys.modules.setdefault("aio_pika", MagicMock())

# Add the app directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set DB env vars BEFORE importing config/database — Pydantic BaseSettings
# requires DB_HOST, DB_USERNAME, DB_PASSWORD, DB_DATABASE (no defaults).
# The actual MySQL URL is never used because test files patch database.engine.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
