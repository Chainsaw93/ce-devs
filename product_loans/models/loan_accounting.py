# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    loan_picking_id = fields.Many2one(
        'stock.picking',
        string='Préstamo Relacionado',
        help="Préstamo que generó este asiento contable"
    )
    
    is_loan_entry = fields.Boolean(
        string='Asiento de Préstamo',
        help="Indica si este asiento está relacionado con operaciones de préstamos"
    )


class StockMove(models.Model):
    _inherit = 'stock.move'
    
    def _create_account_move_line(self, credit_account_id, debit_account_id, journal_id, qty, description, svl_id, cost):
        """Override para manejar valoración específica de préstamos convertidos a venta"""
        
        # Si es una conversión de préstamo a venta, usar costo original
        if (self.picking_id.loan_conversion_sale_order_id and 
            hasattr(self.picking_id, 'is_loan') and 
            self.picking_id.is_loan):
            
            # Buscar el costo original del préstamo
            original_cost = self._get_original_loan_cost()
            if original_cost:
                cost = original_cost
                description = f"{description} (Conversión préstamo - Costo original: {original_cost})"
        
        # Llamada estándar con costo ajustado
        return super()._create_account_move_line(
            credit_account_id, debit_account_id, journal_id, 
            qty, description, svl_id, cost
        )
    
    def _get_original_loan_cost(self):
        """Obtener el costo original del producto al momento del préstamo"""
        # Buscar en el tracker de valoración
        valuation_tracker = self.env['loan.valuation.tracker'].search([
            ('picking_id', '=', self.picking_id.id),
            ('product_id', '=', self.product_id.id)
        ], limit=1)
        
        if valuation_tracker:
            return valuation_tracker.original_cost
        
        # Fallback: buscar en detalles de seguimiento
        tracking_detail = self.env['loan.tracking.detail'].search([
            ('picking_id', '=', self.picking_id.id),
            ('product_id', '=', self.product_id.id)
        ], limit=1)
        
        return tracking_detail.original_cost if tracking_detail else None


class LoanAccountingManager(models.Model):
    _name = 'loan.accounting.manager'
    _description = 'Gestor de Contabilidad de Préstamos'

    # Configuración de cuentas contables
    loan_commitment_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Compromisos de Préstamos',
        help="Cuenta para registrar compromisos por préstamos activos",
        domain=[('account_type', '=', 'liability_current')]
    )
    
    loan_risk_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Riesgo de Préstamos',
        help="Cuenta para registrar riesgo de pérdidas por préstamos",
        domain=[('account_type', '=', 'expense')]
    )
    
    loan_revenue_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Ingresos por Conversión',
        help="Cuenta para registrar ingresos cuando préstamos se convierten en ventas",
        domain=[('account_type', '=', 'income')]
    )
    
    # Configuración de políticas contables
    create_commitment_entries = fields.Boolean(
        string='Crear Asientos de Compromiso',
        default=False,
        help="Crear asientos contables cuando se crean préstamos"
    )
    
    create_risk_entries = fields.Boolean(
        string='Crear Asientos de Riesgo',
        default=False,
        help="Crear provisiones de riesgo para préstamos vencidos"
    )
    
    risk_days_threshold = fields.Integer(
        string='Umbral de Días para Riesgo',
        default=30,
        help="Días de vencimiento para crear provisión de riesgo"
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True
    )

    @api.model
    def get_default_config(self):
        """Obtener configuración por defecto para la compañía actual"""
        config = self.search([('company_id', '=', self.env.company.id)], limit=1)
        if not config:
            config = self.create({
                'company_id': self.env.company.id
            })
        return config

    def create_loan_commitment_entry(self, picking):
        """Crear asiento de compromiso cuando se valida un préstamo"""
        if not self.create_commitment_entries or not self.loan_commitment_account_id:
            return None
        
        total_value = sum([
            move.product_id.standard_price * move.quantity_done 
            for move in picking.move_ids_without_package
        ])
        
        if total_value <= 0:
            return None
        
        # Crear asiento de compromiso
        move_vals = {
            'journal_id': self._get_loan_journal().id,
            'date': picking.date_done or fields.Date.today(),
            'ref': f"Compromiso préstamo {picking.name}",
            'loan_picking_id': picking.id,
            'is_loan_entry': True,
            'line_ids': [
                # Débito: Cuenta de compromisos (activo)
                (0, 0, {
                    'account_id': self.loan_commitment_account_id.id,
                    'name': f"Compromiso por préstamo {picking.name}",
                    'debit': total_value,
                    'credit': 0,
                    'partner_id': picking.owner_id.id,
                }),
                # Crédito: Cuenta de contrapartida (pasivo)
                (0, 0, {
                    'account_id': self._get_loan_offset_account().id,
                    'name': f"Contrapartida préstamo {picking.name}",
                    'debit': 0,
                    'credit': total_value,
                    'partner_id': picking.owner_id.id,
                }),
            ]
        }
        
        account_move = self.env['account.move'].create(move_vals)
        account_move.action_post()
        
        return account_move

    def create_loan_risk_entry(self, picking):
        """Crear asiento de riesgo para préstamos vencidos"""
        if not self.create_risk_entries or not self.loan_risk_account_id:
            return None
        
        if not picking.is_overdue or picking.overdue_days < self.risk_days_threshold:
            return None
        
        # Verificar si ya existe asiento de riesgo
        existing_risk = self.env['account.move'].search([
            ('loan_picking_id', '=', picking.id),
            ('is_loan_entry', '=', True),
            ('ref', 'ilike', 'Riesgo préstamo')
        ], limit=1)
        
        if existing_risk:
            return existing_risk
        
        # Calcular valor en riesgo
        active_details = self.env['loan.tracking.detail'].search([
            ('picking_id', '=', picking.id),
            ('status', '=', 'active')
        ])
        
        risk_value = sum([
            detail.original_cost * detail.quantity 
            for detail in active_details
        ])
        
        if risk_value <= 0:
            return None
        
        # Crear asiento de riesgo
        move_vals = {
            'journal_id': self._get_loan_journal().id,
            'date': fields.Date.today(),
            'ref': f"Riesgo préstamo vencido {picking.name}",
            'loan_picking_id': picking.id,
            'is_loan_entry': True,
            'line_ids': [
                # Débito: Cuenta de gastos por riesgo
                (0, 0, {
                    'account_id': self.loan_risk_account_id.id,
                    'name': f"Provisión riesgo préstamo {picking.name}",
                    'debit': risk_value,
                    'credit': 0,
                    'partner_id': picking.owner_id.id,
                }),
                # Crédito: Cuenta de provisión
                (0, 0, {
                    'account_id': self._get_provision_account().id,
                    'name': f"Provisión por préstamo en riesgo",
                    'debit': 0,
                    'credit': risk_value,
                    'partner_id': picking.owner_id.id,
                }),
            ]
        }
        
        account_move = self.env['account.move'].create(move_vals)
        account_move.action_post()
        
        return account_move

    def reverse_loan_commitment(self, picking):
        """Revertir asiento de compromiso cuando se resuelve un préstamo"""
        commitment_move = self.env['account.move'].search([
            ('loan_picking_id', '=', picking.id),
            ('is_loan_entry', '=', True),
            ('ref', 'ilike', 'Compromiso préstamo'),
            ('state', '=', 'posted')
        ], limit=1)
        
        if not commitment_move:
            return None
        
        # Crear asiento de reversión
        reversal = commitment_move._reverse_moves([{
            'date': fields.Date.today(),
            'reason': f"Resolución préstamo {picking.name}",
            'journal_id': commitment_move.journal_id.id,
        }])
        
        if reversal:
            reversal.action_post()
        
        return reversal

    def create_loan_conversion_adjustment(self, sale_order, original_cost, sale_price):
        """Crear ajuste por diferencia en conversión préstamo → venta"""
        difference = sale_price - original_cost
        
        if abs(difference) < 0.01:  # Diferencia insignificante
            return None
        
        account_id = self.loan_revenue_account_id.id if difference > 0 else self.loan_risk_account_id.id
        
        if not account_id:
            return None
        
        move_vals = {
            'journal_id': self._get_loan_journal().id,
            'date': sale_order.date_order or fields.Date.today(),
            'ref': f"Ajuste conversión préstamo {sale_order.origin or sale_order.name}",
            'is_loan_entry': True,
            'line_ids': []
        }
        
        if difference > 0:
            # Ganancia en la conversión
            move_vals['line_ids'] = [
                (0, 0, {
                    'account_id': account_id,
                    'name': f"Ganancia conversión préstamo",
                    'debit': 0,
                    'credit': abs(difference),
                    'partner_id': sale_order.partner_id.id,
                }),
                (0, 0, {
                    'account_id': self._get_receivable_account(sale_order.partner_id).id,
                    'name': f"Contrapartida ganancia conversión",
                    'debit': abs(difference),
                    'credit': 0,
                    'partner_id': sale_order.partner_id.id,
                })
            ]
        else:
            # Pérdida en la conversión
            move_vals['line_ids'] = [
                (0, 0, {
                    'account_id': account_id,
                    'name': f"Pérdida conversión préstamo",
                    'debit': abs(difference),
                    'credit': 0,
                    'partner_id': sale_order.partner_id.id,
                }),
                (0, 0, {
                    'account_id': self._get_receivable_account(sale_order.partner_id).id,
                    'name': f"Contrapartida pérdida conversión",
                    'debit': 0,
                    'credit': abs(difference),
                    'partner_id': sale_order.partner_id.id,
                })
            ]
        
        account_move = self.env['account.move'].create(move_vals)
        account_move.action_post()
        
        return account_move

    def _get_loan_journal(self):
        """Obtener diario para asientos de préstamos"""
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not journal:
            raise UserError(_("No se encontró un diario general para crear asientos de préstamos."))
        
        return journal

    def _get_loan_offset_account(self):
        """Obtener cuenta de contrapartida para compromisos"""
        # Buscar cuenta de pasivos corrientes
        offset_account = self.env['account.account'].search([
            ('account_type', '=', 'liability_current'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not offset_account:
            raise UserError(_("No se encontró cuenta de contrapartida para compromisos de préstamos."))
        
        return offset_account

    def _get_provision_account(self):
        """Obtener cuenta de provisión para riesgos"""
        provision_account = self.env['account.account'].search([
            ('account_type', '=', 'liability_current'),
            ('name', 'ilike', 'provisión'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not provision_account:
            # Usar la misma cuenta de compromisos como fallback
            provision_account = self._get_loan_offset_account()
        
        return provision_account

    def _get_receivable_account(self, partner):
        """Obtener cuenta de clientes"""
        return partner.property_account_receivable_id

    @api.model
    def process_overdue_risk_entries(self):
        """Cron job para crear asientos de riesgo automáticamente"""
        configs = self.search([('create_risk_entries', '=', True)])
        
        processed = 0
        
        for config in configs:
            # Buscar préstamos vencidos que requieren provisión
            overdue_pickings = self.env['stock.picking'].search([
                ('is_loan', '=', True),
                ('is_overdue', '=', True),
                ('overdue_days', '>=', config.risk_days_threshold),
                ('company_id', '=', config.company_id.id),
                ('loan_state', 'in', ['active', 'in_trial', 'partially_resolved'])
            ])
            
            for picking in overdue_pickings:
                try:
                    move = config.create_loan_risk_entry(picking)
                    if move:
                        processed += 1
                except Exception as e:
                    # Log error pero continuar con otros préstamos
                    self.env['ir.logging'].sudo().create({
                        'name': 'loan_accounting',
                        'type': 'server',
                        'level': 'ERROR',
                        'message': f"Error creando asiento de riesgo para {picking.name}: {str(e)}",
                        'func': 'process_overdue_risk_entries'
                    })
        
        return processed


class StockPickingAccountingExtension(models.Model):
    _inherit = 'stock.picking'
    
    loan_accounting_move_ids = fields.One2many(
        'account.move',
        'loan_picking_id',
        string='Asientos Contables de Préstamo',
        help="Asientos contables relacionados con este préstamo"
    )
    
    has_accounting_entries = fields.Boolean(
        string='Tiene Asientos Contables',
        compute='_compute_has_accounting_entries'
    )

    @api.depends('loan_accounting_move_ids')
    def _compute_has_accounting_entries(self):
        """Verificar si tiene asientos contables asociados"""
        for picking in self:
            picking.has_accounting_entries = bool(picking.loan_accounting_move_ids)

    def button_validate(self):
        """Override para crear asientos contables de préstamos"""
        result = super().button_validate()
        
        # Crear asientos contables si es préstamo y está configurado
        if self.is_loan and self.state == 'done':
            self._create_loan_accounting_entries()
        
        return result

    def _create_loan_accounting_entries(self):
        """Crear asientos contables para el préstamo"""
        accounting_manager = self.env['loan.accounting.manager'].get_default_config()
        
        # Crear asiento de compromiso
        if accounting_manager.create_commitment_entries:
            commitment_move = accounting_manager.create_loan_commitment_entry(self)
            if commitment_move:
                self.message_post(
                    body=f"Asiento de compromiso creado: {commitment_move.name}",
                    subject="Asiento Contable de Préstamo"
                )

    def action_view_accounting_entries(self):
        """Ver asientos contables relacionados con el préstamo"""
        return {
            'name': f'Asientos Contables - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('loan_picking_id', '=', self.id)],
            'context': {'create': False}
        }


class SaleOrderLoanAccounting(models.Model):
    _inherit = 'sale.order'
    
    def action_confirm(self):
        """Override para manejar contabilidad de conversiones de préstamos"""
        result = super().action_confirm()
        
        # Si es una conversión de préstamo, crear ajustes contables
        if self.origin and 'préstamo' in self.origin.lower():
            self._process_loan_conversion_accounting()
        
        return result

    def _process_loan_conversion_accounting(self):
        """Procesar contabilidad de conversión de préstamos"""
        accounting_manager = self.env['loan.accounting.manager'].get_default_config()
        
        for line in self.order_line:
            # Buscar costo original del préstamo
            original_cost = self._get_original_loan_cost(line.product_id)
            
            if original_cost and original_cost != line.price_unit:
                # Crear ajuste por diferencia
                adjustment_move = accounting_manager.create_loan_conversion_adjustment(
                    self, original_cost, line.price_unit
                )
                
                if adjustment_move:
                    self.message_post(
                        body=f"Ajuste contable por conversión: {adjustment_move.name}",
                        subject="Ajuste por Conversión de Préstamo"
                    )

    def _get_original_loan_cost(self, product):
        """Obtener costo original del producto en préstamo"""
        if not self.origin:
            return None
        
        # Buscar préstamo original por referencia en origin
        loan_picking = self.env['stock.picking'].search([
            ('name', 'in', self.origin.split()),
            ('is_loan', '=', True)
        ], limit=1)
        
        if not loan_picking:
            return None
        
        # Buscar detalle de seguimiento
        tracking_detail = self.env['loan.tracking.detail'].search([
            ('picking_id', '=', loan_picking.id),
            ('product_id', '=', product.id),
            ('status', '=', 'active')
        ], limit=1)
        
        return tracking_detail.original_cost if tracking_detail else None