# -*- coding: utf-8 -*-

from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    warehouse_type = fields.Selection([
        ('loans', 'Préstamos'),
    ], string='Tipo de Almacén', required=False, 
       help="Especifica el tipo especial de almacén si aplica")