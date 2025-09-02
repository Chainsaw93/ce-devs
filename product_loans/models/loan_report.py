# -*- coding: utf-8 -*-

from odoo import fields, models, api, tools


class LoanReport(models.Model):
    _name = 'loan.report'
    _description = 'Reporte de Préstamos'
    _auto = False
    _rec_name = 'picking_id'

    picking_id = fields.Many2one('stock.picking', string='Transferencia')
    partner_id = fields.Many2one('res.partner', string='Cliente')
    loaned_to_partner_id = fields.Many2one('res.partner', string='Prestado a')
    product_id = fields.Many2one('product.product', string='Producto')
    product_qty = fields.Float(string='Cantidad')
    scheduled_date = fields.Datetime(string='Fecha Programada')
    date_done = fields.Datetime(string='Fecha Realizada')
    loan_expected_return_date = fields.Date(string='Fecha Esperada Devolución')
    days_overdue = fields.Integer(string='Días de Retraso', help="Días transcurridos desde la fecha esperada de devolución")
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('waiting', 'En Espera'),
        ('confirmed', 'Confirmado'),
        ('assigned', 'Listo'),
        ('done', 'Realizado'),
        ('cancel', 'Cancelado'),
    ], string='Estado')
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén')
    location_dest_id = fields.Many2one('stock.location', string='Ubicación Destino')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT 
                    row_number() OVER () AS id,
                    sp.id as picking_id,
                    sp.partner_id,
                    sp.loaned_to_partner_id,
                    sm.product_id,
                    sm.product_uom_qty as product_qty,
                    sp.scheduled_date,
                    sp.date_done,
                    sp.loan_expected_return_date,
                    CASE 
                        WHEN sp.loan_expected_return_date IS NOT NULL AND sp.state = 'done' 
                        THEN GREATEST(0, CURRENT_DATE - sp.loan_expected_return_date)
                        ELSE 0
                    END as days_overdue,
                    sp.state,
                    spt.warehouse_id,
                    sp.location_dest_id
                FROM stock_picking sp
                JOIN stock_move sm ON sm.picking_id = sp.id
                JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                WHERE sp.is_loan = true
                  AND sp.state != 'cancel'
                  AND sm.state != 'cancel'
            )
        """)
    
    @api.model
    def get_overdue_loans_count(self):
        """Retorna la cantidad de préstamos vencidos"""
        return self.search_count([
            ('state', '=', 'done'),
            ('days_overdue', '>', 0)
        ])
    
    @api.model
    def get_active_loans_count(self):
        """Retorna la cantidad de préstamos activos (realizados pero no devueltos)"""
        return self.search_count([
            ('state', '=', 'done')
        ])
    
    def action_view_picking(self):
        """Acción para ver el picking asociado desde el dashboard"""
        self.ensure_one()
        return {
            'name': 'Préstamo',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }