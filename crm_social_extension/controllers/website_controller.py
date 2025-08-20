# -*- coding: utf-8 -*-

from odoo import http, fields, _
from odoo.http import request
from odoo.addons.website.controllers.main import Website
from odoo.addons.portal.controllers.portal import CustomerPortal
import json
import logging

_logger = logging.getLogger(__name__)


class CustomerShowcaseController(http.Controller):
    
    @http.route(['/customers', '/customers/page/<int:page>'], 
                type='http', auth='public', website=True, sitemap=True)
    def customer_showcase(self, page=1, search='', sort='name', filter_complete='all', **kwargs):
        """Display customer showcase page with social media information."""
        
        # Build domain based on filters
        domain = [
            ('is_company', '=', True),
            ('website_published', '=', True),  # Only show published customers
        ]
        
        # Add search filter
        if search:
            search_domain = [
                '|', '|', '|', '|',
                ('name', 'ilike', search),
                ('facebook_url', 'ilike', search),
                ('linkedin_url', 'ilike', search),
                ('twitter_url', 'ilike', search),
                ('social_notes', 'ilike', search)
            ]
            domain.extend(search_domain)
        
        # Add profile completeness filter
        if filter_complete == 'complete':
            domain.append(('is_profile_complete', '=', True))
        elif filter_complete == 'incomplete':
            domain.append(('is_profile_complete', '=', False))
        
        # Set up sorting
        sort_options = {
            'name': 'name asc',
            'social_score': 'social_score desc',
            'recent': 'last_social_update desc'
        }
        order = sort_options.get(sort, 'name asc')
        
        # Pagination setup
        limit = 12
        offset = (page - 1) * limit
        
        # Get customers
        Partner = request.env['res.partner'].sudo()
        total_customers = Partner.search_count(domain)
        customers = Partner.search(domain, order=order, limit=limit, offset=offset)
        
        # Calculate pagination
        total_pages = (total_customers + limit - 1) // limit
        
        # Prepare values for template
        values = {
            'customers': customers,
            'search': search,
            'sort': sort,
            'filter_complete': filter_complete,
            'page': page,
            'total_pages': total_pages,
            'total_customers': total_customers,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
            'page_range': range(max(1, page - 2), min(total_pages + 1, page + 3)),
        }
        
        return request.render('crm_social_extension.customer_showcase_page', values)

    @http.route('/customers/<model("res.partner"):customer>', 
                type='http', auth='public', website=True)
    def customer_detail(self, customer, **kwargs):
        """Display individual customer detail page."""
        
        # Check if customer is published and is a company
        if not customer.website_published or not customer.is_company:
            return request.not_found()
        
        values = {
            'customer': customer,
            'main_object': customer,  # For SEO
            'social_data': customer.get_social_media_data(),
        }
        
        return request.render('crm_social_extension.customer_detail_page', values)

    @http.route('/customers/search/autocomplete', 
                type='json', auth='public', website=True)
    def customer_search_autocomplete(self, term, **kwargs):
        """AJAX endpoint for search autocomplete."""
        
        if not term or len(term) < 2:
            return []
        
        domain = [
            ('is_company', '=', True),
            ('website_published', '=', True),
            '|', '|', '|',
            ('name', 'ilike', term),
            ('facebook_url', 'ilike', term),
            ('linkedin_url', 'ilike', term),
            ('twitter_url', 'ilike', term)
        ]
        
        customers = request.env['res.partner'].sudo().search(domain, limit=10)
        
        results = []
        for customer in customers:
            social_platforms = []
            if customer.facebook_url:
                social_platforms.append('Facebook')
            if customer.linkedin_url:
                social_platforms.append('LinkedIn')
            if customer.twitter_url:
                social_platforms.append('Twitter')
            
            results.append({
                'id': customer.id,
                'name': customer.name,
                'url': f'/customers/{customer.id}',
                'social_platforms': social_platforms,
                'social_score': customer.social_score,
                'is_complete': customer.is_profile_complete,
            })
        
        return results

    @http.route('/customers/api/stats', 
                type='json', auth='public', website=True)
    def customer_stats(self, **kwargs):
        """API endpoint for customer statistics."""
        
        Partner = request.env['res.partner'].sudo()
        
        total_customers = Partner.search_count([
            ('is_company', '=', True),
            ('website_published', '=', True)
        ])
        
        complete_profiles = Partner.search_count([
            ('is_company', '=', True),
            ('website_published', '=', True),
            ('is_profile_complete', '=', True)
        ])
        
        high_social_score = Partner.search_count([
            ('is_company', '=', True),
            ('website_published', '=', True),
            ('social_score', '>', 80)
        ])
        
        platform_stats = {}
        for platform in ['facebook_url', 'linkedin_url', 'twitter_url']:
            platform_stats[platform] = Partner.search_count([
                ('is_company', '=', True),
                ('website_published', '=', True),
                (platform, '!=', False)
            ])
        
        return {
            'total_customers': total_customers,
            'complete_profiles': complete_profiles,
            'completion_rate': round((complete_profiles / total_customers * 100) if total_customers else 0, 1),
            'high_social_score': high_social_score,
            'platform_stats': platform_stats,
        }


class WebsiteSEOController(Website):
    """Extend website controller for SEO optimization."""
    
    @http.route('/sitemap.xml', type='http', auth="public", website=True, sitemap=False)
    def sitemap_xml_index(self, **kwargs):
        """Override sitemap to include customer pages."""
        response = super().sitemap_xml_index(**kwargs)
        
        # Add customer showcase pages to sitemap
        Partner = request.env['res.partner'].sudo()
        customers = Partner.search([
            ('is_company', '=', True),
            ('website_published', '=', True),
            ('is_profile_complete', '=', True)  # Only complete profiles in sitemap
        ])
        
        sitemap_content = response.get_data(as_text=True)
        
        # Add customer URLs to sitemap
        for customer in customers:
            customer_url = f'{request.httprequest.url_root}customers/{customer.id}'
            sitemap_content = sitemap_content.replace(
                '</urlset>',
                f'<url><loc>{customer_url}</loc><changefreq>weekly</changefreq><priority>0.7</priority></url></urlset>'
            )
        
        return request.make_response(sitemap_content, headers=response.headers)


def sitemap_customers(env, rule, qs):
    """Sitemap function for customer pages."""
    Partner = env['res.partner'].sudo()
    customers = Partner.search([
        ('is_company', '=', True),
        ('website_published', '=', True),
    ])
    
    for customer in customers:
        if customer.website_published:
            yield {
                'loc': f'/customers/{customer.id}',
                'lastmod': customer.last_social_update or customer.write_date,
                'changefreq': 'weekly',
                'priority': 0.8 if customer.is_profile_complete else 0.6,
            }