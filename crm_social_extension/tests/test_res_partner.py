# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase, HttpCase
from odoo.exceptions import ValidationError
from unittest.mock import patch
import logging

_logger = logging.getLogger(__name__)


class TestResPartnerSocial(TransactionCase):
    """Test social media functionality in res.partner model."""

    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner']
        self.partner = self.Partner.create({
            'name': 'Test Customer',
            'is_company': True,
            'email': 'test@example.com',
        })

    def test_social_url_validation_facebook(self):
        """Test Facebook URL validation."""
        # Valid Facebook URLs
        valid_urls = [
            'https://facebook.com/testpage',
            'https://www.facebook.com/testpage',
            'http://facebook.com/testpage',
            'https://fb.com/testpage',
        ]
        
        for url in valid_urls:
            with self.subTest(url=url):
                self.partner.facebook_url = url
                # Should not raise ValidationError
                
        # Invalid Facebook URLs
        invalid_urls = [
            'https://twitter.com/testuser',
            'invalid-url',
            'https://google.com',
        ]
        
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    self.partner.facebook_url = url

    def test_social_url_validation_linkedin(self):
        """Test LinkedIn URL validation."""
        # Valid LinkedIn URLs
        valid_urls = [
            'https://linkedin.com/in/testuser',
            'https://www.linkedin.com/in/testuser',
            'https://linkedin.com/company/testcompany',
        ]
        
        for url in valid_urls:
            with self.subTest(url=url):
                self.partner.linkedin_url = url
                # Should not raise ValidationError
                
        # Invalid LinkedIn URLs
        invalid_urls = [
            'https://facebook.com/testpage',
            'invalid-url',
            'https://linkedin.com/invalid',
        ]
        
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    self.partner.linkedin_url = url

    def test_social_url_validation_twitter(self):
        """Test Twitter URL validation."""
        # Valid Twitter URLs
        valid_urls = [
            'https://twitter.com/testuser',
            'https://www.twitter.com/testuser',
            'https://x.com/testuser',
        ]
        
        for url in valid_urls:
            with self.subTest(url=url):
                self.partner.twitter_url = url
                # Should not raise ValidationError
                
        # Invalid Twitter URLs
        invalid_urls = [
            'https://facebook.com/testpage',
            'invalid-url',
            'https://google.com',
        ]
        
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    self.partner.twitter_url = url

    def test_profile_complete_computation(self):
        """Test profile complete computation."""
        # Initially incomplete
        self.assertFalse(self.partner.is_profile_complete)
        
        # Add Facebook URL
        self.partner.facebook_url = 'https://facebook.com/test'
        self.assertFalse(self.partner.is_profile_complete)
        
        # Add LinkedIn URL
        self.partner.linkedin_url = 'https://linkedin.com/in/test'
        self.assertFalse(self.partner.is_profile_complete)
        
        # Add Twitter URL - now complete
        self.partner.twitter_url = 'https://twitter.com/test'
        self.assertTrue(self.partner.is_profile_complete)
        
        # Remove one URL - becomes incomplete
        self.partner.facebook_url = False
        self.assertFalse(self.partner.is_profile_complete)

    def test_social_score_computation(self):
        """Test social score computation."""
        # Initially 0
        self.assertEqual(self.partner.social_score, 0)
        
        # Add Facebook URL (20 points)
        self.partner.facebook_url = 'https://facebook.com/test'
        self.assertEqual(self.partner.social_score, 20)
        
        # Add LinkedIn URL (20 points)
        self.partner.linkedin_url = 'https://linkedin.com/in/test'
        self.assertEqual(self.partner.social_score, 40)
        
        # Add Twitter URL (20 points)
        self.partner.twitter_url = 'https://twitter.com/test'
        # Now complete, so +20 for completion bonus = 80
        self.assertEqual(self.partner.social_score, 80)
        
        # Set high engagement level (+20 points)
        self.partner.social_engagement_level = 'excellent'
        self.assertEqual(self.partner.social_score, 100)
        
        # Set medium engagement level (+5 points)
        self.partner.social_engagement_level = 'medium'
        self.assertEqual(self.partner.social_score, 85)

    def test_social_media_data_method(self):
        """Test get_social_media_data method."""
        # No social media
        data = self.partner.get_social_media_data()
        self.assertEqual(data, [])
        
        # Add social media URLs
        self.partner.facebook_url = 'https://facebook.com/test'
        self.partner.linkedin_url = 'https://linkedin.com/in/test'
        self.partner.twitter_url = 'https://twitter.com/test'
        
        data = self.partner.get_social_media_data()
        self.assertEqual(len(data), 3)
        
        # Check Facebook data
        facebook_data = next((item for item in data if item['platform'] == 'facebook'), None)
        self.assertIsNotNone(facebook_data)
        self.assertEqual(facebook_data['url'], 'https://facebook.com/test')
        self.assertEqual(facebook_data['icon'], 'fa-facebook')
        self.assertEqual(facebook_data['name'], 'Facebook')

    def test_search_by_social_media(self):
        """Test search by social media functionality."""
        # Create test partners
        partner1 = self.Partner.create({
            'name': 'Company One',
            'facebook_url': 'https://facebook.com/companyone',
        })
        partner2 = self.Partner.create({
            'name': 'Company Two',
            'linkedin_url': 'https://linkedin.com/company/companytwo',
        })
        partner3 = self.Partner.create({
            'name': 'Another Company',
            'twitter_url': 'https://twitter.com/anotherco',
        })
        
        # Search by name
        results = self.Partner.search_by_social_media('Company One')
        self.assertIn(partner1, results)
        
        # Search by Facebook URL
        results = self.Partner.search_by_social_media('companyone')
        self.assertIn(partner1, results)
        
        # Search by LinkedIn URL
        results = self.Partner.search_by_social_media('companytwo')
        self.assertIn(partner2, results)
        
        # Search by Twitter URL
        results = self.Partner.search_by_social_media('anotherco')
        self.assertIn(partner3, results)

    def test_auto_follow_up_creation(self):
        """Test automatic follow-up activity creation."""
        # Set partner as company with auto follow-up enabled
        self.partner.is_company = True
        self.partner.auto_follow_up = True
        
        # Partner has incomplete profile, should create activity
        initial_activities = self.env['mail.activity'].search_count([
            ('res_model', '=', 'res.partner'),
            ('res_id', '=', self.partner.id)
        ])
        
        # Trigger social automation
        self.partner._handle_social_automation()
        
        final_activities = self.env['mail.activity'].search_count([
            ('res_model', '=', 'res.partner'),
            ('res_id', '=', self.partner.id)
        ])
        
        self.assertGreater(final_activities, initial_activities)

    def test_name_get_with_social_score(self):
        """Test name_get method with social score context."""
        self.partner.facebook_url = 'https://facebook.com/test'
        self.partner.linkedin_url = 'https://linkedin.com/in/test'
        self.partner.twitter_url = 'https://twitter.com/test'
        
        # Without context
        name_without_score = self.partner.name_get()[0][1]
        self.assertEqual(name_without_score, 'Test Customer')
        
        # With context
        name_with_score = self.partner.with_context(show_social_score=True).name_get()[0][1]
        self.assertIn('Social:', name_with_score)
        self.assertIn('80', name_with_score)  # Expected score for complete profile

    def test_social_update_timestamp(self):
        """Test that social update timestamp is updated correctly."""
        original_timestamp = self.partner.last_social_update
        
        # Update social field
        self.partner.facebook_url = 'https://facebook.com/test'
        
        # Timestamp should be updated
        self.assertGreater(self.partner.last_social_update, original_timestamp)

    def test_manual_social_score_update(self):
        """Test manual social score update action."""
        self.partner.facebook_url = 'https://facebook.com/test'
        
        # Reset score to 0 manually
        self.partner.social_score = 0
        
        # Call action to recalculate
        result = self.partner.action_update_social_score()
        
        # Should recalculate score
        self.assertEqual(self.partner.social_score, 20)
        self.assertEqual(result['type'], 'ir.actions.client')


class TestWebsiteController(HttpCase):
    """Test website controller functionality."""

    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner']
        
        # Create test customers
        self.customer1 = self.Partner.create({
            'name': 'Test Customer 1',
            'is_company': True,
            'website_published': True,
            'facebook_url': 'https://facebook.com/test1',
            'linkedin_url': 'https://linkedin.com/in/test1',
            'twitter_url': 'https://twitter.com/test1',
        })
        
        self.customer2 = self.Partner.create({
            'name': 'Test Customer 2',
            'is_company': True,
            'website_published': True,
            'facebook_url': 'https://facebook.com/test2',
        })

    def test_customer_showcase_page(self):
        """Test customer showcase page loads correctly."""
        response = self.url_open('/customers')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Our Amazing Customers', response.content)

    def test_customer_detail_page(self):
        """Test customer detail page loads correctly."""
        response = self.url_open(f'/customers/{self.customer1.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.customer1.name.encode(), response.content)

    def test_customer_search_filtering(self):
        """Test customer search and filtering."""
        # Search by name
        response = self.url_open('/customers?search=Test Customer 1')
        self.assertEqual(response.status_code, 200)
        
        # Filter complete profiles
        response = self.url_open('/customers?filter_complete=complete')
        self.assertEqual(response.status_code, 200)
        
        # Filter incomplete profiles
        response = self.url_open('/customers?filter_complete=incomplete')
        self.assertEqual(response.status_code, 200)

    def test_customer_not_found(self):
        """Test customer detail page with invalid ID."""
        response = self.url_open('/customers/99999')
        self.assertEqual(response.status_code, 404)

    def test_unpublished_customer_not_accessible(self):
        """Test that unpublished customers are not accessible."""
        # Create unpublished customer
        unpublished = self.Partner.create({
            'name': 'Unpublished Customer',
            'is_company': True,
            'website_published': False,
        })
        
        response = self.url_open(f'/customers/{unpublished.id}')
        self.assertEqual(response.status_code, 404)


class TestSocialIntegration(TransactionCase):
    """Test integration with CRM and other modules."""

    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner']
        self.Lead = self.env['crm.lead']
        
        self.partner = self.Partner.create({
            'name': 'Test Partner',
            'is_company': True,
            'facebook_url': 'https://facebook.com/test',
            'linkedin_url': 'https://linkedin.com/in/test',
            'twitter_url': 'https://twitter.com/test',
        })

    def test_crm_lead_social_integration(self):
        """Test CRM lead integration with social data."""
        lead = self.Lead.create({
            'name': 'Test Lead',
            'partner_id': self.partner.id,
        })
        
        self.assertEqual(lead.partner_id, self.partner)
        self.assertTrue(lead.partner_id.is_profile_complete)
        self.assertEqual(lead.partner_id.social_score, 80)

    def test_activity_creation_for_incomplete_profile(self):
        """Test activity creation for incomplete profiles."""
        incomplete_partner = self.Partner.create({
            'name': 'Incomplete Partner',
            'is_company': True,
            'auto_follow_up': True,
            'facebook_url': 'https://facebook.com/incomplete',
        })
        
        # Check that activity is created
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'res.partner'),
            ('res_id', '=', incomplete_partner.id),
        ])
        
        self.assertTrue(activities)
        activity = activities[0]
        self.assertIn('social', activity.summary.lower())


class TestPerformanceAndSecurity(TransactionCase):
    """Test performance and security aspects."""

    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner']

    def test_bulk_operations_performance(self):
        """Test performance of bulk operations."""
        # Create multiple partners
        partners_data = []
        for i in range(100):
            partners_data.append({
                'name': f'Bulk Partner {i}',
                'is_company': True,
                'facebook_url': f'https://facebook.com/bulk{i}',
            })
        
        # Measure time for bulk creation
        import time
        start_time = time.time()
        partners = self.Partner.create(partners_data)
        creation_time = time.time() - start_time
        
        # Should complete in reasonable time (less than 5 seconds)
        self.assertLess(creation_time, 5.0)
        
        # Verify all partners have correct social score
        for partner in partners:
            self.assertEqual(partner.social_score, 20)

    def test_sql_injection_protection(self):
        """Test protection against SQL injection in search."""
        # Try to inject SQL in search
        malicious_input = "'; DROP TABLE res_partner; --"
        
        # Should not raise database error
        try:
            results = self.Partner.search_by_social_media(malicious_input)
            # Should return empty results safely
            self.assertEqual(len(results), 0)
        except Exception as e:
            # Should not be a database-related exception
            self.assertNotIn('SQL', str(e).upper())

    def test_access_rights_compliance(self):
        """Test that access rights are properly enforced."""
        # Create a portal user
        portal_user = self.env['res.users'].create({
            'name': 'Portal User',
            'login': 'portal@test.com',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        
        # Portal user should not be able to write social fields
        partner = self.Partner.create({
            'name': 'Test Partner',
            'is_company': True,
        })
        
        with self.assertRaises(Exception):
            partner.with_user(portal_user).write({
                'facebook_url': 'https://facebook.com/hack'
            })