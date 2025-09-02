from odoo import api, fields, models, tools
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


class LoanConversionAnalytics(models.Model):
    _name = 'loan.conversion.analytics'
    _description = 'Analíticas de Conversión de Préstamos'
    _auto = False
    _rec_name = 'period'

    # Dimensiones
    period = fields.Date('Período')
    partner_id = fields.Many2one('res.partner', 'Cliente')
    product_id = fields.Many2one('product.product', 'Producto')
    product_tmpl_id = fields.Many2one('product.template', 'Plantilla Producto')
    
    # Métricas de volumen
    total_loans = fields.Integer('Total Préstamos')
    converted_loans = fields.Integer('Préstamos Convertidos')
    returned_loans = fields.Integer('Préstamos Devueltos')
    active_loans = fields.Integer('Préstamos Activos')
    
    # Métricas de conversión
    conversion_rate = fields.Float('Tasa Conversión (%)', digits=(5,2))
    return_rate = fields.Float('Tasa Devolución (%)', digits=(5,2))
    
    # Métricas financieras
    total_loan_value = fields.Float('Valor Total Préstamos', digits='Product Price')
    converted_value = fields.Float('Valor Convertido', digits='Product Price')
    avg_conversion_days = fields.Float('Días Promedio a Conversión', digits=(5,1))
    
    # Métricas de calidad
    damaged_returns = fields.Integer('Devoluciones Dañadas')
    damage_rate = fields.Float('Tasa Daños (%)', digits=(5,2))

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT 
                    row_number() OVER () AS id,
                    DATE_TRUNC('month', ltd.loan_date)::date as period,
                    ltd.partner_id,
                    ltd.product_id,
                    pp.product_tmpl_id,
                    COUNT(*) as total_loans,
                    COUNT(CASE WHEN ltd.status = 'sold' THEN 1 END) as converted_loans,
                    COUNT(CASE WHEN ltd.status IN ('returned_good', 'returned_damaged', 'returned_defective') THEN 1 END) as returned_loans,
                    COUNT(CASE WHEN ltd.status = 'active' THEN 1 END) as active_loans,
                    CASE 
                        WHEN COUNT(*) > 0 THEN 
                            ROUND(COUNT(CASE WHEN ltd.status = 'sold' THEN 1 END) * 100.0 / COUNT(*), 2)
                        ELSE 0 
                    END as conversion_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN 
                            ROUND(COUNT(CASE WHEN ltd.status IN ('returned_good', 'returned_damaged', 'returned_defective') THEN 1 END) * 100.0 / COUNT(*), 2)
                        ELSE 0 
                    END as return_rate,
                    SUM(ltd.quantity * ltd.original_cost) as total_loan_value,
                    SUM(CASE WHEN ltd.status = 'sold' THEN ltd.quantity * COALESCE(ltd.sale_price, ltd.original_cost) ELSE 0 END) as converted_value,
                    AVG(CASE WHEN ltd.status = 'sold' AND ltd.resolution_date IS NOT NULL THEN 
                        EXTRACT(DAY FROM ltd.resolution_date - ltd.loan_date) 
                    END) as avg_conversion_days,
                    COUNT(CASE WHEN ltd.status IN ('returned_damaged', 'returned_defective') THEN 1 END) as damaged_returns,
                    CASE 
                        WHEN COUNT(CASE WHEN ltd.status IN ('returned_good', 'returned_damaged', 'returned_defective') THEN 1 END) > 0 THEN 
                            ROUND(COUNT(CASE WHEN ltd.status IN ('returned_damaged', 'returned_defective') THEN 1 END) * 100.0 / 
                                  COUNT(CASE WHEN ltd.status IN ('returned_good', 'returned_damaged', 'returned_defective') THEN 1 END), 2)
                        ELSE 0 
                    END as damage_rate
                FROM loan_tracking_detail ltd
                JOIN product_product pp ON pp.id = ltd.product_id
                WHERE ltd.loan_date >= CURRENT_DATE - INTERVAL '24 months'
                GROUP BY 
                    DATE_TRUNC('month', ltd.loan_date),
                    ltd.partner_id,
                    ltd.product_id,
                    pp.product_tmpl_id
            )
        """)

    @api.model
    def get_conversion_trends(self, months=12):
        """Tendencias de conversión mensual"""
        date_from = fields.Date.today() - relativedelta(months=months)
        
        self.env.cr.execute("""
            SELECT 
                period,
                SUM(total_loans) as loans,
                SUM(converted_loans) as conversions,
                CASE WHEN SUM(total_loans) > 0 THEN 
                    ROUND(SUM(converted_loans) * 100.0 / SUM(total_loans), 2)
                ELSE 0 END as rate
            FROM loan_conversion_analytics
            WHERE period >= %s
            GROUP BY period
            ORDER BY period
        """, [date_from])
        
        return self.env.cr.dictfetchall()

    @api.model 
    def get_top_converting_clients(self, limit=10, min_loans=3):
        """Clientes con mejor tasa de conversión"""
        self.env.cr.execute("""
            SELECT 
                rp.name as client_name,
                SUM(lca.total_loans) as total_loans,
                SUM(lca.converted_loans) as conversions,
                ROUND(SUM(lca.converted_loans) * 100.0 / SUM(lca.total_loans), 2) as conversion_rate,
                SUM(lca.converted_value) as total_converted_value
            FROM loan_conversion_analytics lca
            JOIN res_partner rp ON rp.id = lca.partner_id
            WHERE lca.period >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY lca.partner_id, rp.name
            HAVING SUM(lca.total_loans) >= %s
            ORDER BY conversion_rate DESC, total_converted_value DESC
            LIMIT %s
        """, [min_loans, limit])
        
        return self.env.cr.dictfetchall()

    @api.model
    def get_star_products(self, limit=10):
        """Productos estrella en préstamos"""
        self.env.cr.execute("""
            SELECT 
                pt.name as product_name,
                SUM(lca.total_loans) as total_loans,
                SUM(lca.converted_loans) as conversions,
                ROUND(SUM(lca.converted_loans) * 100.0 / SUM(lca.total_loans), 2) as conversion_rate,
                SUM(lca.converted_value) as revenue,
                ROUND(AVG(lca.avg_conversion_days), 1) as avg_days_to_convert
            FROM loan_conversion_analytics lca
            JOIN product_template pt ON pt.id = lca.product_tmpl_id
            WHERE lca.period >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY lca.product_tmpl_id, pt.name
            HAVING SUM(lca.total_loans) >= 3
            ORDER BY conversion_rate DESC, revenue DESC
            LIMIT %s
        """, [limit])
        
        return self.env.cr.dictfetchall()


class LoanAnalyticsDashboard(models.TransientModel):
    _name = 'loan.analytics.dashboard'
    _description = 'Dashboard de Analíticas de Préstamos'

    @api.model
    def get_dashboard_data(self):
        """Datos consolidados para dashboard"""
        analytics = self.env['loan.conversion.analytics']
        
        return {
            'trends': analytics.get_conversion_trends(12),
            'top_clients': analytics.get_top_converting_clients(10),
            'star_products': analytics.get_star_products(10),
            'summary': self._get_summary_stats()
        }

    def _get_summary_stats(self):
        """Estadísticas resumen"""
        self.env.cr.execute("""
            SELECT 
                SUM(total_loans) as total_loans,
                SUM(converted_loans) as total_conversions,
                ROUND(AVG(conversion_rate), 2) as avg_conversion_rate,
                SUM(converted_value) as total_revenue,
                ROUND(AVG(avg_conversion_days), 1) as avg_days_to_convert,
                ROUND(AVG(damage_rate), 2) as avg_damage_rate
            FROM loan_conversion_analytics
            WHERE period >= CURRENT_DATE - INTERVAL '12 months'
        """)
        
        return self.env.cr.dictfetchone() or {}