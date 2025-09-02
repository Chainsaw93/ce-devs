# -*- coding: utf-8 -*-

from odoo import fields, models, _


class StockLocation(models.Model):
    _inherit = 'stock.location'
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente Asociado',
        help="Cliente asociado a esta ubicación (para préstamos dedicados)",
        index=True
    )
    
    # Campo adicional para identificar ubicaciones de préstamos
    is_loan_location = fields.Boolean(
        string='Ubicación de Préstamos',
        help="Indica si esta ubicación es específica para préstamos",
        default=False,
        index=True
    )
    
    def name_get(self):
        """Sobrescribir name_get para mostrar cliente asociado en ubicaciones de préstamos"""
        result = []
        for location in self:
            name = location.name
            # Si es ubicación de préstamo y tiene cliente asociado, mostrar información adicional
            if location.is_loan_location and location.partner_id:
                name = f"{name} [{location.partner_id.name}]"
            elif location.partner_id and 'Préstamos' in location.name:
                # Compatibilidad con ubicaciones existentes que tengan "Préstamos" en el nombre
                name = f"{name} [{location.partner_id.name}]"
            result.append((location.id, name))
        return result