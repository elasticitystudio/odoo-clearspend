# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date
from dateutil.relativedelta import relativedelta

class ClearspendBudget(models.Model):
    _name = 'clearspend.budget'
    _description = 'Budget SaaS'
    _order = 'year desc, month desc'

    name = fields.Char(string='Période', compute='_compute_name', store=True)
    year = fields.Integer(string='Année', required=True, default=lambda self: date.today().year)
    month = fields.Selection([
        ('1', 'Janvier'), ('2', 'Février'), ('3', 'Mars'), ('4', 'Avril'),
        ('5', 'Mai'), ('6', 'Juin'), ('7', 'Juillet'), ('8', 'Août'),
        ('9', 'Septembre'), ('10', 'Octobre'), ('11', 'Novembre'), ('12', 'Décembre'),
    ], string='Mois', required=True, default=lambda self: str(date.today().month))
    
    # Budget prévu par catégorie
    budget_total = fields.Float(string='Budget total (€)', required=True)
    budget_essential = fields.Float(string='Budget essentiels (€)')
    budget_important = fields.Float(string='Budget importants (€)')
    budget_optional = fields.Float(string='Budget optionnels (€)')
    
    # Dépenses réelles (calculées)
    spent_total = fields.Float(string='Dépensé total', compute='_compute_spent', store=True)
    spent_essential = fields.Float(string='Dépensé essentiels', compute='_compute_spent', store=True)
    spent_important = fields.Float(string='Dépensé importants', compute='_compute_spent', store=True)
    spent_optional = fields.Float(string='Dépensé optionnels', compute='_compute_spent', store=True)
    
    # Écarts
    variance_total = fields.Float(string='Écart total', compute='_compute_variance')
    variance_percent = fields.Float(string='Écart (%)', compute='_compute_variance')
    variance_essential = fields.Float(string='Écart essentiels', compute='_compute_variance')
    variance_important = fields.Float(string='Écart importants', compute='_compute_variance')
    variance_optional = fields.Float(string='Écart optionnels', compute='_compute_variance')
    
    # Statut
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('approved', 'Approuvé'),
        ('closed', 'Clôturé'),
    ], string='Statut', default='draft')
    
    status_indicator = fields.Char(string='Indicateur', compute='_compute_variance')
    
    notes = fields.Text(string='Notes')
    
    # Pour recalculer
    subscription_ids = fields.Many2many('clearspend.subscription', string='Abonnements inclus',
                                         compute='_compute_spent')

    @api.depends('year', 'month')
    def _compute_name(self):
        months = {
            '1': 'Janvier', '2': 'Février', '3': 'Mars', '4': 'Avril',
            '5': 'Mai', '6': 'Juin', '7': 'Juillet', '8': 'Août',
            '9': 'Septembre', '10': 'Octobre', '11': 'Novembre', '12': 'Décembre',
        }
        for record in self:
            record.name = f"{months.get(record.month, '')} {record.year}"

    @api.depends('year', 'month')
    def _compute_spent(self):
        Subscription = self.env['clearspend.subscription']
        
        for record in self:
            # Récupérer les abonnements actifs
            active_subs = Subscription.search([('state', 'in', ['active', 'validated'])])
            
            total = essential = important = optional = 0.0
            sub_ids = []
            
            for sub in active_subs:
                # Calculer le montant mensuel
                amount = sub.amount_eur or sub.amount
                if sub.billing_cycle == 'monthly':
                    monthly_amount = amount
                elif sub.billing_cycle == 'quarterly':
                    monthly_amount = amount / 3
                else:  # yearly
                    monthly_amount = amount / 12
                
                total += monthly_amount
                sub_ids.append(sub.id)
                
                if sub.category == 'essential':
                    essential += monthly_amount
                elif sub.category == 'important':
                    important += monthly_amount
                elif sub.category in ('optional', 'to_review'):
                    optional += monthly_amount
            
            record.spent_total = total
            record.spent_essential = essential
            record.spent_important = important
            record.spent_optional = optional
            record.subscription_ids = [(6, 0, sub_ids)]

    @api.depends('budget_total', 'spent_total')
    def _compute_variance(self):
        for record in self:
            record.variance_total = record.budget_total - record.spent_total
            record.variance_essential = record.budget_essential - record.spent_essential
            record.variance_important = record.budget_important - record.spent_important
            record.variance_optional = record.budget_optional - record.spent_optional
            
            if record.budget_total > 0:
                used_percent = (record.spent_total / record.budget_total) * 100
                record.variance_percent = 100 - used_percent
                
                if used_percent >= 100:
                    record.status_indicator = '🔴 Dépassé'
                elif used_percent >= 90:
                    record.status_indicator = '🟠 Attention'
                elif used_percent >= 70:
                    record.status_indicator = '🟡 En cours'
                else:
                    record.status_indicator = '🟢 OK'
            else:
                record.variance_percent = 0
                record.status_indicator = '⚪ Non défini'

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_refresh(self):
        """Recalcule les dépenses et synchronise le budget depuis la config."""
        # Sync budget_total depuis config si pas encore défini ou si = 0
        config = self.env['clearspend.config'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if config and config.budget_monthly and self.budget_total == 0:
            self.budget_total = config.budget_monthly
        self._compute_spent()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🔄 Actualisé',
                'message': 'Les dépenses ont été recalculées.',
                'type': 'success',
            }
        }

    @api.model
    def get_or_create_current(self):
        """Récupère ou crée le budget du mois courant."""
        today = date.today()
        budget = self.search([
            ('year', '=', today.year),
            ('month', '=', str(today.month)),
        ], limit=1)
        
        if not budget:
            # Récupérer le budget du mois précédent comme base
            prev_month = today - relativedelta(months=1)
            prev_budget = self.search([
                ('year', '=', prev_month.year),
                ('month', '=', str(prev_month.month)),
            ], limit=1)
            
            # Priorité : config > mois précédent > 0
            config = self.env['clearspend.config'].search([
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            if config and config.budget_monthly:
                default_total = config.budget_monthly
            elif prev_budget:
                default_total = prev_budget.budget_total
            else:
                default_total = 0
            
            budget = self.create({
                'year': today.year,
                'month': str(today.month),
                'budget_total': default_total,
            })
        
        return budget

    @api.model
    def get_budget_projection(self, months=6):
        """Projette les dépenses sur X mois."""
        Subscription = self.env['clearspend.subscription']
        active_subs = Subscription.search([('state', 'in', ['active', 'validated'])])
        
        projections = []
        today = date.today()
        
        for i in range(months):
            future_date = today + relativedelta(months=i)
            
            monthly_total = 0.0
            for sub in active_subs:
                amount = sub.amount_eur or sub.amount
                if sub.billing_cycle == 'monthly':
                    monthly_total += amount
                elif sub.billing_cycle == 'quarterly':
                    monthly_total += amount / 3
                else:  # yearly
                    monthly_total += amount / 12
            
            months_names = {
                1: 'Jan', 2: 'Fév', 3: 'Mar', 4: 'Avr',
                5: 'Mai', 6: 'Juin', 7: 'Juil', 8: 'Août',
                9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Déc',
            }
            
            projections.append({
                'month': f"{months_names[future_date.month]} {future_date.year}",
                'amount': monthly_total,
            })
        
        return projections
