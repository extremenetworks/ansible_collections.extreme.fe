# Unit tests conftest for extreme.fe collection
"""Pytest configuration and shared fixtures for unit tests."""

import sys
from pathlib import Path

import pytest
from unittest.mock import MagicMock

# Add the collection root to Python path for imports
COLLECTION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(COLLECTION_ROOT) not in sys.path:
    sys.path.insert(0, str(COLLECTION_ROOT))


@pytest.fixture
def mock_module():
    """Create a mock AnsibleModule instance."""
    mock = MagicMock()
    mock.check_mode = False
    mock._socket_path = "/tmp/mock_socket"
    mock.params = {}
    return mock


@pytest.fixture
def mock_connection():
    """Create a mock Connection object."""
    mock = MagicMock()
    mock.send_request = MagicMock(return_value={})
    return mock
