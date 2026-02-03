# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import date

class ClearspendInvoice(models.Model):
    _name = 'clearspend.invoice'
    _description = 'Facture SaaS'
    _order = 'invoice_date desc, create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Référence', required=True, tracking=True)
    
    # Fichier PDF
    invoice_file = fields.Binary(string='Fichier facture', attachment=True)
    invoice_filename = fields.Char(string='Nom du fichier')
    file_size = fields.Char(string='Taille', compute='_compute_file_size')
    
    # Lien avec facture Odoo (stocké comme ID pour éviter dépendance au module account)
    odoo_move_id = fields.Integer(string='ID Facture Odoo', index=True)
    odoo_move_name = fields.Char(string='Réf. Facture Odoo')
    is_from_odoo = fields.Boolean(string='Importée d\'Odoo', default=False)
    
    # Informations facture
    invoice_date = fields.Date(string='Date facture', default=fields.Date.today, tracking=True)
    due_date = fields.Date(string='Date échéance')
    
    # Montant
    amount = fields.Float(string='Montant TTC', tracking=True)
    amount_ht = fields.Float(string='Montant HT')
    currency_id = fields.Many2one('res.currency', string='Devise',
                                   default=lambda self: self.env.company.currency_id)
    
    # Fournisseur (texte libre ou lié)
    vendor_name = fields.Char(string='Fournisseur (texte)')
    provider_id = fields.Many2one('clearspend.saas.provider', string='Fournisseur SaaS',
                                   tracking=True)
    
    # Matching avec abonnement
    subscription_id = fields.Many2one('clearspend.subscription', string='Abonnement lié',
                                       tracking=True)
    subscription_ids = fields.Many2many('clearspend.subscription', string='Abonnements suggérés',
                                         compute='_compute_suggested_subscriptions')
    match_confidence = fields.Selection([
        ('high', '🟢 Haute'),
        ('medium', '🟡 Moyenne'),
        ('low', '🔴 Faible'),
        ('none', '⚪ Aucune'),
    ], string='Confiance matching', compute='_compute_match_confidence')
    
    # Statut
    state = fields.Selection([
        ('inbox', '📥 Inbox'),
        ('processing', '🔄 En traitement'),
        ('matched', '✅ Associée'),
        ('archived', '📦 Archivée'),
    ], string='Statut', default='inbox', tracking=True)
    
    # Période couverte
    period_start = fields.Date(string='Période du')
    period_end = fields.Date(string='Période au')
    
    # Notes
    notes = fields.Text(string='Notes')
    
    # Source de la facture
    source = fields.Selection([
        ('manual', 'Saisie manuelle'),
        ('upload', 'Upload fichier'),
        ('odoo', 'Odoo Comptabilité'),
        ('api', 'API fournisseur'),
        ('email', 'Email'),
    ], string='Source', default='manual')
    
    # Paiement
    is_paid = fields.Boolean(string='Payée', default=False, tracking=True)
    payment_date = fields.Date(string='Date paiement')
    payment_method = fields.Selection([
        ('card', 'Carte bancaire'),
        ('transfer', 'Virement'),
        ('direct_debit', 'Prélèvement'),
        ('other', 'Autre'),
    ], string='Moyen de paiement')

    @api.depends('invoice_file')
    def _compute_file_size(self):
        for record in self:
            if record.invoice_file:
                size_bytes = len(record.invoice_file) * 3 / 4
                if size_bytes > 1048576:
                    record.file_size = f"{size_bytes / 1048576:.1f} MB"
                elif size_bytes > 1024:
                    record.file_size = f"{size_bytes / 1024:.1f} KB"
                else:
                    record.file_size = f"{size_bytes:.0f} B"
            else:
                record.file_size = ''

    @api.depends('provider_id', 'amount', 'vendor_name')
    def _compute_suggested_subscriptions(self):
        """Suggère des abonnements correspondants."""
        Subscription = self.env['clearspend.subscription']
        
        for record in self:
            suggestions = Subscription.browse()
            
            # 1. Par fournisseur lié
            if record.provider_id:
                suggestions = Subscription.search([
                    ('provider_id', '=', record.provider_id.id),
                    ('state', 'in', ['active', 'validated']),
                ])
            
            # 2. Par nom de fournisseur (recherche floue)
            elif record.vendor_name:
                # Chercher le provider par nom
                provider = self.env['clearspend.saas.provider'].search([
                    ('name', 'ilike', record.vendor_name)
                ], limit=1)
                if provider:
                    suggestions = Subscription.search([
                        ('provider_id', '=', provider.id),
                        ('state', 'in', ['active', 'validated']),
                    ])
                else:
                    # Recherche dans le nom des abonnements
                    suggestions = Subscription.search([
                        '|',
                        ('name', 'ilike', record.vendor_name),
                        ('provider_id.name', 'ilike', record.vendor_name),
                        ('state', 'in', ['active', 'validated']),
                    ], limit=5)
            
            record.subscription_ids = suggestions

    @api.depends('subscription_id', 'subscription_ids', 'amount')
    def _compute_match_confidence(self):
        for record in self:
            if record.subscription_id:
                # Vérifie si le montant correspond
                sub = record.subscription_id
                expected = sub.amount
                if record.amount and expected:
                    diff_percent = abs(record.amount - expected) / expected * 100 if expected else 100
                    if diff_percent <= 5:
                        record.match_confidence = 'high'
                    elif diff_percent <= 20:
                        record.match_confidence = 'medium'
                    else:
                        record.match_confidence = 'low'
                else:
                    record.match_confidence = 'medium'
            elif record.subscription_ids:
                record.match_confidence = 'low'
            else:
                record.match_confidence = 'none'

    @api.onchange('provider_id')
    def _onchange_provider_id(self):
        """Remplit le nom du fournisseur."""
        if self.provider_id:
            self.vendor_name = self.provider_id.name

    @api.onchange('vendor_name')
    def _onchange_vendor_name(self):
        """Cherche automatiquement le fournisseur."""
        if self.vendor_name and not self.provider_id:
            provider = self.env['clearspend.saas.provider'].search([
                ('name', 'ilike', self.vendor_name)
            ], limit=1)
            if provider:
                self.provider_id = provider.id

    def action_match(self):
        """Marque comme associée."""
        for record in self:
            if not record.subscription_id:
                raise UserError("Veuillez d'abord sélectionner un abonnement.")
            record.state = 'matched'
            
            # Ajouter la référence à l'abonnement
            if record.subscription_id.invoice_refs:
                record.subscription_id.invoice_refs += f"\n{record.name}"
            else:
                record.subscription_id.invoice_refs = record.name
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✓ Facture associée',
                'message': f'Facture associée à {self.subscription_id.name}',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_process(self):
        """Marque comme en traitement."""
        self.write({'state': 'processing'})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🔄 En traitement',
                'message': 'Facture mise en traitement.',
                'type': 'info',
                'sticky': False,
            }
        }

    def action_archive(self):
        """Archive la facture."""
        self.write({'state': 'archived'})

    def action_back_to_inbox(self):
        """Remet dans l'inbox."""
        self.write({'state': 'inbox', 'subscription_id': False})

    def action_mark_paid(self):
        """Marque comme payée."""
        self.write({
            'is_paid': True,
            'payment_date': date.today(),
        })

    def action_auto_match(self):
        """Tente un matching automatique."""
        matched = 0
        for record in self:
            if record.state == 'inbox' and record.subscription_ids:
                # Si un seul abonnement suggéré avec confiance haute
                if len(record.subscription_ids) == 1:
                    sub = record.subscription_ids[0]
                    expected = sub.amount
                    if record.amount and expected:
                        diff_percent = abs(record.amount - expected) / expected * 100 if expected else 100
                        if diff_percent <= 10:
                            record.subscription_id = sub.id
                            record.state = 'matched'
                            matched += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🔄 Auto-matching',
                'message': f'{matched} facture(s) associée(s) automatiquement.',
                'type': 'success' if matched else 'warning',
            }
        }

    def action_open_subscription(self):
        """Ouvre l'abonnement lié."""
        self.ensure_one()
        if self.subscription_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'clearspend.subscription',
                'res_id': self.subscription_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    @api.model
    def get_inbox_count(self):
        """Retourne le nombre de factures dans l'inbox."""
        return self.search_count([('state', '=', 'inbox')])

    @api.model
    def sync_from_odoo_invoices(self):
        """
        Synchronise les factures fournisseur Odoo vers ClearSpend.
        Appelé par cron ou manuellement.
        """
        # Vérifier si le module account est installé
        if 'account.move' not in self.env:
            return {'synced': 0, 'message': 'Module Comptabilité non installé'}
        
        AccountMove = self.env['account.move']
        Provider = self.env['clearspend.saas.provider']
        
        # Chercher les factures fournisseur non encore importées
        # Types: in_invoice (facture fournisseur), in_refund (avoir fournisseur)
        existing_move_ids = self.search([('odoo_move_id', '>', 0)]).mapped('odoo_move_id')
        
        new_invoices = AccountMove.search([
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('state', '=', 'posted'),  # Seulement les factures validées
            ('id', 'not in', existing_move_ids),
        ], order='invoice_date desc', limit=100)
        
        synced = 0
        for move in new_invoices:
            # Chercher si le partenaire correspond à un fournisseur SaaS
            provider = False
            if move.partner_id:
                # Cherche par nom exact ou partiel
                provider = Provider.search([
                    '|',
                    ('name', '=ilike', move.partner_id.name),
                    ('name', 'ilike', move.partner_id.name.split()[0] if move.partner_id.name else ''),
                ], limit=1)
            
            # Créer l'entrée ClearSpend
            vals = {
                'name': move.name or move.ref or f"Facture {move.partner_id.name}",
                'odoo_move_id': move.id,
                'odoo_move_name': move.name,
                'is_from_odoo': True,
                'invoice_date': move.invoice_date,
                'due_date': move.invoice_date_due,
                'amount': abs(move.amount_total),
                'amount_ht': abs(move.amount_untaxed),
                'currency_id': move.currency_id.id,
                'vendor_name': move.partner_id.name if move.partner_id else '',
                'provider_id': provider.id if provider else False,
                'state': 'inbox',
                'is_paid': move.payment_state == 'paid',
            }
            
            # Récupérer le PDF attaché si disponible
            attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', move.id),
                ('mimetype', '=', 'application/pdf'),
            ], limit=1)
            if attachments:
                vals['invoice_file'] = attachments.datas
                vals['invoice_filename'] = attachments.name
            
            self.create(vals)
            synced += 1
        
        # Tenter un auto-match sur les nouvelles factures
        new_clearspend_invoices = self.search([
            ('is_from_odoo', '=', True),
            ('state', '=', 'inbox'),
            ('subscription_id', '=', False),
        ])
        new_clearspend_invoices.action_auto_match()
        
        return {
            'synced': synced,
            'message': f'{synced} facture(s) importée(s) depuis Odoo'
        }

    @api.model
    def cron_sync_odoo_invoices(self):
        """Cron pour synchroniser les factures Odoo."""
        result = self.sync_from_odoo_invoices()
        return True

    def action_open_odoo_invoice(self):
        """Ouvre la facture Odoo liée."""
        self.ensure_one()
        if self.odoo_move_id and 'account.move' in self.env:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': self.odoo_move_id,
                'view_mode': 'form',
                'target': 'current',
            }

    @api.model
    def action_manual_sync(self):
        """Action manuelle pour synchroniser depuis Odoo."""
        result = self.sync_from_odoo_invoices()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🔄 Synchronisation Odoo',
                'message': result['message'],
                'type': 'success' if result['synced'] > 0 else 'info',
                'sticky': False,
            }
        }

