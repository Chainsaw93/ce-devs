# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    # Campos de stock mejorados
    qty_available_real = fields.Float(
        'Cantidad Real Disponible',
        compute='_compute_qty_available_real',
        help="Stock disponible excluyendo préstamos activos",
        digits='Product Unit of Measure'
    )
    
    qty_in_loans = fields.Float(
        'Cantidad en Préstamos',
        compute='_compute_qty_in_loans',
        help="Cantidad actualmente en préstamos activos",
        digits='Product Unit of Measure'
    )
    
    qty_reserved_for_loans = fields.Float(
        'Cantidad Reservada para Préstamos',
        compute='_compute_qty_reserved_for_loans',
        help="Cantidad reservada en borradores de préstamos",
        digits='Product Unit of Measure'
    )
    
    # Campos para productos con números de serie
    serial_numbers_in_loans = fields.Char(
        'Números de Serie en Préstamos',
        compute='_compute_serial_loans_status',
        help="Números de serie actualmente en préstamos"
    )
    
    loan_history_count = fields.Integer(
        'Historial de Préstamos',
        compute='_compute_loan_history_count'
    )
    
    # Campos de configuración para préstamos
    allow_loans = fields.Boolean(
        'Permitir Préstamos',
        default=True,
        help="Determina si este producto puede ser prestado"
    )
    
    loan_warning = fields.Text(
        'Advertencia de Préstamo',
        help="Mensaje de advertencia al crear préstamos con este producto"
    )
    
    min_loan_qty = fields.Float(
        'Cantidad Mínima de Préstamo',
        default=1.0,
        help="Cantidad mínima que se puede prestar de este producto"
    )

    @api.depends('stock_quant_ids.quantity', 'stock_quant_ids.location_id')
    def _compute_qty_available_real(self):
        """Stock disponible excluyendo préstamos activos"""
        for product in self:
            # Stock tradicional
            traditional_qty = product.qty_available
            
            # Restar préstamos activos
            loan_qty = product._get_active_loans_qty()
            
            product.qty_available_real = max(0, traditional_qty - loan_qty)

    def _compute_qty_in_loans(self):
        """Cantidad actualmente en préstamos activos"""
        for product in self:
            product.qty_in_loans = product._get_active_loans_qty()

    def _compute_qty_reserved_for_loans(self):
        """Cantidad reservada en borradores de préstamos"""
        for product in self:
            reserved_qty = 0.0
            
            # Buscar movimientos draft en almacenes de préstamos
            draft_moves = self.env['stock.move'].search([
                ('product_id', '=', product.id),
                ('state', 'in', ['draft', 'waiting', 'confirmed', 'assigned']),
                ('picking_id.is_loan', '=', True)
            ])
            
            for move in draft_moves:
                reserved_qty += move.product_uom_qty
                
            product.qty_reserved_for_loans = reserved_qty

    def _compute_serial_loans_status(self):
        """Estado de préstamo para productos con números de serie"""
        for product in self:
            if product.tracking == 'serial':
                # Buscar lotes de este producto que estén en préstamos activos
                lots_in_loans = self.env['stock.lot'].search([
                    ('product_id', '=', product.id)
                ]).filtered(lambda lot: lot._is_in_active_loan())
                
                serial_numbers = lots_in_loans.mapped('name')
                product.serial_numbers_in_loans = ', '.join(serial_numbers) if serial_numbers else ''
            else:
                product.serial_numbers_in_loans = ''

    def _compute_loan_history_count(self):
        """Contar historial de préstamos para este producto"""
        for product in self:
            loan_count = self.env['loan.tracking.detail'].search_count([
                ('product_id', '=', product.id)
            ])
            product.loan_history_count = loan_count

    def _get_active_loans_qty(self):
        """Obtener cantidad en préstamos activos"""
        self.ensure_one()
        
        # Buscar almacenes de préstamos
        loan_warehouses = self.env['stock.warehouse'].search([
            ('warehouse_type', '=', 'loans')
        ])
        
        if not loan_warehouses:
            return 0.0
        
        loan_locations = loan_warehouses.mapped('lot_stock_id')
        
        # Buscar quants en ubicaciones de préstamos
        domain = [
            ('product_id', '=', self.id),
            ('location_id', 'child_of', loan_locations.ids),
            ('quantity', '>', 0)
        ]
        
        quants = self.env['stock.quant'].search(domain)
        return sum(quants.mapped('quantity'))

    def _get_available_qty_for_loans(self, location):
        """
        Obtener cantidad disponible para préstamos considerando reservas actuales
        Incluye validación de concurrencia
        """
        self.ensure_one()
        
        # Obtener stock disponible tradicional
        available_qty = self.with_context(location=location.id).qty_available
        
        # Restar cantidad ya reservada para otros préstamos
        reserved_for_loans = self.env['stock.move'].search([
            ('product_id', '=', self.id),
            ('location_id', '=', location.id),
            ('state', 'in', ['confirmed', 'assigned']),
            ('picking_id.is_loan', '=', True),
            ('picking_id.state', 'not in', ['done', 'cancel'])
        ])
        
        total_reserved = sum(reserved_for_loans.mapped('product_uom_qty'))
        
        # Cantidad realmente disponible para nuevos préstamos
        return max(0, available_qty - total_reserved)

    def action_view_loan_history(self):
        """Ver historial completo de préstamos para este producto"""
        return {
            'name': f'Historial de Préstamos - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'loan.tracking.detail',
            'view_mode': 'list,form',
            'domain': [('product_id', '=', self.id)],
            'context': {
                'create': False,
                'search_default_group_by_status': 1
            }
        }

    def action_view_current_loans(self):
        """Ver préstamos activos actuales de este producto"""
        return {
            'name': f'Préstamos Activos - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [
                ('move_ids_without_package.product_id', '=', self.id),
                ('is_loan', '=', True),
                ('loan_state', 'in', ['active', 'in_trial', 'partially_resolved'])
            ],
            'context': {'create': False}
        }

    @api.model
    def _search_qty_available_real(self, operator, value):
        """Permitir búsquedas por cantidad real disponible"""
        # Para búsquedas, calculamos en tiempo real
        products = self.search([])
        matching_products = []
        
        for product in products:
            product._compute_qty_available_real()
            if self._apply_operator(product.qty_available_real, operator, value):
                matching_products.append(product.id)
        
        return [('id', 'in', matching_products)]

    def _apply_operator(self, field_value, operator, search_value):
        """Aplicar operador de búsqueda"""
        if operator == '=':
            return field_value == search_value
        elif operator == '!=':
            return field_value != search_value
        elif operator == '>':
            return field_value > search_value
        elif operator == '>=':
            return field_value >= search_value
        elif operator == '<':
            return field_value < search_value
        elif operator == '<=':
            return field_value <= search_value
        elif operator in ('in', 'not in'):
            return field_value in search_value if operator == 'in' else field_value not in search_value
        return False

    def validate_loan_constraints(self, quantity, partner_id):
        """Validar restricciones específicas de préstamo"""
        self.ensure_one()
        
        # Producto permite préstamos
        if not self.allow_loans:
            raise UserError(_(
                f"El producto '{self.name}' no está habilitado para préstamos."
            ))
        
        # Cantidad mínima
        if quantity < self.min_loan_qty:
            raise UserError(_(
                f"La cantidad mínima de préstamo para '{self.name}' es {self.min_loan_qty:.2f}."
            ))
        
        # Para productos con número de serie
        if self.tracking == 'serial' and quantity != int(quantity):
            raise UserError(_(
                f"Los productos con número de serie solo permiten cantidades enteras. "
                f"Producto: {self.name}"
            ))
        
        # Validar límites del cliente si se proporciona partner_id
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id)
            self._validate_partner_loan_limits(partner, quantity)

    def _validate_partner_loan_limits(self, partner, quantity):
        """Validar límites de préstamo específicos del cliente"""
        # Validar número máximo de items
        if partner.max_loan_items > 0:
            current_items = self.env['loan.tracking.detail'].search_count([
                ('picking_id.owner_id', '=', partner.id),
                ('status', 'in', ['active', 'pending_resolution'])
            ])
            
            if current_items >= partner.max_loan_items:
                raise UserError(_(
                    f"El cliente {partner.name} ha alcanzado su límite de {partner.max_loan_items} "
                    f"items en préstamo simultáneamente."
                ))
        
        # Validar valor máximo (si está configurado)
        if partner.max_loan_value > 0:
            current_value = self._calculate_partner_loan_value(partner)
            new_value = quantity * self.list_price
            
            if current_value + new_value > partner.max_loan_value:
                raise UserError(_(
                    f"Este préstamo excedería el límite de valor ({partner.max_loan_value:.2f}) "
                    f"para el cliente {partner.name}.\n"
                    f"Valor actual: {current_value:.2f}\n"
                    f"Nuevo préstamo: {new_value:.2f}\n"
                    f"Total: {current_value + new_value:.2f}"
                ))

    def _calculate_partner_loan_value(self, partner):
        """Calcular valor actual de préstamos del cliente"""
        active_details = self.env['loan.tracking.detail'].search([
            ('picking_id.owner_id', '=', partner.id),
            ('status', 'in', ['active', 'pending_resolution'])
        ])
        
        total_value = 0.0
        for detail in active_details:
            product_price = detail.product_id.list_price
            total_value += detail.quantity * product_price
            
        return total_value


class StockLot(models.Model):
    _inherit = 'stock.lot'
    
    is_in_loan = fields.Boolean(
        'En Préstamo',
        compute='_compute_loan_status',
        help="Indica si este número de serie está actualmente en préstamo"
    )
    
    loan_history_ids = fields.One2many(
        'loan.tracking.detail',
        'lot_id',
        string='Historial de Préstamos'
    )

    @api.depends('quant_ids.location_id')
    def _compute_loan_status(self):
        """Determinar si el número de serie está en préstamo"""
        for lot in self:
            lot.is_in_loan = lot._is_in_active_loan()

    def _is_in_active_loan(self):
        """Verificar si el lote está en préstamo activo"""
        self.ensure_one()
        
        loan_warehouses = self.env['stock.warehouse'].search([
            ('warehouse_type', '=', 'loans')
        ])
        
        if not loan_warehouses:
            return False
        
        loan_locations = loan_warehouses.mapped('lot_stock_id')
        
        # Verificar si hay quants en ubicaciones de préstamos
        loan_quants = self.quant_ids.filtered(
            lambda q: q.location_id in loan_locations and q.quantity > 0
        )
        
        return bool(loan_quants)

    def action_view_loan_history(self):
        """Ver historial de préstamos para este número de serie"""
        return {
            'name': f'Historial de Préstamos - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'loan.tracking.detail',
            'view_mode': 'list,form',
            'domain': [('lot_id', '=', self.id)],
            'context': {'create': False}
        }
    
class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Campos computados similares pero para el template
    qty_available_real = fields.Float(
        'Cantidad Real Disponible',
        compute='_compute_qty_available_real',
        search='_search_qty_available_real',
        help="Stock disponible excluyendo préstamos activos",
        digits='Product Unit of Measure'
    )
    
    qty_in_loans = fields.Float(
        'Cantidad en Préstamos',
        compute='_compute_qty_in_loans',
        search='_search_qty_in_loans',
        help="Cantidad actualmente en préstamos activos",
        digits='Product Unit of Measure'
    )
    
    qty_reserved_for_loans = fields.Float(
        'Cantidad Reservada para Préstamos',
        compute='_compute_qty_reserved_for_loans',
        help="Cantidad reservada en borradores de préstamos",
        digits='Product Unit of Measure'
    )
    
    serial_numbers_in_loans = fields.Char(
        'Números de Serie en Préstamos',
        compute='_compute_serial_loans_status',
        help="Números de serie actualmente en préstamos"
    )
    
    loan_history_count = fields.Integer(
        'Historial de Préstamos',
        compute='_compute_loan_history_count',
        search='_search_loan_history_count'
    )
    
    # Campos de configuración para préstamos (ya existen en el template base)
    allow_loans = fields.Boolean(
        'Permitir Préstamos',
        default=True,
        help="Determina si este producto puede ser prestado"
    )
    
    loan_warning = fields.Text(
        'Advertencia de Préstamo',
        help="Mensaje de advertencia al crear préstamos con este producto"
    )
    
    min_loan_qty = fields.Float(
        'Cantidad Mínima de Préstamo',
        default=1.0,
        help="Cantidad mínima que se puede prestar de este producto"
    )

    def _compute_qty_available_real(self):
        """Calcular sumando todas las variantes"""
        for template in self:
            total_real = sum(template.product_variant_ids.mapped('qty_available_real'))
            template.qty_available_real = total_real

    def _compute_qty_in_loans(self):
        """Calcular sumando todas las variantes"""
        for template in self:
            total_loans = sum(template.product_variant_ids.mapped('qty_in_loans'))
            template.qty_in_loans = total_loans

    def _compute_qty_reserved_for_loans(self):
        """Calcular sumando todas las variantes"""
        for template in self:
            total_reserved = sum(template.product_variant_ids.mapped('qty_reserved_for_loans'))
            template.qty_reserved_for_loans = total_reserved

    def _compute_serial_loans_status(self):
        """Obtener números de serie de todas las variantes"""
        for template in self:
            if template.tracking == 'serial':
                all_serials = []
                for variant in template.product_variant_ids:
                    variant._compute_serial_loans_status()
                    if variant.serial_numbers_in_loans:
                        all_serials.append(variant.serial_numbers_in_loans)
                
                template.serial_numbers_in_loans = ', '.join(all_serials) if all_serials else ''
            else:
                template.serial_numbers_in_loans = ''

    def _compute_loan_history_count(self):
        """Contar historial para todas las variantes"""
        for template in self:
            loan_count = self.env['loan.tracking.detail'].search_count([
                ('product_id', 'in', template.product_variant_ids.ids)
            ])
            template.loan_history_count = loan_count

    def action_view_loan_history(self):
        """Ver historial completo de préstamos para todas las variantes"""
        variant_ids = self.product_variant_ids.ids
        return {
            'name': f'Historial de Préstamos - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'loan.tracking.detail',
            'view_mode': 'list,form',
            'domain': [('product_id', 'in', variant_ids)],
            'context': {
                'create': False,
                'search_default_group_by_status': 1
            }
        }

    def action_view_current_loans(self):
        """Ver préstamos activos actuales para todas las variantes"""
        variant_ids = self.product_variant_ids.ids
        return {
            'name': f'Préstamos Activos - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [
                ('move_ids_without_package.product_id', 'in', variant_ids),
                ('is_loan', '=', True),
                ('loan_state', 'in', ['active', 'in_trial', 'partially_resolved'])
            ],
            'context': {'create': False}
        }

    @api.model
    def _search_qty_in_loans(self, operator, value):
        """Método de búsqueda personalizado para qty_in_loans"""
        # Buscar productos con préstamos activos
        loan_details = self.env['loan.tracking.detail'].search([
            ('status', '=', 'active')
        ])
        
        # Agrupar por template
        template_quantities = {}
        for detail in loan_details:
            template_id = detail.product_id.product_tmpl_id.id
            if template_id not in template_quantities:
                template_quantities[template_id] = 0
            template_quantities[template_id] += detail.quantity
        
        # Filtrar según el operador
        matching_templates = []
        for template_id, qty in template_quantities.items():
            if self._apply_search_operator(qty, operator, value):
                matching_templates.append(template_id)
        
        # Si el operador es '>' y value es 0, incluir templates con préstamos
        if operator == '>' and value == 0:
            return [('id', 'in', matching_templates)]
        elif operator == '=' and value == 0:
            # Templates sin préstamos
            all_templates = self.search([]).ids
            templates_without_loans = [t for t in all_templates if t not in matching_templates]
            return [('id', 'in', templates_without_loans)]
        else:
            return [('id', 'in', matching_templates)]

    @api.model
    def _search_qty_available_real(self, operator, value):
        """Método de búsqueda personalizado para qty_available_real"""
        # Para simplificar, buscar todos los templates y calcular
        all_templates = self.search([])
        matching_templates = []
        
        for template in all_templates:
            template._compute_qty_available_real()
            if self._apply_search_operator(template.qty_available_real, operator, value):
                matching_templates.append(template.id)
        
        return [('id', 'in', matching_templates)]

    @api.model
    def _search_loan_history_count(self, operator, value):
        """Método de búsqueda personalizado para loan_history_count"""
        # Buscar templates que tienen historial de préstamos
        templates_with_history = self.env['loan.tracking.detail'].read_group([
            ('product_id.product_tmpl_id', '!=', False)
        ], ['product_id'], ['product_id'])
        
        template_counts = {}
        for group in templates_with_history:
            template_id = group['product_id'][0] if group['product_id'] else False
            if template_id:
                # Obtener el template_id desde product_id
                product = self.env['product.product'].browse(template_id)
                tmpl_id = product.product_tmpl_id.id
                if tmpl_id not in template_counts:
                    template_counts[tmpl_id] = 0
                template_counts[tmpl_id] += group['product_id_count']
        
        matching_templates = []
        for template_id, count in template_counts.items():
            if self._apply_search_operator(count, operator, value):
                matching_templates.append(template_id)
        
        if operator == '>' and value == 0:
            return [('id', 'in', matching_templates)]
        elif operator == '=' and value == 0:
            all_templates = self.search([]).ids
            templates_without_history = [t for t in all_templates if t not in matching_templates]
            return [('id', 'in', templates_without_history)]
        else:
            return [('id', 'in', matching_templates)]

    def _apply_search_operator(self, field_value, operator, search_value):
        """Aplicar operador de búsqueda"""
        if operator == '=':
            return field_value == search_value
        elif operator == '!=':
            return field_value != search_value
        elif operator == '>':
            return field_value > search_value
        elif operator == '>=':
            return field_value >= search_value
        elif operator == '<':
            return field_value < search_value
        elif operator == '<=':
            return field_value <= search_value
        elif operator in ('in', 'not in'):
            return field_value in search_value if operator == 'in' else field_value not in search_value
        return False