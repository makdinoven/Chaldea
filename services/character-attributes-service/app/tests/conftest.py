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
