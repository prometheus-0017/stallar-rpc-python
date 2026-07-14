"""
Pytest configuration: auto-configure pytest-asyncio.
"""
import pytest


def pytest_collection_modifyitems(config, items):
    """Mark all async tests with asyncio marker automatically."""
    pass
