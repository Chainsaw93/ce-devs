# -*- coding: utf-8 -*-
"""
Test suite for CRM Social Extension module.

This module contains comprehensive tests for all components of the
CRM Social Extension including:
- Model functionality and business logic
- View rendering and user interface
- Website controllers and public pages
- API endpoints and data processing
- Security and permission controls
- Performance and load testing

Test Structure:
- test_res_partner.py: Tests for the extended partner model
- test_website_controller.py: Tests for website functionality
- test_social_scoring.py: Tests for the lead scoring system
- test_marketing_automation.py: Tests for automated features
- test_security.py: Security and permission tests
- test_performance.py: Performance and load tests
- test_integration.py: Integration tests with other modules

Usage:
    Run all tests:
        python -m pytest tests/
    
    Run specific test file:
        python -m pytest tests/test_res_partner.py
    
    Run with coverage:
        python -m pytest --cov=crm_social_extension tests/
    
    Run specific test method:
        python -m pytest tests/test_res_partner.py::TestResPartnerSocial::test_social_score_computation
"""

from . import test_res_partner
from . import test_website_controller
from . import test_social_scoring
from . import test_marketing_automation
from . import test_security
from . import test_performance
from . import test_integration