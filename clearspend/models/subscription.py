# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError

class ClearspendSubscription(models.Model):
    _name = 'clearspend.subscription'
    _description = 'Abonnement SaaS'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nom', required=True, tracking=True)
    provider_id = fields.Many2one('clearspend.saas.provider', string='Fournisseur', tracking=True)
    
    # Prix et quantité
    unit_price = fields.Float(string='Prix unitaire', tracking=True)
    quantity = fields.Integer(string='Nb abonnements', default=1)
    currency_id = fields.Many2one('res.currency', string='Devise', 
                                   default=lambda self: self.env.ref('base.EUR', raise_if_not_found=False))
    amount = fields.Float(string='Montant total', compute='_compute_amount', store=True)
    
    # Montant converti en EUR pour les calculs
    amount_eur = fields.Float(string='Montant (EUR)', compute='_compute_amount_eur', store=True)
    
    # Cycle et dates
    billing_cycle = fields.Selection([
        ('monthly', 'Mensuel'),
        ('quarterly', 'Trimestriel'),
        ('yearly', 'Annuel'),
    ], string='Cycle', default='monthly', tracking=True)
    start_date = fields.Date(string='Date de début')
    renewal_date = fields.Date(string='Date de renouvellement', tracking=True)
    
    # Catégorie et responsable
    category = fields.Selection([
        ('essential', 'Essentiel'),
        ('important', 'Important'),
        ('optional', 'Optionnel'),
        ('to_review', 'À revoir'),
    ], string='Priorité', default='important')
    responsible_id = fields.Many2one('res.users', string='Responsable', 
                                      default=lambda self: self.env.user, tracking=True)
    department = fields.Char(string='Département (texte)')
    
    # Département lié
    department_id = fields.Many2one('clearspend.department', string='Département', tracking=True)
    
    # ==========================================
    # WORKFLOW D'APPROBATION
    # ==========================================
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('submitted', 'Soumis'),
        ('manager_approved', 'Approuvé Manager'),
        ('approved', 'Approuvé CFO'),
        ('active', 'Actif'),
        ('rejected', 'Rejeté'),
        ('cancelled', 'Résilié'),
    ], string='Statut', default='draft', tracking=True)
    
    # Informations d'approbation
    submitted_by_id = fields.Many2one('res.users', string='Soumis par', readonly=True)
    submitted_date = fields.Datetime(string='Date soumission', readonly=True)
    
    manager_approved_by_id = fields.Many2one('res.users', string='Approuvé par (Manager)', readonly=True)
    manager_approval_date = fields.Datetime(string='Date approbation Manager', readonly=True)
    
    cfo_approved_by_id = fields.Many2one('res.users', string='Approuvé par (CFO)', readonly=True)
    cfo_approval_date = fields.Datetime(string='Date approbation CFO', readonly=True)
    
    rejected_by_id = fields.Many2one('res.users', string='Rejeté par', readonly=True)
    rejection_date = fields.Datetime(string='Date rejet', readonly=True)
    rejection_reason = fields.Text(string='Motif du rejet')
    
    # Montant annuel pour déterminer si approbation CFO requise
    annual_amount = fields.Float(string='Montant annuel', compute='_compute_annual_amount', store=True)
    requires_cfo_approval = fields.Boolean(string='Approbation CFO requise', compute='_compute_requires_cfo', store=True)
    
    # Seuil d'approbation CFO (configurable)
    cfo_approval_threshold = fields.Float(string='Seuil CFO', default=1000.0,
                                           help="Montant annuel au-delà duquel l'approbation CFO est requise")
    
    notes = fields.Text(string='Notes')
    
    # Favoris
    is_favorite = fields.Boolean(string='Favori', default=False)
    
    # Contrats liés
    contract_ids = fields.One2many('clearspend.contract', 'subscription_id', string='Contrats')
    contract_count = fields.Integer(string='Nb contrats', compute='_compute_contract_count')
    
    # Factures liées
    invoice_ids = fields.One2many('clearspend.invoice', 'subscription_id', string='Factures')
    invoice_count = fields.Integer(string='Nb factures', compute='_compute_invoice_count')
    
    # Références factures (simple texte, pas de dépendance comptabilité)
    invoice_refs = fields.Text(string='Références factures',
                                help="Notez ici les numéros de factures liées à cet abonnement")
    
    # Mode simple/avancé (computed depuis config)
    workflow_enabled = fields.Boolean(string='Workflow activé', compute='_compute_workflow_enabled')

    @api.depends_context('uid')
    def _compute_workflow_enabled(self):
        """Vérifie si le workflow est activé dans la config."""
        Config = self.env['clearspend.config']
        config = Config.get_config()
        enabled = config.mode == 'advanced' and config.enable_workflow
        for record in self:
            record.workflow_enabled = enabled

    @api.depends('unit_price', 'quantity')
    def _compute_amount(self):
        for record in self:
            record.amount = record.unit_price * record.quantity

    @api.depends('amount', 'currency_id')
    def _compute_amount_eur(self):
        """Convertit le montant en EUR pour les calculs."""
        eur = self.env.ref('base.EUR', raise_if_not_found=False)
        for record in self:
            if record.currency_id and eur and record.currency_id != eur:
                record.amount_eur = record.currency_id._convert(
                    record.amount, eur, 
                    self.env.company, 
                    fields.Date.today()
                )
            else:
                record.amount_eur = record.amount

    @api.depends('amount_eur', 'billing_cycle')
    def _compute_annual_amount(self):
        """Calcule le montant annuel pour déterminer le niveau d'approbation."""
        for record in self:
            if record.billing_cycle == 'monthly':
                record.annual_amount = record.amount_eur * 12
            elif record.billing_cycle == 'quarterly':
                record.annual_amount = record.amount_eur * 4
            else:
                record.annual_amount = record.amount_eur

    @api.depends('annual_amount')
    def _compute_requires_cfo(self):
        """Détermine si l'approbation CFO est requise selon le montant."""
        Config = self.env['clearspend.config']
        config = Config.get_config()
        threshold = config.cfo_approval_threshold if hasattr(config, 'cfo_approval_threshold') else 1000.0
        for record in self:
            record.requires_cfo_approval = record.annual_amount >= threshold

    @api.depends('contract_ids')
    def _compute_contract_count(self):
        for record in self:
            record.contract_count = len(record.contract_ids)

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    # ==========================================
    # ACTIONS DU WORKFLOW
    # ==========================================
    
    def _is_simple_mode(self):
        """Vérifie si on est en mode simple."""
        Config = self.env['clearspend.config']
        return Config.is_simple_mode()
    
    def _is_workflow_enabled(self):
        """Vérifie si le workflow est activé."""
        Config = self.env['clearspend.config']
        return Config.is_feature_enabled('workflow')
    
    def _check_manager_rights(self):
        """Vérifie si l'utilisateur est manager du département ou CFO."""
        self.ensure_one()
        user = self.env.user
        is_cfo = user.has_group('clearspend.group_cfo')
        is_manager = user.has_group('clearspend.group_manager')
        is_dept_manager = self.department_id and self.department_id.manager_id == user
        
        if not (is_cfo or (is_manager and is_dept_manager)):
            raise AccessError("Seul le manager du département ou le CFO peut approuver cette demande.")
        return True

    def _check_cfo_rights(self):
        """Vérifie si l'utilisateur est CFO."""
        self.ensure_one()
        if not self.env.user.has_group('clearspend.group_cfo'):
            raise AccessError("Seul le CFO peut approuver cette demande.")
        return True

    def action_submit(self):
        """Soumet l'abonnement pour approbation ou l'active directement en mode simple."""
        for record in self:
            if record.state != 'draft':
                raise UserError("Seuls les brouillons peuvent être soumis.")
            
            # Mode simple ou workflow désactivé → activation directe
            if record._is_simple_mode() or not record._is_workflow_enabled():
                record.write({
                    'state': 'active',
                    'submitted_by_id': self.env.user.id,
                    'submitted_date': fields.Datetime.now(),
                })
                return self._notification('✅ Abonnement activé', 'L\'abonnement est maintenant actif.', 'success')
            
            # Mode avancé avec workflow → soumission pour approbation
            if not record.department_id:
                raise UserError("Veuillez sélectionner un département avant de soumettre.")
            
            record.write({
                'state': 'submitted',
                'submitted_by_id': self.env.user.id,
                'submitted_date': fields.Datetime.now(),
            })
            
            # Notification au manager
            if record.department_id.manager_id:
                record.message_post(
                    body=f"📤 Demande soumise par {self.env.user.name} pour approbation.",
                    partner_ids=[record.department_id.manager_id.partner_id.id],
                    subtype_xmlid='mail.mt_comment',
                )
        
        return self._notification('📤 Demande soumise', 'En attente d\'approbation manager.', 'info')

    def action_simple_activate(self):
        """Active directement l'abonnement (mode simple uniquement)."""
        for record in self:
            if record.state != 'draft':
                raise UserError("Seuls les brouillons peuvent être activés.")
            record.write({'state': 'active'})
        return self._notification('✅ Abonnement activé', 'L\'abonnement est maintenant actif.', 'success')

    def action_manager_approve(self):
        """Le manager approuve l'abonnement."""
        for record in self:
            if record.state != 'submitted':
                raise UserError("Cette demande n'est pas en attente d'approbation manager.")
            
            record._check_manager_rights()
            
            # Si montant élevé, passage par CFO
            if record.requires_cfo_approval:
                record.write({
                    'state': 'manager_approved',
                    'manager_approved_by_id': self.env.user.id,
                    'manager_approval_date': fields.Datetime.now(),
                })
                record.message_post(
                    body=f"✅ Approuvé par {self.env.user.name} (Manager). En attente approbation CFO (montant > seuil).",
                    subtype_xmlid='mail.mt_comment',
                )
                return self._notification('✅ Approuvé Manager', 'En attente approbation CFO.', 'success')
            else:
                # Approbation directe sans CFO
                record.write({
                    'state': 'active',
                    'manager_approved_by_id': self.env.user.id,
                    'manager_approval_date': fields.Datetime.now(),
                })
                record.message_post(
                    body=f"✅ Approuvé et activé par {self.env.user.name} (Manager).",
                    subtype_xmlid='mail.mt_comment',
                )
                return self._notification('✅ Approuvé & Activé', 'L\'abonnement est maintenant actif.', 'success')

    def action_cfo_approve(self):
        """Le CFO approuve l'abonnement."""
        for record in self:
            if record.state not in ['submitted', 'manager_approved']:
                raise UserError("Cette demande n'est pas en attente d'approbation CFO.")
            
            record._check_cfo_rights()
            
            record.write({
                'state': 'active',
                'cfo_approved_by_id': self.env.user.id,
                'cfo_approval_date': fields.Datetime.now(),
            })
            record.message_post(
                body=f"✅ Approuvé et activé par {self.env.user.name} (CFO).",
                subtype_xmlid='mail.mt_comment',
            )
        
        return self._notification('✅ Approuvé CFO', 'L\'abonnement est maintenant actif.', 'success')

    def action_reject(self):
        """Rejette la demande d'abonnement."""
        for record in self:
            if record.state not in ['submitted', 'manager_approved']:
                raise UserError("Cette demande ne peut pas être rejetée.")
            
            # Manager peut rejeter son département, CFO peut tout rejeter
            if record.state == 'manager_approved':
                record._check_cfo_rights()
            else:
                record._check_manager_rights()
            
            record.write({
                'state': 'rejected',
                'rejected_by_id': self.env.user.id,
                'rejection_date': fields.Datetime.now(),
            })
            record.message_post(
                body=f"❌ Rejeté par {self.env.user.name}.\nMotif : {record.rejection_reason or 'Non spécifié'}",
                partner_ids=[record.submitted_by_id.partner_id.id] if record.submitted_by_id else [],
                subtype_xmlid='mail.mt_comment',
            )
        
        return self._notification('❌ Demande rejetée', 'Le demandeur a été notifié.', 'warning')

    def action_cancel(self):
        """Résilier l'abonnement."""
        for record in self:
            if record.state not in ['active', 'approved']:
                raise UserError("Seuls les abonnements actifs peuvent être résiliés.")
            record.write({'state': 'cancelled'})
            record.message_post(body=f"🚫 Résilié par {self.env.user.name}.")
        
        return self._notification('🚫 Abonnement résilié', 'L\'abonnement a été désactivé.', 'warning')

    def action_draft(self):
        """Remettre en brouillon (pour corrections après rejet)."""
        for record in self:
            if record.state not in ['rejected', 'draft']:
                raise UserError("Seuls les abonnements rejetés peuvent être remis en brouillon.")
            record.write({
                'state': 'draft',
                'rejection_reason': False,
                'rejected_by_id': False,
                'rejection_date': False,
            })
        
        return self._notification('↩ Retour brouillon', 'Vous pouvez modifier et resoumettre.', 'info')

    def action_reactivate(self):
        """Réactiver un abonnement résilié."""
        for record in self:
            if record.state != 'cancelled':
                raise UserError("Seuls les abonnements résiliés peuvent être réactivés.")
            record._check_manager_rights()
            record.write({'state': 'active'})
            record.message_post(body=f"♻️ Réactivé par {self.env.user.name}.")
        
        return self._notification('♻️ Réactivé', 'L\'abonnement est de nouveau actif.', 'success')

    def _notification(self, title, message, notif_type='info'):
        """Helper pour retourner une notification."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notif_type,
                'sticky': False,
            }
        }

    # ==========================================
    # ANCIENNES ACTIONS (compatibilité)
    # ==========================================
    
    def action_validate(self):
        """Alias pour action_submit (compatibilité)."""
        return self.action_submit()

    def action_activate(self):
        """Alias pour activation directe (CFO uniquement)."""
        self._check_cfo_rights()
        self.write({'state': 'active'})
        return self._notification('▶ Activé', 'Abonnement activé directement.', 'success')

    def action_toggle_favorite(self):
        """Basculer le statut favori."""
        for record in self:
            record.is_favorite = not record.is_favorite
            status = "ajouté aux" if record.is_favorite else "retiré des"
            return self._notification('⭐ Favoris', f'{record.name} {status} favoris.', 'info')

    def action_save(self):
        """Sauvegarde explicite avec notification."""
        return self._notification('💾 Enregistré', 'Les modifications ont été sauvegardées.', 'success')

    def action_view_contracts(self):
        """Ouvre les contrats liés."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Contrats',
            'res_model': 'clearspend.contract',
            'view_mode': 'list,form',
            'domain': [('subscription_id', '=', self.id)],
            'context': {'default_subscription_id': self.id},
        }

    def action_create_contract(self):
        """Crée un nouveau contrat."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nouveau contrat',
            'res_model': 'clearspend.contract',
            'view_mode': 'form',
            'context': {
                'default_subscription_id': self.id,
                'default_name': f"Contrat {self.name}",
                'default_contract_value': self.annual_amount,
            },
            'target': 'current',
        }

    def action_view_invoices(self):
        """Ouvre les factures liées."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Factures',
            'res_model': 'clearspend.invoice',
            'view_mode': 'list,kanban,form',
            'domain': [('subscription_id', '=', self.id)],
            'context': {'default_subscription_id': self.id},
        }

    def action_export_excel(self):
        """Exporte les abonnements sélectionnés en Excel."""
        import base64
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
        except ImportError:
            raise UserError("Le module openpyxl n'est pas installé.")
        
        from io import BytesIO
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Abonnements"
        
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        
        headers = ['Nom', 'Fournisseur', 'Prix unitaire', 'Quantité', 'Montant total', 'Montant annuel',
                   'Cycle', 'Priorité', 'Responsable', 'Département', 'Date renouvellement', 'Statut', 
                   'Soumis par', 'Approuvé Manager', 'Approuvé CFO', 'Notes']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')
        
        cycle_labels = {'monthly': 'Mensuel', 'quarterly': 'Trimestriel', 'yearly': 'Annuel'}
        category_labels = {'essential': 'Essentiel', 'important': 'Important', 'optional': 'Optionnel', 'to_review': 'À revoir'}
        state_labels = {'draft': 'Brouillon', 'submitted': 'Soumis', 'manager_approved': 'Approuvé Manager',
                        'approved': 'Approuvé CFO', 'active': 'Actif', 'rejected': 'Rejeté', 'cancelled': 'Résilié'}
        
        for row, sub in enumerate(self, 2):
            ws.cell(row=row, column=1, value=sub.name)
            ws.cell(row=row, column=2, value=sub.provider_id.name if sub.provider_id else '')
            ws.cell(row=row, column=3, value=sub.unit_price)
            ws.cell(row=row, column=4, value=sub.quantity)
            ws.cell(row=row, column=5, value=sub.amount)
            ws.cell(row=row, column=6, value=sub.annual_amount)
            ws.cell(row=row, column=7, value=cycle_labels.get(sub.billing_cycle, ''))
            ws.cell(row=row, column=8, value=category_labels.get(sub.category, ''))
            ws.cell(row=row, column=9, value=sub.responsible_id.name if sub.responsible_id else '')
            ws.cell(row=row, column=10, value=sub.department_id.name if sub.department_id else sub.department or '')
            ws.cell(row=row, column=11, value=str(sub.renewal_date) if sub.renewal_date else '')
            ws.cell(row=row, column=12, value=state_labels.get(sub.state, ''))
            ws.cell(row=row, column=13, value=sub.submitted_by_id.name if sub.submitted_by_id else '')
            ws.cell(row=row, column=14, value=sub.manager_approved_by_id.name if sub.manager_approved_by_id else '')
            ws.cell(row=row, column=15, value=sub.cfo_approved_by_id.name if sub.cfo_approved_by_id else '')
            ws.cell(row=row, column=16, value=sub.notes or '')
        
        for col in range(1, 17):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 15
        
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        attachment = self.env['ir.attachment'].create({
            'name': 'export_abonnements.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
