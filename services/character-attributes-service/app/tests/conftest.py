"""
Fixtures for character-attributes-service tests.

Adds the app directory to sys.path so bare imports work.
"""

import sys
import os

# Add the app directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
