# -*- coding: utf-8 -*-
"""Unit tests for extreme_fe_autosense module."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestExtremeFEAutosense:
    """Test suite for extreme_fe_autosense module."""

    def test_module_import(self):
        """Test that the module can be imported."""
        from plugins.modules import extreme_fe_autosense
        assert hasattr(extreme_fe_autosense, 'DOCUMENTATION')
        assert hasattr(extreme_fe_autosense, 'EXAMPLES')

    def test_module_has_argument_spec(self):
        """Test that module defines argument spec."""
        from plugins.modules import extreme_fe_autosense
        # Module should have main() or run_module() function
        assert hasattr(extreme_fe_autosense, 'main') or hasattr(extreme_fe_autosense, 'run_module')

    def test_documentation_exists(self):
        """Test that DOCUMENTATION string exists and is non-empty."""
        from plugins.modules import extreme_fe_autosense
        
        assert extreme_fe_autosense.DOCUMENTATION is not None
        assert len(extreme_fe_autosense.DOCUMENTATION) > 100
        assert 'module:' in extreme_fe_autosense.DOCUMENTATION
        assert 'extreme_fe_autosense' in extreme_fe_autosense.DOCUMENTATION

    def test_examples_exists(self):
        """Test that EXAMPLES string exists and is non-empty."""
        from plugins.modules import extreme_fe_autosense
        
        assert extreme_fe_autosense.EXAMPLES is not None
        assert len(extreme_fe_autosense.EXAMPLES) > 50

    def test_documentation_has_required_fields(self):
        """Test that DOCUMENTATION contains required Ansible fields."""
        from plugins.modules import extreme_fe_autosense
        
        doc = extreme_fe_autosense.DOCUMENTATION
        # Check for required Ansible documentation fields
        assert 'module:' in doc
        assert 'short_description:' in doc
        assert 'description:' in doc
        assert 'options:' in doc
        assert 'author:' in doc

    def test_state_option_in_documentation(self):
        """Test that state option is documented with correct choices."""
        from plugins.modules import extreme_fe_autosense
        
        doc = extreme_fe_autosense.DOCUMENTATION
        # Verify state choices are documented
        assert 'merged' in doc
        assert 'replaced' in doc
        assert 'deleted' in doc
        assert 'gathered' in doc


class TestExtremeFEAutosenseHelpers:
    """Test helper functions in the autosense module."""

    @pytest.fixture
    def mock_connection(self):
        """Create mock connection for testing."""
        conn = MagicMock()
        conn.send_request = MagicMock(return_value={})
        return conn

    def test_global_settings_documented(self):
        """Test that global_settings is documented."""
        from plugins.modules import extreme_fe_autosense
        
        doc = extreme_fe_autosense.DOCUMENTATION
        
        # Check that global_settings suboption is mentioned
        assert 'global_settings:' in doc
        assert 'fabric_attach' in doc


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
