# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

class ClearspendExpenseHistory(models.Model):
    _name = 'clearspend.expense.history'
    _description = 'Historique des dépenses'
    _order = 'date desc'

    date = fields.Date(string='Date', required=True)
    month = fields.Char(string='Mois', compute='_compute_period', store=True)
    year = fields.Char(string='Année', compute='_compute_period', store=True)
    total_monthly = fields.Float(string='Total mensuel')
    subscription_count = fields.Integer(string='Nb abonnements')
    essential_amount = fields.Float(string='Essentiels')
    important_amount = fields.Float(string='Importants')
    optional_amount = fields.Float(string='Optionnels')
    finops_score = fields.Integer(string='Score FinOps')

    @api.depends('date')
    def _compute_period(self):
        months_fr = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
            5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
            9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
        }
        for record in self:
            if record.date:
                record.month = months_fr.get(record.date.month, '')
                record.year = str(record.date.year)
            else:
                record.month = ''
                record.year = ''

    @api.model
    def record_snapshot(self):
        """Enregistre un snapshot des dépenses actuelles."""
        Subscription = self.env['clearspend.subscription']
        
        active_subs = Subscription.search([('state', 'in', ['active', 'validated'])])
        
        # Calculer les totaux
        monthly_total = 0.0
        essential_total = 0.0
        important_total = 0.0
        optional_total = 0.0
        
        for sub in active_subs:
            if sub.billing_cycle == 'monthly':
                amount = sub.amount
            elif sub.billing_cycle == 'quarterly':
                amount = sub.amount / 3
            else:  # yearly
                amount = sub.amount / 12
            
            monthly_total += amount
            
            if sub.category == 'essential':
                essential_total += amount
            elif sub.category == 'important':
                important_total += amount
            elif sub.category in ('optional', 'to_review'):
                optional_total += amount
        
        # Calculer le score (simplifié)
        score = 100
        if len(active_subs) > 0:
            essential_ratio = len(active_subs.filtered(lambda s: s.category == 'essential')) / len(active_subs)
            if essential_ratio < 0.3:
                score -= 15
            to_review_count = len(active_subs.filtered(lambda s: s.category == 'to_review'))
            if to_review_count > 2:
                score -= 10
        
        # Vérifier si un snapshot existe déjà pour aujourd'hui
        today = date.today()
        existing = self.search([('date', '=', today)], limit=1)
        
        vals = {
            'date': today,
            'total_monthly': monthly_total,
            'subscription_count': len(active_subs),
            'essential_amount': essential_total,
            'important_amount': important_total,
            'optional_amount': optional_total,
            'finops_score': max(0, min(100, score)),
        }
        
        if existing:
            existing.write(vals)
        else:
            self.create(vals)
        
        return True

    @api.model
    def generate_demo_history(self):
        """Génère un historique de démo sur 12 mois."""
        today = date.today()
        
        # Supprimer l'ancien historique de démo
        self.search([]).unlink()
        
        base_amount = 500  # Montant de base
        
        for i in range(12):
            past_date = today - relativedelta(months=i)
            # Variation aléatoire simulée
            variation = 1 + (i % 3) * 0.05  # +0%, +5%, +10%
            amount = base_amount * variation
            
            self.create({
                'date': past_date.replace(day=1),
                'total_monthly': amount + (i * 20),  # Croissance progressive
                'subscription_count': 10 + i,
                'essential_amount': amount * 0.5,
                'important_amount': amount * 0.35,
                'optional_amount': amount * 0.15,
                'finops_score': 85 - i,
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Historique généré',
                'message': '12 mois d\'historique de démo créés.',
                'type': 'success',
            }
        }
