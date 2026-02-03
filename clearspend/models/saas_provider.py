# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ClearspendSaasProvider(models.Model):
    _name = 'clearspend.saas.provider'
    _description = 'Fournisseur SaaS'
    _order = 'name'

    name = fields.Char(string='Nom', required=True)
    website = fields.Char(string='Site web')
    category = fields.Selection([
        ('productivity', 'Productivité'),
        ('communication', 'Communication'),
        ('marketing', 'Marketing'),
        ('finance', 'Finance'),
        ('hr', 'RH'),
        ('dev', 'Développement'),
        ('design', 'Design'),
        ('storage', 'Stockage'),
        ('security', 'Sécurité'),
        ('other', 'Autre'),
    ], string='Catégorie', default='other')
    logo = fields.Image(string='Logo', max_width=128, max_height=128)
    notes = fields.Text(string='Notes')
    
    # Alternatives
    alternative_ids = fields.Many2many(
        'clearspend.saas.provider', 
        'clearspend_provider_alternatives_rel',
        'provider_id', 
        'alternative_id',
        string='Alternatives moins chères')
    avg_price_monthly = fields.Float(string='Prix moyen (€/utilisateur/mois)',
                                      help="Prix indicatif pour comparaison")
    
    subscription_ids = fields.One2many('clearspend.subscription', 'provider_id', string='Abonnements')
    subscription_count = fields.Integer(string='Nb abonnements', compute='_compute_subscription_count')

    def _compute_subscription_count(self):
        for record in self:
            record.subscription_count = len(record.subscription_ids)
    
    def action_view_alternatives(self):
        """Affiche les alternatives de ce fournisseur."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Alternatives à {self.name}',
            'res_model': 'clearspend.saas.provider',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.alternative_ids.ids)],
        }
