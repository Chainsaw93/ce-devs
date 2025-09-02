# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta


class LoanTrialConfigWizard(models.TransientModel):
    _name = 'loan.trial.config.wizard'
    _description = 'Configuración de Período de Prueba'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Préstamo',
        required=True,
        readonly=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        related='picking_id.loaned_to_partner_id',
        string='Cliente',
        readonly=True
    )
    
    trial_end_date = fields.Date(
        string='Fecha Fin del Período de Prueba',
        required=True,
        default=lambda self: fields.Date.today() + timedelta(days=7)
    )
    
    trial_duration_days = fields.Integer(
        string='Duración (días)',
        compute='_compute_trial_duration',
        inverse='_inverse_trial_duration',
        help="Duración del período de prueba en días"
    )
    
    automatic_reminder = fields.Boolean(
        string='Recordatorio Automático',
        default=True,
        help="Crear recordatorio automático 1 día antes del vencimiento"
    )
    
    reminder_user_id = fields.Many2one(
        'res.users',
        string='Usuario para Recordatorio',
        default=lambda self: self.env.user,
        help="Usuario que recibirá el recordatorio automático"
    )
    
    notes = fields.Text(
        string='Notas del Período de Prueba',
        help="Observaciones sobre el período de prueba"
    )

    @api.depends('trial_end_date')
    def _compute_trial_duration(self):
        """Calcular duración en días"""
        today = fields.Date.today()
        for wizard in self:
            if wizard.trial_end_date:
                delta = wizard.trial_end_date - today
                wizard.trial_duration_days = max(1, delta.days)
            else:
                wizard.trial_duration_days = 7

    def _inverse_trial_duration(self):
        """Calcular fecha fin basada en duración"""
        today = fields.Date.today()
        for wizard in self:
            if wizard.trial_duration_days > 0:
                wizard.trial_end_date = today + timedelta(days=wizard.trial_duration_days)

    @api.constrains('trial_end_date')
    def _check_trial_date(self):
        """Validar que la fecha de fin sea futura"""
        today = fields.Date.today()
        for wizard in self:
            if wizard.trial_end_date <= today:
                raise ValidationError(_(
                    "La fecha de fin del período de prueba debe ser posterior a hoy."
                ))

    def action_configure_trial(self):
        """Configurar el período de prueba"""
        self.ensure_one()
        
        # Actualizar el préstamo
        self.picking_id.write({
            'loan_state': 'in_trial',
            'trial_end_date': self.trial_end_date,
            'loan_expected_return_date': self.trial_end_date,
            'loan_notes': (self.picking_id.loan_notes or '') + f"\n\nPeríodo de prueba iniciado: {fields.Date.today()} - {self.trial_end_date}. {self.notes or ''}"
        })
        
        # Crear recordatorio automático si está habilitado
        if self.automatic_reminder:
            self._create_reminder_activity()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Período de Prueba Configurado',
                'message': f'El período de prueba ha sido configurado hasta el {self.trial_end_date}',
                'type': 'success',
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'stock.picking',
                    'res_id': self.picking_id.id,
                    'view_mode': 'form',
                    'target': 'current'
                }
            }
        }

    def _create_reminder_activity(self):
        """Crear actividad de recordatorio automático"""
        reminder_date = self.trial_end_date - timedelta(days=1)
        
        if reminder_date <= fields.Date.today():
            reminder_date = fields.Date.today()
        
        activity_type = self.env.ref('mail.mail_activity_data_todo', False)
        if not activity_type:
            activity_type = self.env['mail.activity.type'].search([], limit=1)
        
        self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'summary': f'Período de Prueba Finaliza - {self.picking_id.name}',
            'note': f'''
                <p><strong>El período de prueba finaliza mañana</strong></p>
                <p>Cliente: {self.partner_id.name}</p>
                <p>Fecha de vencimiento: {self.trial_end_date}</p>
                <p>Acciones recomendadas:</p>
                <ul>
                    <li>Contactar al cliente para conocer su decisión</li>
                    <li>Usar "Resolver Préstamo" para procesar compras/devoluciones</li>
                    <li>Extender período si es necesario</li>
                </ul>
                <p>Notas: {self.notes or 'N/A'}</p>
            ''',
            'date_deadline': reminder_date,
            'user_id': self.reminder_user_id.id,
        })


class LoanReturnWizardEnhanced(models.TransientModel):
    _name = 'loan.return.wizard.enhanced'
    _description = 'Asistente Mejorado para Devolución de Préstamos'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Préstamo Original',
        required=True,
        readonly=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        related='picking_id.loaned_to_partner_id',
        string='Cliente',
        readonly=True
    )
    
    return_location_id = fields.Many2one(
        'stock.location',
        string='Ubicación de Devolución',
        required=True,
        domain=[('usage', 'in', ('internal', 'transit'))],
        help="Ubicación donde se almacenarán los productos devueltos"
    )
    
    return_date = fields.Datetime(
        string='Fecha de Devolución',
        default=fields.Datetime.now,
        required=True
    )
    
    inspection_required = fields.Boolean(
        string='Requiere Inspección',
        default=True,
        help="Los productos devueltos requieren inspección antes de regresar al stock general"
    )
    
    inspection_location_id = fields.Many2one(
        'stock.location',
        string='Ubicación de Inspección',
        help="Ubicación temporal para inspección (opcional)"
    )
    
    notes = fields.Text(
        string='Notas de Devolución',
        help="Observaciones generales sobre la devolución"
    )
    
    return_line_ids = fields.One2many(
        'loan.return.wizard.enhanced.line',
        'wizard_id',
        string='Productos a Devolver'
    )

    @api.model
    def default_get(self, fields_list):
        """Poblar automáticamente las líneas desde detalles de seguimiento activos"""
        res = super().default_get(fields_list)
        
        if 'picking_id' in self.env.context:
            picking_id = self.env.context['picking_id']
            picking = self.env['stock.picking'].browse(picking_id)
            
            if picking.exists() and picking.is_loan:
                # Buscar detalles de seguimiento activos
                active_details = self.env['loan.tracking.detail'].search([
                    ('picking_id', '=', picking_id),
                    ('status', '=', 'active')
                ])
                
                return_lines = []
                for detail in active_details:
                    return_lines.append((0, 0, {
                        'tracking_detail_id': detail.id,
                        'product_id': detail.product_id.id,
                        'lot_id': detail.lot_id.id if detail.lot_id else False,
                        'loaned_qty': detail.quantity,
                        'return_qty': detail.quantity,  # Por defecto devolver todo
                        'return_condition': 'good',
                    }))
                
                res['return_line_ids'] = return_lines
                
                # Configurar ubicación de devolución por defecto
                if 'return_location_id' in self.env.context:
                    res['return_location_id'] = self.env.context['return_location_id']
                else:
                    # Buscar almacén principal
                    main_warehouse = self.env['stock.warehouse'].search([
                        ('warehouse_type', '!=', 'loans')
                    ], limit=1)
                    if main_warehouse:
                        res['return_location_id'] = main_warehouse.lot_stock_id.id
        
        return res

    def action_process_return(self):
        """Procesar la devolución completa"""
        self.ensure_one()
        
        # Validaciones
        self._validate_return()
        
        try:
            # Crear picking de devolución
            return_picking = self._create_return_picking()
            
            # Actualizar detalles de seguimiento
            self._update_tracking_details(return_picking)
            
            # Actualizar estado del préstamo original
            self._update_loan_status()
            
            return self._return_success_action(return_picking)
            
        except Exception as e:
            raise UserError(_(f"Error al procesar la devolución: {str(e)}"))

    def _validate_return(self):
        """Validaciones antes de procesar"""
        if not self.return_line_ids:
            raise UserError(_("Debe especificar al menos un producto para devolver."))
        
        # Validar cantidades
        for line in self.return_line_ids:
            if line.return_qty <= 0:
                raise UserError(_(
                    f"La cantidad a devolver debe ser mayor a 0 para {line.product_id.name}"
                ))
            
            if line.return_qty > line.loaned_qty:
                raise UserError(_(
                    f"No se puede devolver más cantidad de la prestada para {line.product_id.name}. "
                    f"Prestado: {line.loaned_qty}, Intentando devolver: {line.return_qty}"
                ))

    def _create_return_picking(self):
        """Crear transferencia de devolución"""
        # Determinar ubicación final según si requiere inspección
        final_location = self.inspection_location_id if self.inspection_required else self.return_location_id
        
        picking_vals = {
            'partner_id': self.partner_id.id,
            'picking_type_id': self.picking_id.picking_type_id.id,
            'location_id': self.picking_id.location_dest_id.id,
            'location_dest_id': final_location.id,
            'origin': f"Devolución de {self.picking_id.name}",
            'scheduled_date': self.return_date,
            'note': self.notes or f"Devolución procesada automáticamente",
            'move_ids_without_package': []
        }
        
        # Crear movimientos
        moves = []
        for line in self.return_line_ids:
            if line.return_qty > 0:
                move_vals = {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.return_qty,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': self.picking_id.location_dest_id.id,
                    'location_dest_id': final_location.id,
                    'name': f"Devolución: {line.product_id.name}",
                    'origin': self.picking_id.name,
                }
                
                # Agregar información de número de serie si aplica
                if line.lot_id:
                    move_vals['lot_ids'] = [(4, line.lot_id.id)]
                
                moves.append((0, 0, move_vals))
        
        picking_vals['move_ids_without_package'] = moves
        return_picking = self.env['stock.picking'].create(picking_vals)
        
        # Confirmar automáticamente
        return_picking.action_confirm()
        
        return return_picking

    def _update_tracking_details(self, return_picking):
        """Actualizar detalles de seguimiento según devolución"""
        for line in self.return_line_ids:
            if line.return_qty > 0:
                # Mapear condición a estado
                condition_to_status = {
                    'good': 'returned_good',
                    'damaged': 'returned_damaged',
                    'defective': 'returned_defective'
                }
                
                # Actualizar el detalle de seguimiento
                line.tracking_detail_id.action_mark_as_returned(
                    return_picking,
                    line.return_condition,
                    line.condition_notes
                )

    def _update_loan_status(self):
        """Actualizar estado del préstamo original"""
        # Verificar si quedan productos activos
        remaining_active = self.env['loan.tracking.detail'].search_count([
            ('picking_id', '=', self.picking_id.id),
            ('status', '=', 'active')
        ])
        
        if remaining_active == 0:
            # Todos los productos fueron devueltos o resueltos
            self.picking_id.loan_state = 'completed'
        else:
            # Aún hay productos pendientes
            self.picking_id.loan_state = 'partially_resolved'

    def _return_success_action(self, return_picking):
        """Acción de retorno exitosa"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Devolución Procesada',
                'message': f'Devolución creada exitosamente: {return_picking.name}',
                'type': 'success',
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'stock.picking',
                    'res_id': return_picking.id,
                    'view_mode': 'form',
                    'target': 'current'
                }
            }
        }


class LoanReturnWizardEnhancedLine(models.TransientModel):
    _name = 'loan.return.wizard.enhanced.line'
    _description = 'Línea de Devolución Mejorada'

    wizard_id = fields.Many2one(
        'loan.return.wizard.enhanced',
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
    
    return_qty = fields.Float(
        string='Cantidad a Devolver',
        required=True,
        digits='Product Unit of Measure'
    )
    
    return_condition = fields.Selection([
        ('good', 'Buen Estado'),
        ('damaged', 'Dañado - Reparable'),
        ('defective', 'Defectuoso - No Reparable')
    ], string='Condición', required=True, default='good')
    
    condition_notes = fields.Text(
        string='Notas de Condición',
        help="Descripción detallada del estado del producto"
    )

    @api.constrains('return_qty', 'loaned_qty')
    def _check_return_quantity(self):
        """Validar cantidad de devolución"""
        for line in self:
            if line.return_qty < 0:
                raise ValidationError(_(
                    "La cantidad a devolver no puede ser negativa."
                ))
            
            if line.return_qty > line.loaned_qty:
                raise ValidationError(_(
                    f"La cantidad a devolver ({line.return_qty}) no puede ser mayor "
                    f"a la cantidad prestada ({line.loaned_qty}) para {line.product_id.name}."
                ))
            
            # Para productos con serie, solo cantidades enteras de 1
            if (line.product_id.tracking == 'serial' and 
                line.return_qty > 0 and 
                line.return_qty != 1):
                raise ValidationError(_(
                    f"Los productos con número de serie solo permiten devolver 1 unidad. "
                    f"Producto: {line.product_id.name}"
                ))


class LoanNotificationWizard(models.TransientModel):
    _name = 'loan.notification.wizard'
    _description = 'Asistente de Notificaciones de Préstamos'

    notification_type = fields.Selection([
        ('overdue', 'Préstamos Vencidos'),
        ('due_soon', 'Préstamos por Vencer'),
        ('trial_ending', 'Períodos de Prueba Finalizando')
    ], string='Tipo de Notificación', required=True)
    
    days_threshold = fields.Integer(
        string='Umbral de Días',
        default=3,
        help="Días de anticipación para notificaciones 'por vencer'"
    )
    
    partner_ids = fields.Many2many(
        'res.partner',
        string='Clientes Específicos',
        help="Dejar vacío para notificar a todos los clientes aplicables"
    )
    
    create_activities = fields.Boolean(
        string='Crear Actividades',
        default=True,
        help="Crear actividades para seguimiento interno"
    )
    
    send_emails = fields.Boolean(
        string='Enviar Emails',
        default=False,
        help="Enviar notificaciones por email a los clientes"
    )
    
    assigned_user_id = fields.Many2one(
        'res.users',
        string='Usuario Asignado',
        default=lambda self: self.env.user,
        help="Usuario que será asignado a las actividades creadas"
    )

    def action_send_notifications(self):
        """Enviar notificaciones según configuración"""
        self.ensure_one()
        
        # Obtener préstamos aplicables
        loans = self._get_applicable_loans()
        
        if not loans:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sin Préstamos Aplicables',
                    'message': 'No se encontraron préstamos que cumplan los criterios.',
                    'type': 'info'
                }
            }
        
        processed = 0
        
        # Crear actividades si está habilitado
        if self.create_activities:
            processed += self._create_notification_activities(loans)
        
        # Enviar emails si está habilitado
        if self.send_emails:
            processed += self._send_notification_emails(loans)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Notificaciones Procesadas',
                'message': f'Se procesaron {processed} notificaciones para {len(loans)} préstamos.',
                'type': 'success'
            }
        }

    def _get_applicable_loans(self):
        """Obtener préstamos aplicables según tipo de notificación"""
        domain = [
            ('is_loan', '=', True),
            ('loan_state', 'in', ['active', 'in_trial', 'partially_resolved'])
        ]
        
        # Filtrar por clientes específicos si se especificaron
        if self.partner_ids:
            domain.append(('loaned_to_partner_id', 'in', self.partner_ids.ids))
        
        loans = self.env['stock.picking'].search(domain)
        
        # Filtrar según tipo de notificación
        if self.notification_type == 'overdue':
            return loans.filtered('is_overdue')
        elif self.notification_type == 'due_soon':
            threshold_date = fields.Date.today() + timedelta(days=self.days_threshold)
            return loans.filtered(
                lambda l: l.loan_expected_return_date and 
                         l.loan_expected_return_date <= threshold_date and
                         not l.is_overdue
            )
        elif self.notification_type == 'trial_ending':
            threshold_date = fields.Date.today() + timedelta(days=self.days_threshold)
            return loans.filtered(
                lambda l: l.loan_state == 'in_trial' and
                         l.trial_end_date and
                         l.trial_end_date <= threshold_date
            )
        
        return loans

    def _create_notification_activities(self, loans):
        """Crear actividades de notificación"""
        activity_type = self.env.ref('mail.mail_activity_data_todo', False)
        if not activity_type:
            activity_type = self.env['mail.activity.type'].search([], limit=1)
        
        activities_created = 0
        
        for loan in loans:
            # Evitar duplicar actividades recientes
            existing = self.env['mail.activity'].search([
                ('res_model', '=', 'stock.picking'),
                ('res_id', '=', loan.id),
                ('activity_type_id', '=', activity_type.id),
                ('date_deadline', '>=', fields.Date.today() - timedelta(days=1))
            ], limit=1)
            
            if existing:
                continue  # Ya existe actividad reciente
            
            summary, note = self._get_activity_content(loan)
            
            self.env['mail.activity'].create({
                'activity_type_id': activity_type.id,
                'res_model': 'stock.picking',
                'res_id': loan.id,
                'summary': summary,
                'note': note,
                'date_deadline': fields.Date.today(),
                'user_id': self.assigned_user_id.id,
            })
            
            activities_created += 1
        
        return activities_created

    def _get_activity_content(self, loan):
        """Generar contenido de actividad según tipo"""
        if self.notification_type == 'overdue':
            summary = f'Préstamo Vencido - {loan.name}'
            note = f'''
                <p><strong>Préstamo vencido hace {loan.overdue_days} días</strong></p>
                <p>Cliente: {loan.loaned_to_partner_id.name}</p>
                <p>Fecha esperada: {loan.loan_expected_return_date}</p>
            '''
        elif self.notification_type == 'due_soon':
            days_until = (loan.loan_expected_return_date - fields.Date.today()).days
            summary = f'Préstamo Vence Pronto - {loan.name}'
            note = f'''
                <p><strong>Préstamo vence en {days_until} días</strong></p>
                <p>Cliente: {loan.loaned_to_partner_id.name}</p>
                <p>Fecha de vencimiento: {loan.loan_expected_return_date}</p>
            '''
        else:  # trial_ending
            days_until = (loan.trial_end_date - fields.Date.today()).days
            summary = f'Período de Prueba Finaliza - {loan.name}'
            note = f'''
                <p><strong>Período de prueba finaliza en {days_until} días</strong></p>
                <p>Cliente: {loan.loaned_to_partner_id.name}</p>
                <p>Fecha límite: {loan.trial_end_date}</p>
            '''
        
        return summary, note

    def _send_notification_emails(self, loans):
        """Enviar emails de notificación (implementación básica)"""
        # Esta es una implementación básica
        # En un entorno real, necesitarías templates de email personalizados
        emails_sent = 0
        
        for loan in loans:
            if not loan.loaned_to_partner_id.email:
                continue  # Skip si no hay email
            
            subject, body = self._get_email_content(loan)
            
            # Enviar email simple
            loan.message_post(
                subject=subject,
                body=body,
                partner_ids=[loan.loaned_to_partner_id.id],
                email_layout_xmlid='mail.mail_notification_light'
            )
            
            emails_sent += 1
        
        return emails_sent

    def _get_email_content(self, loan):
        """Generar contenido de email"""
        if self.notification_type == 'overdue':
            subject = f'Préstamo Vencido - {loan.name}'
            body = f'''
                Estimado/a {loan.loaned_to_partner_id.name},<br/><br/>
                Su préstamo {loan.name} está vencido hace {loan.overdue_days} días.
                Por favor contacte con nosotros para coordinar la devolución o resolución.<br/><br/>
                Fecha esperada de devolución: {loan.loan_expected_return_date}
            '''
        elif self.notification_type == 'due_soon':
            days_until = (loan.loan_expected_return_date - fields.Date.today()).days
            subject = f'Recordatorio - Préstamo Vence Pronto'
            body = f'''
                Estimado/a {loan.loaned_to_partner_id.name},<br/><br/>
                Su préstamo {loan.name} vence en {days_until} días.
                Fecha de vencimiento: {loan.loan_expected_return_date}<br/><br/>
                Por favor coordine la devolución o contacte con nosotros.
            '''
        else:  # trial_ending
            days_until = (loan.trial_end_date - fields.Date.today()).days
            subject = f'Período de Prueba Finaliza'
            body = f'''
                Estimado/a {loan.loaned_to_partner_id.name},<br/><br/>
                El período de prueba para su préstamo {loan.name} finaliza en {days_until} días.
                Fecha límite: {loan.trial_end_date}<br/><br/>
                Por favor infórmenos su decisión sobre los productos en préstamo.
            '''
        
        return subject, body