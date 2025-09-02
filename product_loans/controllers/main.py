from odoo import http
from odoo.http import request

class LoanAnalyticsController(http.Controller):
    
    @http.route('/loan_analytics/dashboard_data', type='json', auth='user')
    def get_dashboard_data(self):
        dashboard = request.env['loan.analytics.dashboard']
        return dashboard.get_dashboard_data()
    
    @http.route('/loan_analytics/trends/<int:months>', type='json', auth='user')
    def get_trends(self, months=12):
        analytics = request.env['loan.conversion.analytics']
        return analytics.get_conversion_trends(months)