# -*- coding: utf-8 -*-

from odoo import fields, models, api


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    warehouse_type_display = fields.Char(
        string='Tipo de Almacén',
        compute='_compute_warehouse_type_display',
        store=False
    )

    @api.depends('warehouse_id.warehouse_type')
    def _compute_warehouse_type_display(self):
        """Calcula el tipo de almacén para mostrar en la vista"""
        for record in self:
            if record.warehouse_id and record.warehouse_id.warehouse_type:
                record.warehouse_type_display = dict(record.warehouse_id._fields['warehouse_type'].selection).get(
                    record.warehouse_id.warehouse_type, record.warehouse_id.warehouse_type
                )
            else:
                record.warehouse_type_display = False

    @property 
    def is_loan_warehouse(self):
        """Propiedad para verificar si es un almacén de préstamos"""
        return self.warehouse_id and self.warehouse_id.warehouse_type == 'loans'