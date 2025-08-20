# -*- coding: utf-8 -*-

from . import models
from . import controllers

def _post_init_hook(env):
    """Post-installation hook to set up default data and configurations."""
    # Update existing partners with default social score
    partners = env['res.partner'].search([('social_score', '=', 0)])
    for partner in partners:
        partner._compute_social_score()
    
    # Create default marketing activities for incomplete profiles
    incomplete_partners = env['res.partner'].search([('is_profile_complete', '=', False), ('is_company', '=', True)])
    activity_type = env['mail.activity.type'].search([('name', '=', 'Social Media Follow-up')], limit=1)
    
    if not activity_type:
        activity_type = env['mail.activity.type'].create({
            'name': 'Social Media Follow-up',
            'summary': 'Follow up on social media profile completion',
            'res_model': 'res.partner',
            'category': 'meeting',
            'delay_count': 7,
            'delay_unit': 'days',
        })
    
    for partner in incomplete_partners[:10]:  # Limit to first 10 to avoid performance issues
        # CORREGIDO: Usar res_model_id en lugar de res_model para Odoo 18.0
        env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'res_id': partner.id,
            'res_model_id': env['ir.model']._get_id('res.partner'),
            'summary': f'Complete social media profile for {partner.name}',
            'note': 'This customer has an incomplete social media profile. Consider reaching out to gather their social media information for better engagement opportunities.',
            'user_id': env.user.id,
        })