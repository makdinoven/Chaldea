"""
Fixtures for autobattle-service tests.

Sets required environment variables and patches external modules
before any service module is imported.
"""

import os
import sys

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("BATTLE_SERVICE_URL", "http://localhost:8010")

# Add the app directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
