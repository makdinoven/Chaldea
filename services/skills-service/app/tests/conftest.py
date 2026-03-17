"""
Fixtures for skills-service tests.

Sets DATABASE_URL to an in-memory SQLite before any service module is imported,
preventing the async engine from trying to connect to an unreachable MySQL host.
Also adds the app directory to sys.path so bare imports work.
"""

import os
import sys

# Override DATABASE_URL BEFORE any service module is imported.
# This prevents database.py from creating an aiomysql engine that hangs
# trying to resolve the Docker-internal "mysql" hostname.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

# Prevent RabbitMQ consumer from trying to connect during tests.
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672")

# Add the app directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
