# -*- coding: utf-8 -*-
{
    'name': 'CRM Social Media Extension',
    'version': '18.0.1.0.0',
    'category': 'Customer Relationship Management',
    'summary': 'Enhanced CRM with social media integration, lead scoring and marketing automation',
    'description': """
CRM Social Media Extension
==========================

This module extends the CRM functionality with comprehensive social media features:

Core Features:
-------------
• Social Media URLs: Register Facebook, LinkedIn, and Twitter URLs for customers
• Social Tab: Dedicated tab in customer profile with social media icons
• Profile Completion: Visual indicator for complete social profiles
• Profile Filtering: Filter customers by profile completion status
• Customer Promotion: Public website page showcasing customers with social data
• Advanced Search: Search customers by name and social media accounts

Marketing Features:
------------------
• Lead Scoring: Automatic 0-100 scoring based on social profile completeness
• Marketing Activities: Automated follow-up activities for incomplete profiles
• Social Engagement: Track social media engagement levels
• Automated Tasks: Generate sales team tasks for social media follow-up

Technical Features:
------------------
• Unit Tests: Comprehensive Python and QUnit test coverage
• Performance Optimized: Efficient database queries and caching
• Multi-website Compatible: Full multi-website support
• Responsive Design: Mobile-friendly interfaces
• SEO Optimized: SEO-friendly customer promotion pages
    """,
    'author': 'Javier',
    'website': 'https://cuban.engineer/',
    'depends': [
        'base',
        'crm',
        'website',
        'mail',
        'portal',
        'marketing_automation',  # For advanced marketing features
        'sales_team',
        'board',
    ],
    'data': [
        'data/social_scoring_data.xml',
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/website_templates.xml',
        'views/crm_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'crm_social_extension/static/src/css/social_fields.css',
            'crm_social_extension/static/src/js/social_widget.js',
            'crm_social_extension/static/src/xml/social_templates.xml',
        ],
        'web.assets_frontend': [
            'crm_social_extension/static/src/css/website_style.css',
            'crm_social_extension/static/src/js/customer_search.js',
        ],
        'web.qunit_suite_tests': [
            'crm_social_extension/static/tests/**/*',
        ],
    },
    'demo': [
        'demo/res_partner_demo.xml',
    ],
    'icon': 'crm_social_extension/static/description/icon.png',
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
    'post_init_hook': '_post_init_hook',
}