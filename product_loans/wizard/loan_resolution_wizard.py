# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class LoanResolutionWizard(models.TransientModel):
    _name = 'loan.resolution.wizard'
    _description = 'Asistente para Resolución de Préstamos'

    # Información del préstamo
    picking_id = fields.Many2one(
        'stock.picking',
        string='Préstamo Original',
        required=True,
        readonly=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        related='picking_id.owner_id',
        string='Cliente',
        readonly=True
    )
    
    loan_date = fields.Datetime(
        related='picking_id.date_done',
        string='Fecha del Préstamo',
        readonly=True
    )
    
    # Configuración de la resolución
    resolution_date = fields.Datetime(
        string='Fecha de Resolución',
        default=fields.Datetime.now,
        required=True
    )
    
    notes = fields.Text(
        string='Notas de Resolución',
        help="Observaciones sobre la resolución del préstamo"
    )
    
    # Líneas de resolución
    resolution_line_ids = fields.One2many(
        'loan.resolution.wizard.line',
        'wizard_id',
        string='Productos a Resolver'
    )
    
    # Campos calculados automáticamente
    total_sale_amount = fields.Monetary(
        string='Total Venta',
        compute='_compute_totals',
        currency_field='currency_id',
        help="Monto total de productos que serán vendidos"
    )
    
    total_return_items = fields.Integer(
        string='Items a Devolver',
        compute='_compute_totals',
        help="Número de items que serán devueltos"
    )
    
    total_keep_loan_items = fields.Integer(
        string='Items que Permanecen en Préstamo',
        compute='_compute_totals',
        help="Número de items que siguen en préstamo"
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id
    )
    
    # Flags de estado
    has_sales = fields.Boolean(
        string='Tiene Ventas',
        compute='_compute_totals'
    )
    
    has_returns = fields.Boolean(
        string='Tiene Devoluciones',
        compute='_compute_totals'
    )
    
    has_continued_loans = fields.Boolean(
        string='Préstamos Continuos',
        compute='_compute_totals'
    )

    @api.model
    def default_get(self, fields_list):
        """Poblar automáticamente las líneas de resolución desde los detalles de seguimiento"""
        res = super().default_get(fields_list)
        
        if 'picking_id' in self.env.context:
            picking_id = self.env.context['picking_id']
            picking = self.env['stock.picking'].browse(picking_id)
            
            if picking.exists() and picking.is_loan:
                # Obtener detalles de seguimiento activos
                active_details = self.env['loan.tracking.detail'].search([
                    ('picking_id', '=', picking_id),
                    ('status', '=', 'active')
                ])
                
                resolution_lines = []
                for detail in active_details:
                    resolution_lines.append((0, 0, {
                        'tracking_detail_id': detail.id,
                        'product_id': detail.product_id.id,
                        'lot_id': detail.lot_id.id if detail.lot_id else False,
                        'loaned_qty': detail.quantity,
                        'resolution_type': 'keep_loan',  # Por defecto mantener préstamo
                        'qty_to_resolve': detail.quantity,
                    }))
                
                res['resolution_line_ids'] = resolution_lines
        
        return res

    @api.depends('resolution_line_ids.resolution_type', 'resolution_line_ids.qty_to_resolve', 'resolution_line_ids.unit_price')
    def _compute_totals(self):
        """Calcular totales basados en las decisiones de resolución"""
        for wizard in self:
            total_sale = 0.0
            return_items = 0
            keep_loan_items = 0
            has_sales = False
            has_returns = False
            has_continued = False
            
            for line in wizard.resolution_line_ids:
                if line.resolution_type == 'buy':
                    total_sale += line.qty_to_resolve * line.unit_price
                    has_sales = True
                elif line.resolution_type == 'return':
                    return_items += 1 if line.product_id.tracking == 'serial' else line.qty_to_resolve
                    has_returns = True
                elif line.resolution_type == 'keep_loan':
                    keep_loan_items += 1 if line.product_id.tracking == 'serial' else line.qty_to_resolve
                    has_continued = True
            
            wizard.total_sale_amount = total_sale
            wizard.total_return_items = return_items
            wizard.total_keep_loan_items = keep_loan_items
            wizard.has_sales = has_sales
            wizard.has_returns = has_returns
            wizard.has_continued_loans = has_continued

    def action_process_resolution(self):
        """Procesar la resolución del préstamo"""
        self.ensure_one()
        
        # Validaciones previas
        self._validate_resolution()
        
        results = {
            'sale_order': None,
            'return_picking': None,
            'continued_details': []
        }
        
        try:
            # 1. Procesar ventas
            if self.has_sales:
                results['sale_order'] = self._process_sales()
            
            # 2. Procesar devoluciones
            if self.has_returns:
                results['return_picking'] = self._process_returns()
            
            # 3. Mantener préstamos continuos
            if self.has_continued_loans:
                results['continued_details'] = self._process_continued_loans()
            
            # 4. Actualizar estado del préstamo original
            self._update_original_loan_state()
            
            return self._return_resolution_results(results)
            
        except Exception as e:
            raise UserError(_(
                f"Error al procesar la resolución del préstamo: {str(e)}"
            ))

    def _validate_resolution(self):
        """Validar que la resolución es consistente"""
        if not self.resolution_line_ids:
            raise UserError(_("No hay productos para resolver."))
        
        # Validar que todas las líneas tengan decisión
        unresolved_lines = self.resolution_line_ids.filtered(
            lambda l: not l.resolution_type
        )
        if unresolved_lines:
            raise UserError(_(
                "Todas las líneas deben tener un tipo de resolución definido."
            ))
        
        # Validar cantidades
        for line in self.resolution_line_ids:
            if line.qty_to_resolve <= 0:
                raise UserError(_(
                    f"La cantidad a resolver debe ser mayor a 0 para {line.product_id.name}"
                ))
            
            if line.qty_to_resolve > line.loaned_qty:
                raise UserError(_(
                    f"No se puede resolver más cantidad de la prestada para {line.product_id.name}. "
                    f"Prestado: {line.loaned_qty}, Intentando resolver: {line.qty_to_resolve}"
                ))
        
        # Validar precios para ventas
        sale_lines = self.resolution_line_ids.filtered(
            lambda l: l.resolution_type == 'buy'
        )
        for line in sale_lines:
            if line.unit_price <= 0:
                raise UserError(_(
                    f"El precio de venta debe ser mayor a 0 para {line.product_id.name}"
                ))

    def _process_sales(self):
        """Procesar productos que el cliente decide comprar"""
        sale_lines = self.resolution_line_ids.filtered(
            lambda l: l.resolution_type == 'buy'
        )
        
        if not sale_lines:
            return None
        
        # Crear orden de venta
        sale_order = self._create_sale_order(sale_lines)
        
        # Actualizar detalles de seguimiento
        for line in sale_lines:
            line.tracking_detail_id.action_mark_as_sold(
                sale_order.order_line.filtered(
                    lambda sol: sol.product_id == line.product_id and (
                        not line.lot_id or 
                        line.lot_id.name in (sol.name or '')
                    )
                )[:1],
                line.unit_price
            )
        
        return sale_order

    def _create_sale_order(self, sale_lines):
        """Crear orden de venta para productos comprados"""
        order_lines = []
        
        # Agrupar líneas por producto si no tienen números de serie específicos
        grouped_lines = {}
        for line in sale_lines:
            key = (line.product_id.id, line.unit_price)
            if line.product_id.tracking == 'serial':
                # Para productos con serie, una línea por cada número de serie
                key = (line.product_id.id, line.unit_price, line.lot_id.id if line.lot_id else 0)
            
            if key not in grouped_lines:
                grouped_lines[key] = {
                    'product_id': line.product_id.id,
                    'quantity': 0,
                    'price': line.unit_price,
                    'lot_name': line.lot_id.name if line.lot_id else None
                }
            
            grouped_lines[key]['quantity'] += line.qty_to_resolve
        
        # Crear líneas de orden de venta
        for group_data in grouped_lines.values():
            line_name = group_data['lot_name']
            if line_name:
                line_name = f"Conversión préstamo - S/N: {line_name}"
            else:
                line_name = "Conversión de préstamo"
            
            order_lines.append((0, 0, {
                'product_id': group_data['product_id'],
                'product_uom_qty': group_data['quantity'],
                'price_unit': group_data['price'],
                'name': line_name,
            }))
        
        # Crear la orden de venta
        sale_vals = {
            'partner_id': self.partner_id.id,
            'origin': f"Conversión préstamo {self.picking_id.name}",
            'note': f"Orden creada desde resolución de préstamo. Notas: {self.notes or 'N/A'}",
            'order_line': order_lines,
            'date_order': self.resolution_date,
        }
        
        sale_order = self.env['sale.order'].create(sale_vals)
        
        # Vincular con el préstamo original
        self.picking_id.conversion_sale_order_id = sale_order.id
        
        return sale_order

    def _process_returns(self):
        """Procesar productos que el cliente devuelve"""
        return_lines = self.resolution_line_ids.filtered(
            lambda l: l.resolution_type == 'return'
        )
        
        if not return_lines:
            return None
        
        # Crear picking de devolución
        return_picking = self._create_return_picking(return_lines)
        
        # Actualizar detalles de seguimiento como pendientes de resolución física
        for line in return_lines:
            line.tracking_detail_id.write({
                'status': 'pending_resolution',
                'notes': f"Marcado para devolución el {fields.Date.today()}. Condición: {line.return_condition}"
            })
        
        return return_picking

    def _create_return_picking(self, return_lines):
        """Crear picking de devolución"""
        # Determinar ubicación de destino
        main_warehouse = self.env['stock.warehouse'].search([
            ('warehouse_type', '!=', 'loans')
        ], limit=1)
        
        if not main_warehouse:
            raise UserError(_("No se encontró almacén principal para devoluciones."))
        
        # Determinar tipo de operación de devolución
        return_type = self.picking_id.picking_type_id  # Usar el mismo tipo por defecto
        
        # Crear picking de devolución
        picking_vals = {
            'partner_id': self.partner_id.id,
            'picking_type_id': return_type.id,
            'location_id': self.picking_id.location_dest_id.id,  # Desde ubicación de préstamo
            'location_dest_id': main_warehouse.lot_stock_id.id,  # A almacén principal
            'origin': f"Devolución {self.picking_id.name}",
            'note': f"Devolución procesada desde resolución de préstamo. Notas: {self.notes or 'N/A'}",
            'scheduled_date': self.resolution_date,
            'move_ids_without_package': []
        }
        
        # Crear movimientos
        moves = []
        for line in return_lines:
            move_vals = {
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_to_resolve,
                'product_uom': line.product_id.uom_id.id,
                'location_id': self.picking_id.location_dest_id.id,
                'location_dest_id': main_warehouse.lot_stock_id.id,
                'name': f"Devolución: {line.product_id.name}",
                'origin': f"Resolución {self.picking_id.name}",
                'state': 'draft',
            }
            
            # Para productos con número de serie, especificar el lote
            if line.lot_id:
                move_vals['lot_ids'] = [(4, line.lot_id.id)]
            
            moves.append((0, 0, move_vals))
        
        picking_vals['move_ids_without_package'] = moves
        return_picking = self.env['stock.picking'].create(picking_vals)
        
        # Confirmar automáticamente el picking
        return_picking.action_confirm()
        
        return return_picking

    def _process_continued_loans(self):
        """Procesar productos que siguen en préstamo"""
        continued_lines = self.resolution_line_ids.filtered(
            lambda l: l.resolution_type == 'keep_loan'
        )
        
        continued_details = []
        
        for line in continued_lines:
            # Mantener el detalle de seguimiento como activo
            line.tracking_detail_id.write({
                'notes': f"Préstamo extendido el {fields.Date.today()}. Resolución: mantener en préstamo."
            })
            continued_details.append(line.tracking_detail_id)
        
        return continued_details

    def _update_original_loan_state(self):
        """Actualizar el estado del préstamo original basado en la resolución"""
        # Determinar nuevo estado basado en qué quedó pendiente
        if self.has_continued_loans:
            new_state = 'partially_resolved'
        else:
            new_state = 'completed'
        
        self.picking_id.write({
            'loan_state': new_state,
            'loan_notes': (self.picking_id.loan_notes or '') + f"\n\nResolución {fields.Date.today()}: {self.notes or 'Procesado'}"
        })

    def _return_resolution_results(self, results):
        """Retornar vista con resultados de la resolución"""
        message_parts = ["Resolución de préstamo procesada exitosamente:"]
        actions = []
        
        if results['sale_order']:
            message_parts.append(f"• Orden de venta creada: {results['sale_order'].name}")
            actions.append({
                'name': 'Ver Orden de Venta',
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': results['sale_order'].id,
                'view_mode': 'form',
                'target': 'new'
            })
        
        if results['return_picking']:
            message_parts.append(f"• Devolución creada: {results['return_picking'].name}")
            actions.append({
                'name': 'Ver Devolución',
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'res_id': results['return_picking'].id,
                'view_mode': 'form',
                'target': 'new'
            })
        
        if results['continued_details']:
            count = len(results['continued_details'])
            message_parts.append(f"• {count} item(s) continúan en préstamo")
        
        # Mostrar mensaje de resumen
        message = "\n".join(message_parts)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Resolución Completada',
                'message': message,
                'type': 'success',
                'sticky': True,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'stock.picking',
                    'res_id': self.picking_id.id,
                    'view_mode': 'form',
                    'target': 'current'
                }
            }
        }


class LoanResolutionWizardLine(models.TransientModel):
    _name = 'loan.resolution.wizard.line'
    _description = 'Línea de Resolución de Préstamo'

    wizard_id = fields.Many2one(
        'loan.resolution.wizard',
        required=True,
        ondelete='cascade'
    )
    
    tracking_detail_id = fields.Many2one(
        'loan.tracking.detail',
        string='Detalle de Seguimiento',
        required=True,
        readonly=True
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        readonly=True
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Número de Serie/Lote',
        readonly=True
    )
    
    loaned_qty = fields.Float(
        string='Cantidad Prestada',
        readonly=True,
        digits='Product Unit of Measure'
    )
    
    qty_to_resolve = fields.Float(
        string='Cantidad a Resolver',
        required=True,
        digits='Product Unit of Measure',
        help="Cantidad que se resolverá con la decisión seleccionada"
    )
    
    resolution_type = fields.Selection([
        ('buy', 'Comprar'),
        ('return', 'Devolver'),
        ('keep_loan', 'Mantener Préstamo')
    ], string='Decisión', required=True, default='keep_loan')
    
    # Campos para venta
    unit_price = fields.Float(
        string='Precio Unitario',
        digits='Product Price',
        help="Precio por unidad si se decide comprar"
    )
    
    total_price = fields.Float(
        string='Total',
        compute='_compute_total_price',
        digits='Product Price'
    )
    
    # Campos para devolución
    return_condition = fields.Selection([
        ('good', 'Buen Estado'),
        ('damaged', 'Dañado'),
        ('defective', 'Defectuoso')
    ], string='Condición', default='good')
    
    notes = fields.Text(
        string='Observaciones',
        help="Notas específicas para este item"
    )

    @api.depends('qty_to_resolve', 'unit_price')
    def _compute_total_price(self):
        """Calcular precio total"""
        for line in self:
            line.total_price = line.qty_to_resolve * line.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Auto-llenar precio basado en lista de precios del producto"""
        if self.product_id:
            self.unit_price = self.product_id.list_price

    @api.onchange('resolution_type')
    def _onchange_resolution_type(self):
        """Manejar cambios en el tipo de resolución"""
        if self.resolution_type == 'buy':
            # Auto-llenar precio si no está establecido
            if not self.unit_price and self.product_id:
                self.unit_price = self.product_id.list_price
        elif self.resolution_type in ('return', 'keep_loan'):
            # Limpiar campos de precio
            self.unit_price = 0.0

    @api.constrains('qty_to_resolve', 'loaned_qty')
    def _check_quantity_consistency(self):
        """Validar consistencia de cantidades"""
        for line in self:
            if line.qty_to_resolve > line.loaned_qty:
                raise ValidationError(_(
                    f"No se puede resolver más cantidad de la prestada para {line.product_id.name}. "
                    f"Prestado: {line.loaned_qty}, Intentando resolver: {line.qty_to_resolve}"
                ))
            
            if line.qty_to_resolve <= 0:
                raise ValidationError(_(
                    f"La cantidad a resolver debe ser mayor a 0 para {line.product_id.name}"
                ))
            
            # Para productos con número de serie, solo se permiten cantidades enteras de 1
            if (line.product_id.tracking == 'serial' and 
                line.qty_to_resolve != 1):
                raise ValidationError(_(
                    f"Los productos con número de serie solo permiten cantidades de 1. "
                    f"Producto: {line.product_id.name}"
                ))

    @api.constrains('unit_price', 'resolution_type')
    def _check_sale_price(self):
        """Validar precio de venta"""
        for line in self:
            if line.resolution_type == 'buy' and line.unit_price <= 0:
                raise ValidationError(_(
                    f"El precio de venta debe ser mayor a 0 para {line.product_id.name}"
                ))