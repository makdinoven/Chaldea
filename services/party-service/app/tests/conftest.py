"""Test bootstrap for party-service.

Adds the app directory to sys.path (bare imports like `import config`) and sets
dummy DB env vars BEFORE config is imported — Pydantic BaseSettings requires
DB_HOST/DB_USERNAME/DB_PASSWORD/DB_DATABASE with no defaults. The real MySQL URL
is never used: the tests run on an in-memory SQLite engine and mock character
lookups. `setdefault` keeps the container's real env when running locally.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
