# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import UserError


class LoanReturnWizard(models.TransientModel):
    _name = 'loan.return.wizard'
    _description = 'Asistente para Devolución de Préstamos'

    picking_id = fields.Many2one('stock.picking', string='Préstamo Original', required=True)
    return_location_id = fields.Many2one(
        'stock.location', 
        string='Ubicación de Devolución', 
        required=True,
        domain=[('usage', 'in', ('internal', 'transit'))]
    )
    return_date = fields.Datetime(
        string='Fecha de Devolución', 
        default=fields.Datetime.now, 
        required=True
    )
    notes = fields.Text(string='Notas de Devolución')
    move_line_ids = fields.One2many(
        'loan.return.wizard.line', 
        'wizard_id', 
        string='Productos a Devolver'
    )

    @api.model
    def default_get(self, fields_list):
        """Poblar automáticamente las líneas de productos del préstamo original"""
        res = super().default_get(fields_list)
        
        if 'picking_id' in self.env.context:
            picking_id = self.env.context['picking_id']
            picking = self.env['stock.picking'].browse(picking_id)
            
            # Validación anti-bucles
            if not picking.exists():
                raise UserError(_("El préstamo especificado no existe."))
                
            if not picking.is_loan:
                raise UserError(_("Solo se pueden devolver préstamos. Este registro no es un préstamo."))
                
            if picking.state != 'done':
                raise UserError(_("Solo se pueden devolver préstamos completados."))
                
            # VALIDACIÓN: Verificar si ya es una devolución
            if picking.origin and 'Devolución de' in picking.origin:
                raise UserError(_(
                    "Este picking ya es una devolución. No se pueden crear devoluciones de devoluciones.\n"
                    f"Origen: {picking.origin}"
                ))
                
            # VALIDACIÓN: Verificar si el préstamo ya está completamente devuelto
            if picking.loan_state == 'completed':
                raise UserError(_("Este préstamo ya está completado. No se pueden crear más devoluciones."))
            
            move_lines = []
            for move in picking.move_ids_without_package:
                qty_done = sum(move.move_line_ids.mapped('qty_done'))
                
                # VALIDACIÓN: Solo incluir productos que aún pueden devolverse
                if qty_done > 0:
                    # Verificar si hay cantidad pendiente de devolver
                    returned_qty = picking._get_already_returned_qty(move.product_id)
                    pending_qty = qty_done - returned_qty
                    
                    if pending_qty > 0:
                        move_lines.append((0, 0, {
                            'product_id': move.product_id.id,
                            'original_qty': qty_done,
                            'returned_qty': returned_qty,
                            'pending_qty': pending_qty,
                            'return_qty': pending_qty,  # Por defecto devolver todo lo pendiente
                            'product_uom_id': move.product_uom.id,
                        }))
                        
            if not move_lines:
                raise UserError(_("No hay productos pendientes de devolver en este préstamo."))
                
            res['move_line_ids'] = move_lines
        
        return res

    def action_create_return(self):
        """Crear transferencia de devolución"""
        self.ensure_one()
        
        # Validaciones adicionales
        self._validate_return_conditions()

        # Validar que al menos un producto tenga cantidad a devolver
        if not any(line.return_qty > 0 for line in self.move_line_ids):
            raise UserError(_("Debe especificar al menos un producto para devolver."))

        # Crear picking de devolución
        return_picking_vals = {
            'partner_id': self.picking_id.partner_id.id,
            'loaned_to_partner_id': self.picking_id.loaned_to_partner_id.id,
            'picking_type_id': self._get_return_picking_type(),
            'location_id': self.picking_id.location_dest_id.id,
            'location_dest_id': self.return_location_id.id,
            'origin': f"Devolución de {self.picking_id.name}",
            'scheduled_date': self.return_date,
            'is_loan': False,  # La devolución no es un préstamo
            'note': self.notes or f"Devolución automática del préstamo {self.picking_id.name}",
            'loan_return_origin_id': self.picking_id.id, # Referencia al préstamo original para tracking
        }

        # Crear movimientos basados en las líneas seleccionadas
        move_vals = []
        for line in self.move_line_ids:
            if line.return_qty > 0:
                move_vals.append((0, 0, {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.return_qty,
                    'product_uom': line.product_uom_id.id,
                    'location_id': self.picking_id.location_dest_id.id,
                    'location_dest_id': self.return_location_id.id,
                    'name': f"Devolución: {line.product_id.name}",
                    'loan_return_qty': line.return_qty,# NUEVO: Referencia para tracking
                }))

        return_picking_vals['move_ids_without_package'] = move_vals
        return_picking = self.env['stock.picking'].create(return_picking_vals)

        # Configurar hook para actualización automática de estado
        return_picking._setup_loan_return_hooks(self.picking_id)

        return {
            'name': _('Devolución Creada'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': return_picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _validate_return_conditions(self):
        """Validaciones completas antes de crear devolución"""
        if not self.picking_id.is_loan or self.picking_id.state != 'done':
            raise UserError(_("Solo se pueden devolver préstamos completados."))
            
        # Validar que no sea ya una devolución
        if self.picking_id.origin and 'Devolución de' in self.picking_id.origin:
            raise UserError(_("No se pueden crear devoluciones de devoluciones."))
            
        # Validar fechas
        if self.return_date < self.picking_id.date_done:
            raise UserError(_(
                "La fecha de devolución no puede ser anterior a la fecha del préstamo original."
            ))
    
    def _get_return_picking_type(self):
        """Obtener el tipo de operación apropiado para la devolución"""
        # Intentar usar el mismo tipo de operación del préstamo original pero invertido
        original_type = self.picking_id.picking_type_id
        
        # Si es del almacén de préstamos, buscar el tipo de devolución
        if original_type.warehouse_id.warehouse_type == 'loans':
            # Buscar tipo de devolución en el mismo almacén
            return_type = self.env['stock.picking.type'].search([
                ('warehouse_id', '=', original_type.warehouse_id.id),
                ('code', '=', 'internal'),
                ('default_location_src_id', '=', original_type.default_location_dest_id.id),
                ('active', '=', True)
            ], limit=1)
            
            if return_type:
                return return_type.id
        
        # Como fallback, usar el mismo tipo del préstamo original
        return original_type.id


class LoanReturnWizardLine(models.TransientModel):
    _name = 'loan.return.wizard.line'
    _description = 'Línea de Asistente para Devolución de Préstamos'

    wizard_id = fields.Many2one('loan.return.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    original_qty = fields.Float(string='Cantidad Original', readonly=True)
    # NUEVOS CAMPOS: Para tracking de devoluciones parciales
    returned_qty = fields.Float(string='Ya Devuelto', readonly=True, help="Cantidad ya devuelta previamente")
    pending_qty = fields.Float(string='Pendiente', readonly=True, help="Cantidad pendiente de devolver")
    return_qty = fields.Float(
        string='Cantidad a Devolver', 
        required=True,
        help="Cantidad que se devolverá en esta operación."
    )
    product_uom_id = fields.Many2one('uom.uom', string='Unidad de Medida', required=True)

    @api.constrains('return_qty', 'pending_qty')
    def _check_return_qty(self):
        """Validar que la cantidad a devolver sea válida"""
        for line in self:
            if line.return_qty < 0:
                raise UserError(_("La cantidad a devolver no puede ser negativa."))
            if line.return_qty > line.pending_qty:
                raise UserError(_(
                    f"La cantidad a devolver ({line.return_qty}) no puede ser mayor "
                    f"a la cantidad pendiente ({line.pending_qty}) para el producto {line.product_id.name}."
                ))

    @api.onchange('return_qty')
    def _onchange_return_qty(self):
        """Validar cambios en tiempo real"""
        if self.return_qty > self.pending_qty:
            self.return_qty = self.pending_qty
            return {
                'warning': {
                    'title': _('Cantidad ajustada'),
                    'message': _(f'La cantidad se ajustó al máximo pendiente: {self.pending_qty}')
                }
            }