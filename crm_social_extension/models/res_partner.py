# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Social Media Fields
    facebook_url = fields.Char(
        string='Facebook URL',
        help='Facebook profile or page URL'
    )
    linkedin_url = fields.Char(
        string='LinkedIn URL', 
        help='LinkedIn profile or company page URL'
    )
    twitter_url = fields.Char(
        string='Twitter URL',
        help='Twitter profile URL'
    )
    
    # Profile Completion Fields
    is_profile_complete = fields.Boolean(
        string='Profile Complete',
        compute='_compute_profile_complete',
        store=True,
        help='True if all social media URLs are provided'
    )
    
    # Marketing & Lead Scoring Fields
    social_score = fields.Integer(
        string='Social Score',
        compute='_compute_social_score',
        store=True,
        help='Lead scoring based on social media presence (0-100)'
    )
    
    social_engagement_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('excellent', 'Excellent')
    ], string='Social Engagement Level', default='low',
       help='Level of engagement on social media platforms')
    
    last_social_update = fields.Datetime(
        string='Last Social Update',
        default=fields.Datetime.now,
        help='Last time social media information was updated'
    )
    
    social_notes = fields.Text(
        string='Social Media Notes',
        help='Additional notes about social media presence and engagement'
    )
    
    # Marketing Automation Fields
    auto_follow_up = fields.Boolean(
        string='Auto Follow-up',
        default=True,
        help='Automatically create follow-up activities for incomplete profiles'
    )
    
    social_campaign_ids = fields.Many2many(
        'marketing.campaign',
        string='Social Campaigns',
        help='Marketing campaigns related to social media'
    )

    @api.depends('facebook_url', 'linkedin_url', 'twitter_url')
    def _compute_profile_complete(self):
        """Compute if the social media profile is complete."""
        for partner in self:
            partner.is_profile_complete = bool(
                partner.facebook_url and 
                partner.linkedin_url and 
                partner.twitter_url
            )

    @api.depends('facebook_url', 'linkedin_url', 'twitter_url', 'social_engagement_level')
    def _compute_social_score(self):
        """Compute social media lead score (0-100)."""
        for partner in self:
            score = 0
            
            # Base score for each social media platform (20 points each)
            if partner.facebook_url:
                score += 20
            if partner.linkedin_url:
                score += 20
            if partner.twitter_url:
                score += 20
            
            # Bonus for complete profile (20 points)
            if partner.is_profile_complete:
                score += 20
            
            # Engagement level bonus (0-20 points)
            engagement_bonus = {
                'low': 0,
                'medium': 5,
                'high': 10,
                'excellent': 20
            }
            score += engagement_bonus.get(partner.social_engagement_level, 0)
            
            partner.social_score = min(score, 100)

    @api.constrains('facebook_url')
    def _check_facebook_url(self):
        """Validate Facebook URL format."""
        for partner in self:
            if partner.facebook_url and not self._is_valid_social_url(partner.facebook_url, 'facebook'):
                raise ValidationError(_('Please enter a valid Facebook URL (e.g., https://facebook.com/username)'))

    @api.constrains('linkedin_url')
    def _check_linkedin_url(self):
        """Validate LinkedIn URL format."""
        for partner in self:
            if partner.linkedin_url and not self._is_valid_social_url(partner.linkedin_url, 'linkedin'):
                raise ValidationError(_('Please enter a valid LinkedIn URL (e.g., https://linkedin.com/in/username)'))

    @api.constrains('twitter_url')
    def _check_twitter_url(self):
        """Validate Twitter URL format."""
        for partner in self:
            if partner.twitter_url and not self._is_valid_social_url(partner.twitter_url, 'twitter'):
                raise ValidationError(_('Please enter a valid Twitter URL (e.g., https://twitter.com/username)'))

    def _is_valid_social_url(self, url, platform):
        """Validate social media URL format."""
        if not url:
            return True
            
        patterns = {
            'facebook': r'^https?://(www\.)?(facebook|fb)\.com/.+',
            'linkedin': r'^https?://(www\.)?linkedin\.com/(in|company)/.+',
            'twitter': r'^https?://(www\.)?(twitter|x)\.com/.+'
        }
        
        pattern = patterns.get(platform)
        if pattern:
            return bool(re.match(pattern, url.lower()))
        return False

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle social media scoring and automation."""
        partners = super().create(vals_list)
        for partner in partners:
            partner._handle_social_automation()
        return partners

    def write(self, vals):
        """Override write to handle social media updates and automation."""
        # Check if social fields are being updated
        social_fields = ['facebook_url', 'linkedin_url', 'twitter_url', 'social_engagement_level']
        social_updated = any(field in vals for field in social_fields)
        
        if social_updated:
            vals['last_social_update'] = fields.Datetime.now()
        
        result = super().write(vals)
        
        if social_updated:
            for partner in self:
                partner._handle_social_automation()
        
        return result

    def _handle_social_automation(self):
        """Handle marketing automation based on social media profile."""
        self.ensure_one()
        
        if not self.auto_follow_up:
            return
            
        # Create follow-up activity for incomplete profiles
        if not self.is_profile_complete and self.is_company:
            self._create_social_follow_up_activity()
        
        # Update social campaigns
        self._update_social_campaigns()

    def _create_social_follow_up_activity(self):
        """Create a follow-up activity for incomplete social profiles."""
        self.ensure_one()
        
        # Check if there's already a pending activity
        existing_activity = self.env['mail.activity'].search([
            ('res_model_id', '=', self.env['ir.model']._get_id('res.partner')),
            ('res_id', '=', self.id),
            ('activity_type_id.name', '=', 'Social Media Follow-up'),
            ('state', '=', 'planned')
        ], limit=1)
        
        if existing_activity:
            return
        
        # Get or create activity type
        activity_type = self.env['mail.activity.type'].search([
            ('name', '=', 'Social Media Follow-up')
        ], limit=1)
        
        if not activity_type:
            activity_type = self.env['mail.activity.type'].create({
                'name': 'Social Media Follow-up',
                'summary': 'Follow up on social media profile completion',
                'res_model': 'res.partner',
                'category': 'meeting',
                'delay_count': 7,
                'delay_unit': 'days',
            })
        
        missing_platforms = []
        if not self.facebook_url:
            missing_platforms.append('Facebook')
        if not self.linkedin_url:
            missing_platforms.append('LinkedIn')
        if not self.twitter_url:
            missing_platforms.append('Twitter')
        
        # CORREGIDO: Usar res_model_id en lugar de res_model para Odoo 18.0
        self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'res_id': self.id,
            'res_model_id': self.env['ir.model']._get_id('res.partner'),
            'summary': f'Complete social media profile for {self.name}',
            'note': f'Missing social media platforms: {", ".join(missing_platforms)}. '
                   f'Current social score: {self.social_score}/100. '
                   f'Consider reaching out to gather social media information for better engagement opportunities.',
            'user_id': self.env.user.id,
        })

    def _update_social_campaigns(self):
        """Update marketing campaigns based on social score."""
        self.ensure_one()
        
        # Example: Add to high-value campaign if social score > 80
        if self.social_score > 80:
            high_value_campaign = self.env['marketing.campaign'].search([
                ('name', 'ilike', 'High Social Value')
            ], limit=1)
            
            if high_value_campaign and high_value_campaign not in self.social_campaign_ids:
                self.social_campaign_ids = [(4, high_value_campaign.id)]

    def action_update_social_score(self):
        """Manual action to recalculate social score."""
        self._compute_social_score()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_open_social_activities(self):
        """Open social media related activities."""
        self.ensure_one()
        return {
            'name': _('Social Media Activities'),
            'type': 'ir.actions.act_window',
            'res_model': 'mail.activity',
            'view_mode': 'tree,form',
            'domain': [
                ('res_model_id', '=', self.env['ir.model']._get_id('res.partner')),
                ('res_id', '=', self.id),
                ('activity_type_id.name', 'ilike', 'social')
            ],
            'context': {
                'default_res_id': self.id, 
                'default_res_model_id': self.env['ir.model']._get_id('res.partner')
            },
        }

    def get_social_media_data(self):
        """Get formatted social media data for website display."""
        self.ensure_one()
        social_data = []
        
        if self.facebook_url:
            social_data.append({
                'platform': 'facebook',
                'url': self.facebook_url,
                'icon': 'fa-facebook',
                'name': 'Facebook'
            })
        
        if self.linkedin_url:
            social_data.append({
                'platform': 'linkedin', 
                'url': self.linkedin_url,
                'icon': 'fa-linkedin',
                'name': 'LinkedIn'
            })
        
        if self.twitter_url:
            social_data.append({
                'platform': 'twitter',
                'url': self.twitter_url,
                'icon': 'fa-twitter',
                'name': 'Twitter'
            })
        
        return social_data

    @api.model
    def search_by_social_media(self, search_term):
        """Search partners by social media information."""
        domain = [
            '|', '|', '|',
            ('name', 'ilike', search_term),
            ('facebook_url', 'ilike', search_term),
            ('linkedin_url', 'ilike', search_term),
            ('twitter_url', 'ilike', search_term)
        ]
        return self.search(domain)

    def name_get(self):
        """Override name_get to include social score in display."""
        result = super().name_get()
        if self.env.context.get('show_social_score'):
            new_result = []
            for partner_id, name in result:
                partner = self.browse(partner_id)
                if partner.social_score > 0:
                    name = f"{name} (Social: {partner.social_score})"
                new_result.append((partner_id, name))
            return new_result
        return result