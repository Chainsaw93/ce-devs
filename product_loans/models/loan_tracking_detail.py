# models/loan_tracking_detail.py - ACTUALIZADO

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class LoanTrackingDetail(models.Model):
    _name = 'loan.tracking.detail'
    _description = 'Seguimiento Detallado de Préstamos'
    _order = 'loan_date desc, id desc'
    _rec_name = 'display_name'

    # Referencias principales
    picking_id = fields.Many2one(
        'stock.picking',
        string='Préstamo',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        index=True
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Número de Serie/Lote',
        help="Solo para productos con rastreo por serie o lote",
        index=True
    )
    
    # Información del préstamo
    quantity = fields.Float(
        string='Cantidad',
        required=True,
        digits='Product Unit of Measure',
        help="Cantidad prestada (siempre 1 para productos con número de serie)"
    )
    
    status = fields.Selection([
        ('active', 'Préstamo Activo'),
        ('sold', 'Convertido a Venta'),
        ('returned_good', 'Devuelto en Buen Estado'),
        ('returned_damaged', 'Devuelto Dañado'),
        ('returned_defective', 'Devuelto Defectuoso'),
        ('pending_resolution', 'Pendiente de Resolución')
    ], string='Estado', required=True, default='active', index=True)
    
    # Fechas importantes
    loan_date = fields.Datetime(
        string='Fecha de Préstamo',
        required=True,
        default=fields.Datetime.now,
        index=True
    )
    
    resolution_date = fields.Datetime(
        string='Fecha de Resolución',
        help="Fecha cuando se resolvió el préstamo (venta o devolución)"
    )
    
    expected_return_date = fields.Date(
        related='picking_id.loan_expected_return_date',
        string='Fecha Esperada de Devolución',
        store=True,
        readonly=True
    )
    
    # CAMBIO: Información del cliente usando el nuevo campo
    partner_id = fields.Many2one(
        'res.partner',
        related='picking_id.loaned_to_partner_id',  # CAMBIO AQUÍ
        string='Cliente',
        store=True,
        readonly=True,
        index=True
    )
    
    # Información financiera
    original_cost = fields.Float(
        string='Costo Original',
        help="Costo del producto al momento del préstamo",
        digits='Product Price'
    )
    
    sale_price = fields.Float(
        string='Precio de Venta',
        help="Precio al cual se vendió (si aplica)",
        digits='Product Price'
    )
    
    # Referencias a transacciones relacionadas
    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        string='Línea de Venta',
        help="Línea de orden de venta si se convirtió a venta"
    )
    
    return_picking_id = fields.Many2one(
        'stock.picking',
        string='Devolución',
        help="Transferencia de devolución si se devolvió"
    )
    
    # Campos calculados
    days_in_loan = fields.Integer(
        string='Días en Préstamo',
        compute='_compute_days_in_loan',
        store=True,
        help="Número de días que el producto ha estado/estuvo prestado"
    )
    
    is_overdue = fields.Boolean(
        string='Vencido',
        compute='_compute_overdue_status',
        store=True
    )
    
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True
    )
    
    # Notas y observaciones
    notes = fields.Text(
        string='Notas',
        help="Observaciones adicionales sobre este préstamo específico"
    )
    
    return_condition_notes = fields.Text(
        string='Notas de Condición',
        help="Notas sobre el estado del producto al momento de la devolución"
    )

    @api.depends('product_id', 'lot_id', 'quantity', 'partner_id')
    def _compute_display_name(self):
        """Generar nombre descriptivo para el registro"""
        for record in self:
            parts = [record.product_id.name or 'Producto']
            
            if record.lot_id:
                parts.append(f"S/N: {record.lot_id.name}")
            elif record.quantity != 1:
                parts.append(f"Qty: {record.quantity}")
                
            if record.partner_id:
                parts.append(f"→ {record.partner_id.name}")
                
            record.display_name = ' '.join(parts)

    @api.depends('loan_date', 'resolution_date', 'status')
    def _compute_days_in_loan(self):
        """Calcular días en préstamo"""
        for record in self:
            if record.status == 'active':
                # Préstamo activo - calcular desde fecha de préstamo hasta hoy
                end_date = fields.Datetime.now()
            else:
                # Préstamo resuelto - calcular hasta fecha de resolución
                end_date = record.resolution_date or record.loan_date
                
            if record.loan_date:
                delta = end_date - record.loan_date
                record.days_in_loan = delta.days
            else:
                record.days_in_loan = 0

    @api.depends('expected_return_date', 'status')
    def _compute_overdue_status(self):
        """Determinar si el préstamo está vencido"""
        today = fields.Date.today()
        for record in self:
            if (record.status == 'active' and 
                record.expected_return_date and 
                record.expected_return_date < today):
                record.is_overdue = True
            else:
                record.is_overdue = False

    @api.constrains('quantity', 'product_id', 'lot_id')
    def _check_tracking_consistency(self):
        """Validar consistencia entre tipo de rastreo y datos"""
        for record in self:
            if record.product_id.tracking == 'serial':
                # Productos con serie deben tener lot_id y cantidad = 1
                if not record.lot_id:
                    raise ValidationError(_(
                        f"El producto {record.product_id.name} requiere número de serie."
                    ))
                if record.quantity != 1:
                    raise ValidationError(_(
                        f"Los productos con número de serie deben tener cantidad = 1. "
                        f"Producto: {record.product_id.name}"
                    ))
            elif record.product_id.tracking == 'lot':
                # Productos con lote deben tener lot_id
                if not record.lot_id:
                    raise ValidationError(_(
                        f"El producto {record.product_id.name} requiere número de lote."
                    ))
            else:
                # Productos sin rastreo no deben tener lot_id
                if record.lot_id:
                    raise ValidationError(_(
                        f"El producto {record.product_id.name} no usa rastreo por serie/lote."
                    ))

    @api.constrains('status', 'resolution_date', 'sale_order_line_id', 'return_picking_id')
    def _check_resolution_consistency(self):
        """Validar consistencia en la resolución del préstamo"""
        for record in self:
            if record.status == 'sold':
                if not record.sale_order_line_id:
                    raise ValidationError(_(
                        "Los préstamos vendidos deben tener una línea de orden de venta asociada."
                    ))
                    
            if record.status in ('returned_good', 'returned_damaged', 'returned_defective'):
                if not record.return_picking_id:
                    raise ValidationError(_(
                        "Los préstamos devueltos deben tener una transferencia de devolución asociada."
                    ))
                    
            if record.status != 'active' and not record.resolution_date:
                record.resolution_date = fields.Datetime.now()

    def action_mark_as_sold(self, sale_order_line, sale_price=None):
        """Marcar el préstamo como vendido"""
        self.ensure_one()
        
        if self.status != 'active':
            raise UserError(_(
                "Solo los préstamos activos pueden marcarse como vendidos."
            ))
        
        self.write({
            'status': 'sold',
            'sale_order_line_id': sale_order_line.id,
            'sale_price': sale_price or sale_order_line.price_unit,
            'resolution_date': fields.Datetime.now()
        })

    def action_mark_as_returned(self, return_picking, condition='good', notes=None):
        """Marcar el préstamo como devuelto"""
        self.ensure_one()
        
        if self.status not in ('active', 'pending_resolution'):
            raise UserError(_(
                "Solo los préstamos activos pueden marcarse como devueltos."
            ))
        
        status_mapping = {
            'good': 'returned_good',
            'damaged': 'returned_damaged',
            'defective': 'returned_defective'
        }
        
        self.write({
            'status': status_mapping.get(condition, 'returned_good'),
            'return_picking_id': return_picking.id,
            'resolution_date': fields.Datetime.now(),
            'return_condition_notes': notes or ''
        })

    def action_view_related_documents(self):
        """Ver documentos relacionados (orden de venta o devolución)"""
        self.ensure_one()
        
        if self.sale_order_line_id:
            return {
                'name': 'Orden de Venta',
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': self.sale_order_line_id.order_id.id,
                'view_mode': 'form',
                'target': 'current'
            }
        elif self.return_picking_id:
            return {
                'name': 'Devolución',
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'res_id': self.return_picking_id.id,
                'view_mode': 'form',
                'target': 'current'
            }
        else:
            return {
                'name': 'Préstamo Original',
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'res_id': self.picking_id.id,
                'view_mode': 'form',
                'target': 'current'
            }

    @api.model
    def get_loan_analytics(self, date_from=None, date_to=None, partner_ids=None):
        """Obtener analíticas de préstamos para dashboards"""
        domain = []
        
        if date_from:
            domain.append(('loan_date', '>=', date_from))
        if date_to:
            domain.append(('loan_date', '<=', date_to))
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids))
        
        records = self.search(domain)
        
        analytics = {
            'total_loans': len(records),
            'active_loans': len(records.filtered(lambda r: r.status == 'active')),
            'overdue_loans': len(records.filtered('is_overdue')),
            'sold_conversions': len(records.filtered(lambda r: r.status == 'sold')),
            'returns_good': len(records.filtered(lambda r: r.status == 'returned_good')),
            'returns_damaged': len(records.filtered(lambda r: r.status in ('returned_damaged', 'returned_defective'))),
            'avg_days_in_loan': sum(records.mapped('days_in_loan')) / len(records) if records else 0,
            'conversion_rate': len(records.filtered(lambda r: r.status == 'sold')) / len(records) * 100 if records else 0,
        }
        
        return analytics

    @api.model
    def _cron_cleanup_old_resolved_records(self):
        """Cron job para limpiar registros antiguos resueltos (opcional)"""
        # Buscar registros resueltos hace más de 2 años
        cutoff_date = fields.Datetime.now() - timedelta(days=730)
        
        old_records = self.search([
            ('status', 'in', ['sold', 'returned_good', 'returned_damaged', 'returned_defective']),
            ('resolution_date', '<', cutoff_date)
        ])
        
        _logger.info(f"Limpieza automática: encontrados {len(old_records)} registros antiguos")
        
        # En lugar de eliminar, podríamos archivar o mover a tabla histórica
        # old_records.unlink()  # Descomenta si quieres eliminar automáticamente
        
        return len(old_records)


class LoanValuationTracker(models.Model):
    _name = 'loan.valuation.tracker'
    _description = 'Seguimiento de Valoración de Préstamos'
    _order = 'loan_date desc'

    # Referencias
    picking_id = fields.Many2one(
        'stock.picking',
        string='Préstamo',
        required=True,
        ondelete='cascade'
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Número de Serie/Lote'
    )
    
    # Información de valoración
    loan_date = fields.Datetime(
        string='Fecha de Préstamo',
        required=True
    )
    
    original_cost = fields.Float(
        string='Costo al Momento del Préstamo',
        digits='Product Price',
        required=True
    )
    
    current_cost = fields.Float(
        string='Costo Actual del Producto',
        digits='Product Price',
        compute='_compute_current_cost',
        store=True
    )
    
    valuation_difference = fields.Float(
        string='Diferencia de Valoración',
        digits='Product Price',
        compute='_compute_valuation_difference',
        store=True,
        help="Diferencia entre costo actual y costo original"
    )
    
    # Estado
    is_resolved = fields.Boolean(
        string='Resuelto',
        default=False,
        help="Indica si este préstamo ya fue resuelto (vendido o devuelto)"
    )
    
    resolution_type = fields.Selection([
        ('sold', 'Vendido'),
        ('returned', 'Devuelto')
    ], string='Tipo de Resolución')
    
    final_cost = fields.Float(
        string='Costo Final Utilizado',
        digits='Product Price',
        help="Costo utilizado para valoración en la transacción final"
    )

    @api.depends('product_id')
    def _compute_current_cost(self):
        """Obtener costo actual del producto"""
        for record in self:
            if record.product_id:
                record.current_cost = record.product_id.standard_price
            else:
                record.current_cost = 0.0

    @api.depends('original_cost', 'current_cost')
    def _compute_valuation_difference(self):
        """Calcular diferencia de valoración"""
        for record in self:
            record.valuation_difference = record.current_cost - record.original_cost

    def mark_as_resolved(self, resolution_type, final_cost=None):
        """Marcar como resuelto con tipo específico"""
        self.write({
            'is_resolved': True,
            'resolution_type': resolution_type,
            'final_cost': final_cost or self.original_cost
        })

    @api.model
    def create_for_loan(self, picking):
        """Crear registros de valoración para un préstamo nuevo"""
        valuation_records = []
        
        for move in picking.move_ids_without_package:
            if move.product_id.tracking == 'serial':
                # Un registro por cada número de serie
                for move_line in move.move_line_ids:
                    if move_line.lot_id:
                        valuation_records.append({
                            'picking_id': picking.id,
                            'product_id': move.product_id.id,
                            'lot_id': move_line.lot_id.id,
                            'loan_date': picking.date_done or fields.Datetime.now(),
                            'original_cost': move.product_id.standard_price,
                        })
            else:
                # Un registro por producto
                valuation_records.append({
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'loan_date': picking.date_done or fields.Datetime.now(),
                    'original_cost': move.product_id.standard_price,
                })
        
        return self.create(valuation_records)

    @api.model
    def get_valuation_impact_report(self):
        """Generar reporte de impacto de valoración"""
        unresolved_records = self.search([('is_resolved', '=', False)])
        
        total_original = sum(unresolved_records.mapped('original_cost'))
        total_current = sum(unresolved_records.mapped('current_cost'))
        total_difference = total_current - total_original
        
        return {
            'unresolved_loans_count': len(unresolved_records),
            'total_original_value': total_original,
            'total_current_value': total_current,
            'total_valuation_impact': total_difference,
            'avg_valuation_difference': total_difference / len(unresolved_records) if unresolved_records else 0,
            'significant_differences': unresolved_records.filtered(
                lambda r: abs(r.valuation_difference) > r.original_cost * 0.1
            )
        }