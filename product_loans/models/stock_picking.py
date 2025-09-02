# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    is_loan = fields.Boolean(
        string='Préstamo',
        readonly=True,
        help="Indica que esta transferencia es un préstamo de productos"
    )

    loan_return_origin_id = fields.Many2one(
        'stock.picking',
        string='Préstamo Original',
        help="Préstamo original si este picking es una devolución"
    )
    
    # NUEVO CAMPO: Reemplaza owner_id
    loaned_to_partner_id = fields.Many2one(
        'res.partner',
        string='Prestado a',
        help="Cliente al que se presta el producto"
    )
    
    loan_state = fields.Selection([
        ('active', 'Préstamo Activo'),
        ('in_trial', 'En Período de Prueba'),
        ('resolving', 'Resolviendo Préstamo'),
        ('partially_resolved', 'Parcialmente Resuelto'),
        ('completed', 'Completado')
    ], string='Estado del Préstamo', default='active')
    
    loan_expected_return_date = fields.Date(
        string='Fecha Esperada de Devolución',
        help="Fecha esperada para la devolución del préstamo"
    )
    
    trial_end_date = fields.Date(
        string='Fin del Período de Prueba',
        help="Fecha límite para que el cliente decida comprar o devolver"
    )
    
    loan_notes = fields.Text(
        string='Notas del Préstamo',
        help="Notas adicionales sobre el préstamo"
    )
    
    # Campos de integración con ventas
    conversion_sale_order_id = fields.Many2one(
        'sale.order', 
        string='Orden de Venta Generada',
        help="Orden de venta creada a partir de este préstamo"
    )
    
    # Campos para alertas y notificaciones
    overdue_days = fields.Integer(
        string='Días de Retraso',
        compute='_compute_overdue_days',
        store=True,
        help="Días transcurridos desde la fecha esperada de devolución"
    )
    
    is_overdue = fields.Boolean(
        string='Vencido',
        compute='_compute_overdue_days',
        store=True
    )
    
    # Campos para validaciones avanzadas
    bypass_stock_validation = fields.Boolean(
        string='Omitir Validación de Stock',
        help="Permitir préstamo sin validar stock disponible (solo administradores)"
    )
    
    bypass_reason = fields.Text(
        string='Razón para Omitir Validación',
        help="Justificación para omitir validaciones estándar"
    )
    
    # Campos de trazabilidad
    loan_tracking_detail_ids = fields.One2many(
        'loan.tracking.detail',
        'picking_id',
        string='Detalles de Seguimiento'
    )

    loan_operation_type = fields.Selection([
        ('loan', 'Préstamo'),
        ('return', 'Devolución'),
        ('standard', 'Estándar')
    ], string='Tipo de Operación', compute='_compute_loan_operation_type', store=True)
    
    loan_display_state = fields.Char(
        string='Estado del Préstamo',
        compute='_compute_loan_display_state',
        store=True,
        help="Estado legible del préstamo para mostrar en vistas"
    )


    @api.model
    def create(self, vals):
        """Override create para configuración automática de préstamos"""
        picking = super().create(vals)
        
        # Verificar si es préstamo automáticamente
        if (picking.picking_type_id and 
            picking.picking_type_id.warehouse_id and 
            picking.picking_type_id.warehouse_id.warehouse_type == 'loans'):
            picking.is_loan = True
            picking._setup_loan_location()
            
        return picking

    @api.depends('loan_expected_return_date', 'loan_state')
    def _compute_overdue_days(self):
        """Calcular días de retraso para préstamos"""
        today = fields.Date.today()
        for picking in self:
            if (picking.is_loan and 
                picking.loan_expected_return_date and 
                picking.loan_state in ['active', 'in_trial', 'partially_resolved']):
                
                delta = today - picking.loan_expected_return_date
                picking.overdue_days = max(0, delta.days)
                picking.is_overdue = picking.overdue_days > 0
            else:
                picking.overdue_days = 0
                picking.is_overdue = False

    @api.constrains('loaned_to_partner_id', 'is_loan', 'picking_type_id', 'bypass_stock_validation')
    def _check_loan_requirements(self):
        """Validaciones mejoradas para préstamos con bypass opcional"""
        for picking in self:
            if picking.is_loan:
                # Validar cliente destino
                if not picking.loaned_to_partner_id:
                    raise UserError(_("Los préstamos deben tener un cliente destino asignado."))
                
                # Validar que sea transferencia interna
                if picking.picking_type_id.code != 'internal':
                    raise UserError(_("Los préstamos solo pueden ser transferencias internas."))
                
                # Validación de stock avanzada (opcional)
                if not picking.bypass_stock_validation:
                    picking._validate_advanced_stock_availability()
                elif not picking.bypass_reason:
                    raise UserError(_(
                        "Debe proporcionar una razón para omitir la validación de stock."
                    ))

    def _validate_advanced_stock_availability(self):
        """Validación avanzada considerando reservas y movimientos pendientes"""
        for move in self.move_ids_without_package:
            if move.product_uom_qty <= 0:
                continue
                
            # Obtener disponibilidad real considerando reservas
            available_qty = move.product_id._get_available_qty_for_loans(
                move.location_id
            )
            
            if move.product_uom_qty > available_qty:
                raise UserError(_(
                    f"Stock insuficiente para préstamo:\n"
                    f"Producto: {move.product_id.name}\n"
                    f"Ubicación: {move.location_id.name}\n"
                    f"Solicitado: {move.product_uom_qty:.2f}\n"
                    f"Disponible para préstamos: {available_qty:.2f}\n\n"
                    f"Considere usar 'Omitir Validación de Stock' con justificación apropiada."
                ))

    def _setup_loan_location(self):
        """Configurar ubicación de destino según estrategia del cliente"""
        if not self.loaned_to_partner_id:
            return
            
        strategy = self._get_location_strategy()
        location = strategy['location']
        
        if self.location_dest_id != location:
            self.location_dest_id = location
            
        # Actualizar movimientos si existen
        for move in self.move_ids_without_package:
            move.location_dest_id = location

    def _get_location_strategy(self):
        """Determinar estrategia de ubicación según perfil del cliente"""
        loan_frequency = self.env['stock.picking'].search_count([
            ('loaned_to_partner_id', '=', self.loaned_to_partner_id.id),
            ('is_loan', '=', True),
            ('create_date', '>=', fields.Date.today() - timedelta(days=365))
        ])
        
        if loan_frequency >= 3:  # Cliente frecuente
            return {
                'location': self.loaned_to_partner_id._get_or_create_dedicated_location(),
                'type': 'dedicated'
            }
        else:  # Cliente ocasional
            return {
                'location': self._get_shared_temporary_location(),
                'type': 'shared'
            }

    def _get_shared_temporary_location(self):
        """Ubicación compartida para préstamos ocasionales"""
        loan_warehouse = self.env['stock.warehouse'].search([
            ('warehouse_type', '=', 'loans')
        ], limit=1)
        
        if not loan_warehouse:
            raise UserError(_("No se encontró almacén de préstamos configurado."))
        
        # Buscar o crear ubicación temporal compartida
        temp_location = self.env['stock.location'].search([
            ('name', '=', 'Préstamos Temporales'),
            ('location_id', '=', loan_warehouse.lot_stock_id.id)
        ], limit=1)
        
        if not temp_location:
            temp_location = self.env['stock.location'].create({
                'name': 'Préstamos Temporales',
                'location_id': loan_warehouse.lot_stock_id.id,
                'usage': 'internal',
                'comment': 'Ubicación compartida para préstamos ocasionales'
            })
        
        return temp_location

    def write(self, vals):
        """Override write para manejar cambios de estado"""
        # Validar cambios críticos
        if 'loan_state' in vals:
            for picking in self:
                if picking.is_loan:
                    picking._validate_state_transition(vals['loan_state'])
        
        # Manejo estándar
        if 'location_dest_id' in vals and any(p.is_loan for p in self):
            if self.env.context.get('from_loans_menu'):
                vals.pop('location_dest_id')
        
        res = super().write(vals)
           
        if any(key in vals for key in ['state', 'loan_state', 'is_loan']) and any(p.is_loan or p.loan_return_origin_id for p in self):
            for picking in self:
                if picking.is_loan or picking.loan_return_origin_id:
                    picking._trigger_quantity_recalculation()
        
        return res
    
 
    def _get_already_returned_qty(self, product_id):
        """Obtener cantidad ya devuelta previamente de un producto"""
        self.ensure_one()
        
        # Buscar devoluciones previas completadas
        returned_pickings = self.env['stock.picking'].search([
            ('loan_return_origin_id', '=', self.id),
            ('state', '=', 'done')
        ])
        
        total_returned = 0.0
        for picking in returned_pickings:
            for move in picking.move_ids_without_package:
                if move.product_id.id == product_id.id:
                    total_returned += sum(move.move_line_ids.mapped('qty_done'))
        
        return total_returned
    
    def _setup_loan_return_hooks(self, original_loan_picking):
        """Configurar hooks para actualización automática cuando se valide la devolución"""
        self.ensure_one()
        
        # Almacenar referencia al préstamo original
        self.loan_return_origin_id = original_loan_picking.id
        
        # El resto del procesamiento se hará en button_validate cuando se valide

    

    def _validate_state_transition(self, new_state):
        """Validar transiciones de estado válidas"""
        valid_transitions = {
            'active': ['in_trial', 'resolving'],
            'in_trial': ['resolving', 'completed'],
            'resolving': ['partially_resolved', 'completed'],
            'partially_resolved': ['resolving', 'completed'],
            'completed': []
        }
        
        if (self.loan_state and 
            new_state not in valid_transitions.get(self.loan_state, [])):
            raise ValidationError(_(
                f"Transición de estado no válida: {self.loan_state} → {new_state}"
            ))

    def button_validate(self):
        """Override para manejar actualizaciones automáticas de préstamos"""
        # Llamar al método original
        res = super().button_validate()
        
        # CORRECCIÓN 1: Si esta es una devolución de préstamo, actualizar estados
        if self.state == 'done' and self.loan_return_origin_id:
            self._update_loan_tracking_on_return()
            # CORRECCIÓN 3: Trigger recálculo de cantidades
            self._trigger_quantity_recalculation()
        
        # CORRECCIÓN 3: Si es un préstamo que se está validando, también trigger recálculo
        if self.state == 'done' and self.is_loan:
            self._trigger_quantity_recalculation()
        
        return res
    
    def _update_loan_tracking_on_return(self):
        """Actualizar registros de loan.tracking.detail cuando se valida una devolución"""
        self.ensure_one()
        
        if not self.loan_return_origin_id:
            return
        
        original_loan = self.loan_return_origin_id
        
        # Procesar cada movimiento de la devolución
        for return_move in self.move_ids_without_package:
            qty_returned = sum(return_move.move_line_ids.mapped('qty_done'))
            
            if qty_returned <= 0:
                continue
            
            # Buscar registros de tracking activos para este producto
            if return_move.product_id.tracking == 'serial':
                # Para productos con serie, marcar cada serie como devuelta
                for move_line in return_move.move_line_ids:
                    if move_line.lot_id and move_line.qty_done > 0:
                        tracking_records = self.env['loan.tracking.detail'].search([
                            ('picking_id', '=', original_loan.id),
                            ('product_id', '=', return_move.product_id.id),
                            ('lot_id', '=', move_line.lot_id.id),
                            ('status', '=', 'active')
                        ])
                        
                        for record in tracking_records:
                            record.action_mark_as_returned(
                                return_picking=self,
                                condition='good',  # Podríamos hacer esto configurable
                                notes=f"Devuelto automáticamente el {fields.Datetime.now()}"
                            )
            else:
                # Para productos sin serie, marcar cantidad devuelta
                tracking_records = self.env['loan.tracking.detail'].search([
                    ('picking_id', '=', original_loan.id),
                    ('product_id', '=', return_move.product_id.id),
                    ('status', '=', 'active')
                ])
                
                remaining_qty = qty_returned
                for record in tracking_records:
                    if remaining_qty <= 0:
                        break
                        
                    if record.quantity <= remaining_qty:
                        # Devolver completamente este registro
                        record.action_mark_as_returned(
                            return_picking=self,
                            condition='good',
                            notes=f"Devuelto automáticamente el {fields.Datetime.now()}"
                        )
                        remaining_qty -= record.quantity
                    else:
                        # Devolución parcial - crear nuevo registro para la parte devuelta
                        # y ajustar el registro original
                        returned_record = record.copy({
                            'quantity': remaining_qty,
                            'status': 'returned_good',
                            'return_picking_id': self.id,
                            'resolution_date': fields.Datetime.now(),
                            'return_condition_notes': f"Devolución parcial automática el {fields.Datetime.now()}"
                        })
                        
                        record.quantity = record.quantity - remaining_qty
                        remaining_qty = 0
        
        # Actualizar estado del préstamo original
        self._update_original_loan_state(original_loan)

    def _update_original_loan_state(self, original_loan):
        """Actualizar estado del préstamo original según devoluciones"""
        # Verificar si quedan productos activos en préstamo
        active_tracking = self.env['loan.tracking.detail'].search([
            ('picking_id', '=', original_loan.id),
            ('status', '=', 'active')
        ])
        
        if not active_tracking:
            # No quedan productos en préstamo - completar préstamo
            original_loan.loan_state = 'completed'
        else:
            # Quedan algunos productos - parcialmente resuelto
            total_tracking = self.env['loan.tracking.detail'].search([
                ('picking_id', '=', original_loan.id)
            ])
            
            if len(active_tracking) < len(total_tracking):
                original_loan.loan_state = 'partially_resolved'

    def _trigger_quantity_recalculation(self):
        """Método centralizado para forzar recálculo de cantidades"""
        for product in self:
            try:
                # Forzar recálculo directo sin invalidación problemática
                product._compute_qty_available_real()
                product._compute_qty_in_loans()
                product._compute_qty_reserved_for_loans()
                
                # También el template si existe
                if hasattr(product, 'product_tmpl_id') and product.product_tmpl_id:
                    product.product_tmpl_id._compute_qty_available_real()
                    product.product_tmpl_id._compute_qty_in_loans()
                    product.product_tmpl_id._compute_qty_reserved_for_loans()
            except Exception:
                # Si falla, continuar sin interrumpir el flujo
                pass

    def _create_tracking_details(self):
        """Crear registros detallados de seguimiento por producto/serie"""
        tracking_details = []
        
        for move in self.move_ids_without_package:
            if move.product_id.tracking == 'serial':
                # Crear registro por cada número de serie
                for move_line in move.move_line_ids:
                    if move_line.lot_id and move_line.qty_done > 0:
                        tracking_details.append({
                            'picking_id': self.id,
                            'product_id': move.product_id.id,
                            'lot_id': move_line.lot_id.id,
                            'quantity': 1,  # Siempre 1 para series
                            'status': 'active',
                            'loan_date': self.date_done or fields.Datetime.now(),
                            'original_cost': move.product_id.standard_price,
                        })
            else:
                # Crear registro por cantidad total
                qty_done = sum(move.move_line_ids.mapped('qty_done'))
                if qty_done > 0:
                    tracking_details.append({
                        'picking_id': self.id,
                        'product_id': move.product_id.id,
                        'quantity': qty_done,
                        'status': 'active',
                        'loan_date': self.date_done or fields.Datetime.now(),
                        'original_cost': move.product_id.standard_price,
                    })
        
        # Crear registros en batch
        if tracking_details:
            self.env['loan.tracking.detail'].create(tracking_details)

    def action_create_loan_return(self):
        """Abrir wizard para crear devolución de préstamo"""
        if not self.is_loan:
            raise UserError(_("Solo se pueden devolver préstamos."))
        if self.state != 'done':
            raise UserError(_("Solo se pueden devolver préstamos completados."))
            
        return {
            'name': _('Devolver Préstamo'),
            'type': 'ir.actions.act_window',
            'res_model': 'loan.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_picking_id': self.id,
                'default_return_location_id': self.location_id.id,
            }
        }
    
    def action_resolve_loan_trial(self):
        """Abrir wizard para resolver período de prueba"""
        if not self.is_loan:
            raise UserError(_("Solo aplicable a préstamos."))
        if self.loan_state not in ['in_trial', 'active']:
            raise UserError(_("El préstamo debe estar en período de prueba o activo."))
            
        return {
            'name': _('Resolver Préstamo'),
            'type': 'ir.actions.act_window',
            'res_model': 'loan.resolution.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_picking_id': self.id,
            }
        }

    def action_start_trial_period(self):
        """Iniciar período de prueba para el préstamo"""
        if not self.is_loan or self.state != 'done':
            raise UserError(_("Solo préstamos completados pueden entrar en período de prueba."))
        
        return {
            'name': _('Configurar Período de Prueba'),
            'type': 'ir.actions.act_window',
            'res_model': 'loan.trial.config.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_picking_id': self.id,
                'default_trial_end_date': fields.Date.today() + timedelta(days=7),
            }
        }

    @api.model
    def _cron_check_overdue_loans(self):
        """Cron job para verificar préstamos vencidos y crear actividades"""
        overdue_pickings = self.search([
            ('is_overdue', '=', True),
            ('loan_state', 'in', ['active', 'in_trial', 'partially_resolved'])
        ])
        
        for picking in overdue_pickings:
            picking._create_overdue_activity()
        
        _logger.info(f"Procesados {len(overdue_pickings)} préstamos vencidos")

    def _create_overdue_activity(self):
        """Crear actividad para préstamo vencido"""
        existing_activity = self.env['mail.activity'].search([
            ('res_model', '=', 'stock.picking'),
            ('res_id', '=', self.id),
            ('activity_type_id.name', 'ilike', 'préstamo vencido'),
            ('date_deadline', '>=', fields.Date.today())
        ], limit=1)
        
        if existing_activity:
            return  # Ya existe actividad reciente
        
        activity_type = self.env.ref('mail.mail_activity_data_todo', False)
        if not activity_type:
            activity_type = self.env['mail.activity.type'].search([], limit=1)
        
        self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'res_model': 'stock.picking',
            'res_id': self.id,
            'summary': f'Préstamo Vencido - {self.name}',
            'note': f'''
                <p><strong>Préstamo vencido hace {self.overdue_days} días</strong></p>
                <p>Cliente: {self.loaned_to_partner_id.name}</p>
                <p>Fecha esperada de devolución: {self.loan_expected_return_date}</p>
                <p>Estado actual: {dict(self._fields['loan_state'].selection).get(self.loan_state)}</p>
                <p>Acciones recomendadas:</p>
                <ul>
                    <li>Contactar al cliente</li>
                    <li>Resolver el período de prueba si aplica</li>
                    <li>Procesar devolución</li>
                </ul>
            ''',
            'date_deadline': fields.Date.today(),
            'user_id': self.user_id.id or self.env.user.id,
        })

    @api.depends('is_loan', 'loan_return_origin_id', 'loan_state', 'state')
    def _compute_loan_operation_type(self):
        """Determinar tipo de operación para diferenciación visual"""
        for picking in self:
            if picking.loan_return_origin_id:
                picking.loan_operation_type = 'return'
            elif picking.is_loan:
                picking.loan_operation_type = 'loan'
            else:
                picking.loan_operation_type = 'standard'

    @api.depends('is_loan', 'loan_return_origin_id', 'loan_state', 'state')
    def _compute_loan_display_state(self):
        """Generar texto de estado legible para préstamos """
        for picking in self:
            # ORDEN CORRECTO: Primero verificar si es devolución
            if picking.loan_return_origin_id:
                # Es una devolución
                if picking.state == 'done':
                    picking.loan_display_state = 'Devolución Completada'
                elif picking.state in ['assigned', 'confirmed']:
                    picking.loan_display_state = 'Devolución Pendiente'
                else:
                    picking.loan_display_state = 'Devolución'
                    
            elif picking.is_loan:
                # Es un préstamo (no devolución)
                if picking.state != 'done':
                    state_mapping = {
                        'draft': 'Borrador',
                        'waiting': 'En Espera',
                        'confirmed': 'Confirmado', 
                        'assigned': 'Listo',
                        'cancel': 'Cancelado'
                    }
                    picking.loan_display_state = state_mapping.get(picking.state, 'Borrador')
                else:
                    # Préstamo validado
                    state_mapping = {
                        'completed': 'Devuelto',
                        'partially_resolved': 'Parcialmente Devuelto',
                        'in_trial': 'En Período de Prueba',
                        'resolving': 'Resolviendo'
                    }
                    
                    display_state = state_mapping.get(picking.loan_state, 'Activo')
                    
                    # Solo agregar VENCIDO si es estado activo
                    if (picking.loan_state == 'active' and picking.is_overdue):
                        display_state = 'Activo (VENCIDO)'
                    elif picking.loan_state == 'active':
                        display_state = 'Activo'
                        
                    picking.loan_display_state = display_state
            else:
                # Operación estándar
                picking.loan_display_state = ''


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    # Campos estadísticos de préstamos
    loan_count = fields.Integer(
        'Número de Préstamos',
        compute='_compute_loan_stats',
        search='_search_loan_count'
    )
    
    active_loans_count = fields.Integer(
        'Préstamos Activos',
        compute='_compute_loan_stats',
        search='_search_active_loans_count'
    )
    
    overdue_loans_count = fields.Integer(
        'Préstamos Vencidos',
        compute='_compute_loan_stats',
        search='_search_overdue_loans_count'
    )

    # Campo booleano para agrupación en vistas
    has_active_loans = fields.Boolean(
        'Tiene Préstamos Activos',
        compute='_compute_has_active_loans',
        search='_search_has_active_loans',
        help="Indica si el cliente tiene préstamos activos actualmente"
    )
   
    # Configuración de límites
    max_loan_value = fields.Monetary(
        'Valor Máximo de Préstamos',
        help="Valor máximo permitido en préstamos simultáneos"
    )
    
    max_loan_items = fields.Integer(
        'Máximo Items en Préstamo',
        default=0,
        help="Número máximo de productos diferentes en préstamo simultáneamente (0 = sin límite)"
    )
    
    # Ubicación dedicada
    dedicated_loan_location_id = fields.Many2one(
        'stock.location',
        'Ubicación de Préstamo Dedicada',
        help="Ubicación específica para préstamos de este cliente"
    )

    def _compute_loan_stats(self):
        """Calcular estadísticas de préstamos para el cliente"""
        for partner in self:
            try:
                loans = self.env['stock.picking'].search([
                    ('loaned_to_partner_id', '=', partner.id),  # CAMBIO AQUÍ
                    ('is_loan', '=', True)
                ])
                
                partner.loan_count = len(loans)
                partner.active_loans_count = len(loans.filtered(
                    lambda p: p.loan_state in ['active', 'in_trial', 'partially_resolved']
                ))
                partner.overdue_loans_count = len(loans.filtered('is_overdue'))
            except Exception:
                # Valores por defecto si hay error
                partner.loan_count = 0
                partner.active_loans_count = 0
                partner.overdue_loans_count = 0

    @api.depends('active_loans_count')
    def _compute_has_active_loans(self):
        """Calcular si tiene préstamos activos"""
        for partner in self:
            partner.has_active_loans = partner.active_loans_count > 0

    def _get_or_create_dedicated_location(self):
        """Crear o obtener ubicación dedicada para este cliente"""
        if self.dedicated_loan_location_id:
            return self.dedicated_loan_location_id
        
        loan_warehouse = self.env['stock.warehouse'].search([
            ('warehouse_type', '=', 'loans')
        ], limit=1)
        
        if not loan_warehouse:
            raise UserError(_("No se encontró almacén de préstamos configurado."))
        
        location = self.env['stock.location'].create({
            'name': f"Préstamos - {self.name}",
            'location_id': loan_warehouse.lot_stock_id.id,
            'usage': 'internal',
            'partner_id': self.id,
            'comment': f'Ubicación dedicada para préstamos del cliente {self.name}'
        })
        
        self.dedicated_loan_location_id = location.id
        return location

    @api.model
    def _search_loan_count(self, operator, value):
        """Método de búsqueda para loan_count"""
        # Obtener partners con préstamos
        partners_with_loans = self.env['stock.picking'].search([
            ('is_loan', '=', True)
        ]).mapped('loaned_to_partner_id.id')  # CAMBIO AQUÍ
        
        if operator == '>' and value == 0:
            return [('id', 'in', partners_with_loans)]
        elif operator == '=' and value == 0:
            all_partners = self.search([]).ids
            partners_without_loans = [p for p in all_partners if p not in partners_with_loans]
            return [('id', 'in', partners_without_loans)]
        else:
            # Para otros operadores, calcular exacto
            matching_partners = []
            for partner in self.browse(partners_with_loans):
                partner._compute_loan_stats()
                if self._apply_search_operator(partner.loan_count, operator, value):
                    matching_partners.append(partner.id)
            return [('id', 'in', matching_partners)]
        
    @api.model
    def _search_has_active_loans(self, operator, value):
        """Método de búsqueda para has_active_loans"""
        # Obtener partners con préstamos activos
        partners_with_active = self.env['stock.picking'].search([
            ('is_loan', '=', True),
            ('loan_state', 'in', ['active', 'in_trial', 'partially_resolved'])
        ]).mapped('loaned_to_partner_id.id')  # CAMBIO AQUÍ
        
        # Lógica según operador y valor
        if operator == '=' and value == True:
            return [('id', 'in', partners_with_active)]
        elif operator == '=' and value == False:
            all_partners = self.search([]).ids
            partners_without_active = [p for p in all_partners if p not in partners_with_active]
            return [('id', 'in', partners_without_active)]
        elif operator == '!=' and value == True:
            all_partners = self.search([]).ids
            partners_without_active = [p for p in all_partners if p not in partners_with_active]
            return [('id', 'in', partners_without_active)]
        elif operator == '!=' and value == False:
            return [('id', 'in', partners_with_active)]
        else:
            # Para otros operadores, devolver todos o ninguno
            if value:
                return [('id', 'in', partners_with_active)]
            else:
                return [('id', '=', False)]  # Ninguno

    @api.model
    def _search_active_loans_count(self, operator, value):
        """Método de búsqueda para active_loans_count"""
        # Obtener partners con préstamos activos
        partners_with_active = self.env['stock.picking'].search([
            ('is_loan', '=', True),
            ('loan_state', 'in', ['active', 'in_trial', 'partially_resolved'])
        ]).mapped('loaned_to_partner_id.id')  # CAMBIO AQUÍ
        
        if operator == '>' and value == 0:
            return [('id', 'in', partners_with_active)]
        elif operator == '=' and value == 0:
            all_partners = self.search([]).ids
            partners_without_active = [p for p in all_partners if p not in partners_with_active]
            return [('id', 'in', partners_without_active)]
        else:
            matching_partners = []
            for partner in self.browse(partners_with_active):
                partner._compute_loan_stats()
                if self._apply_search_operator(partner.active_loans_count, operator, value):
                    matching_partners.append(partner.id)
            return [('id', 'in', matching_partners)]

    @api.model
    def _search_overdue_loans_count(self, operator, value):
        """Método de búsqueda para overdue_loans_count"""
        # Obtener partners con préstamos vencidos
        partners_with_overdue = self.env['stock.picking'].search([
            ('is_loan', '=', True),
            ('is_overdue', '=', True)
        ]).mapped('loaned_to_partner_id.id')  # CAMBIO AQUÍ
        
        if operator == '>' and value == 0:
            return [('id', 'in', partners_with_overdue)]
        elif operator == '=' and value == 0:
            all_partners = self.search([]).ids
            partners_without_overdue = [p for p in all_partners if p not in partners_with_overdue]
            return [('id', 'in', partners_without_overdue)]
        else:
            matching_partners = []
            for partner in self.browse(partners_with_overdue):
                partner._compute_loan_stats()
                if self._apply_search_operator(partner.overdue_loans_count, operator, value):
                    matching_partners.append(partner.id)
            return [('id', 'in', matching_partners)]

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

    def action_view_loans(self):
        """Ver todos los préstamos del cliente"""
        return {
            'name': f'Préstamos - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('loaned_to_partner_id', '=', self.id), ('is_loan', '=', True)],  # CAMBIO AQUÍ
            'context': {'create': False}
        }
    
