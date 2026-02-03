# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date, timedelta

class ClearspendContract(models.Model):
    _name = 'clearspend.contract'
    _description = 'Contrat SaaS'
    _order = 'end_date asc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nom du contrat', required=True, tracking=True)
    subscription_id = fields.Many2one('clearspend.subscription', string='Abonnement lié', 
                                       ondelete='cascade', tracking=True)
    provider_id = fields.Many2one('clearspend.saas.provider', string='Fournisseur',
                                   related='subscription_id.provider_id', store=True)
    
    # Fichier PDF
    contract_file = fields.Binary(string='Fichier contrat', attachment=True)
    contract_filename = fields.Char(string='Nom du fichier')
    file_size = fields.Char(string='Taille', compute='_compute_file_size')
    
    # Dates
    start_date = fields.Date(string='Date de début', tracking=True)
    end_date = fields.Date(string='Date de fin', tracking=True)
    signature_date = fields.Date(string='Date de signature')
    
    # Conditions
    contract_type = fields.Selection([
        ('monthly', 'Mensuel'),
        ('annual', 'Annuel'),
        ('multi_year', 'Pluriannuel'),
        ('perpetual', 'Perpétuel'),
    ], string='Type de contrat', default='annual')
    
    auto_renewal = fields.Boolean(string='Renouvellement auto', default=True)
    notice_period = fields.Integer(string='Préavis (jours)', default=30,
                                    help="Nombre de jours avant la fin pour résilier")
    notice_date = fields.Date(string='Date limite préavis', compute='_compute_notice_date', store=True)
    
    # Financier
    contract_value = fields.Float(string='Valeur totale (€)', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Devise',
                                   default=lambda self: self.env.company.currency_id)
    payment_terms = fields.Selection([
        ('monthly', 'Mensuel'),
        ('quarterly', 'Trimestriel'),
        ('annual', 'Annuel'),
        ('upfront', 'Paiement initial'),
    ], string='Modalités paiement', default='annual')
    
    # Clauses importantes
    min_users = fields.Integer(string='Utilisateurs min.')
    max_users = fields.Integer(string='Utilisateurs max.')
    price_lock = fields.Boolean(string='Prix garanti', help="Le prix ne peut pas augmenter pendant la durée")
    price_increase_cap = fields.Float(string='Hausse max (%)', help="Augmentation maximale autorisée au renouvellement")
    
    # Notes
    notes = fields.Text(string='Notes / Clauses importantes')
    key_terms = fields.Text(string='Conditions clés',
                            help="Résumé des conditions importantes du contrat")
    
    # Statut
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('active', 'Actif'),
        ('expiring', 'Expire bientôt'),
        ('expired', 'Expiré'),
        ('renewed', 'Renouvelé'),
        ('cancelled', 'Résilié'),
    ], string='Statut', default='draft', tracking=True)
    
    days_until_end = fields.Integer(string='Jours restants', compute='_compute_days_until_end')
    days_until_notice = fields.Integer(string='Jours avant préavis', compute='_compute_days_until_end')

    @api.depends('contract_file')
    def _compute_file_size(self):
        for record in self:
            if record.contract_file:
                # Taille approximative en base64
                size_bytes = len(record.contract_file) * 3 / 4
                if size_bytes > 1048576:
                    record.file_size = f"{size_bytes / 1048576:.1f} MB"
                elif size_bytes > 1024:
                    record.file_size = f"{size_bytes / 1024:.1f} KB"
                else:
                    record.file_size = f"{size_bytes:.0f} B"
            else:
                record.file_size = ''

    @api.depends('end_date', 'notice_period')
    def _compute_notice_date(self):
        for record in self:
            if record.end_date and record.notice_period:
                record.notice_date = record.end_date - timedelta(days=record.notice_period)
            else:
                record.notice_date = False

    @api.depends('end_date', 'notice_date')
    def _compute_days_until_end(self):
        today = date.today()
        for record in self:
            if record.end_date:
                delta = (record.end_date - today).days
                record.days_until_end = delta
            else:
                record.days_until_end = 0
            
            if record.notice_date:
                delta_notice = (record.notice_date - today).days
                record.days_until_notice = delta_notice
            else:
                record.days_until_notice = 0

    def action_activate(self):
        self.write({'state': 'active'})

    def action_renew(self):
        """Renouvelle le contrat."""
        self.ensure_one()
        # Créer un nouveau contrat basé sur celui-ci
        new_contract = self.copy({
            'name': f"{self.name} (Renouvellement)",
            'start_date': self.end_date,
            'end_date': self.end_date + timedelta(days=365) if self.contract_type == 'annual' else False,
            'state': 'draft',
            'contract_file': False,
            'contract_filename': False,
        })
        self.write({'state': 'renewed'})
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'clearspend.contract',
            'res_id': new_contract.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    @api.model
    def update_contract_states(self):
        """Met à jour les statuts des contrats (cron)."""
        today = date.today()
        
        # Contrats expirés
        expired = self.search([
            ('state', 'in', ['active', 'expiring']),
            ('end_date', '<', today),
        ])
        expired.write({'state': 'expired'})
        
        # Contrats qui expirent bientôt (30 jours)
        expiring_soon = self.search([
            ('state', '=', 'active'),
            ('end_date', '>=', today),
            ('end_date', '<=', today + timedelta(days=30)),
        ])
        expiring_soon.write({'state': 'expiring'})
        
        return True

    @api.model
    def get_expiring_contracts(self, days=30):
        """Retourne les contrats qui expirent dans X jours."""
        today = date.today()
        return self.search([
            ('state', 'in', ['active', 'expiring']),
            ('end_date', '>=', today),
            ('end_date', '<=', today + timedelta(days=days)),
        ])
