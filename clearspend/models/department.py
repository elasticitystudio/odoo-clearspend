# -*- coding: utf-8 -*-

from odoo import models, fields, api


class Department(models.Model):
    _name = 'clearspend.department'
    _description = 'Département'
    _order = 'name'

    name = fields.Char(string='Nom', required=True)
    code = fields.Char(string='Code', help='Code court (ex: IT, RH, MKT)')
    description = fields.Text(string='Description')
    
    # État
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('active', 'Actif'),
    ], string='État', default='draft', tracking=True)
    
    # Responsable
    manager_id = fields.Many2one('res.users', string='Responsable')
    member_ids = fields.Many2many('res.users', string='Membres',
                                   help='Utilisateurs autorisés à saisir des dépenses pour ce département')
    
    # Budget
    monthly_budget = fields.Float(string='Budget mensuel (€)')
    yearly_budget = fields.Float(string='Budget annuel (€)', compute='_compute_yearly_budget', store=True)
    
    # Couleur pour les graphiques
    color = fields.Integer(string='Couleur')
    
    # Stats calculées
    subscription_count = fields.Integer(string='Nb abonnements', compute='_compute_stats')
    total_monthly = fields.Float(string='Coût mensuel', compute='_compute_stats')
    total_yearly = fields.Float(string='Coût annuel', compute='_compute_stats')
    budget_used_percent = fields.Float(string='Budget utilisé (%)', compute='_compute_stats')
    
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)

    _sql_constraints = [
        ('code_unique', 'unique(code, company_id)', 'Le code département doit être unique par société.')
    ]

    def action_validate(self):
        """Valide le département."""
        self.write({'state': 'active'})

    def action_draft(self):
        """Remet en brouillon."""
        self.write({'state': 'draft'})

    @api.depends('monthly_budget')
    def _compute_yearly_budget(self):
        for record in self:
            record.yearly_budget = record.monthly_budget * 12

    @api.depends('name')
    def _compute_stats(self):
        Subscription = self.env['clearspend.subscription']
        for record in self:
            subs = Subscription.search([
                ('department_id', '=', record.id),
                ('state', 'in', ['active', 'validated'])
            ])
            
            record.subscription_count = len(subs)
            
            total = 0
            for sub in subs:
                amount = sub.amount_eur or sub.amount
                if sub.billing_cycle == 'monthly':
                    total += amount
                elif sub.billing_cycle == 'quarterly':
                    total += amount / 3
                elif sub.billing_cycle == 'yearly':
                    total += amount / 12
                else:
                    total += amount
            
            record.total_monthly = total
            record.total_yearly = total * 12
            
            if record.monthly_budget > 0:
                record.budget_used_percent = (total / record.monthly_budget) * 100
            else:
                record.budget_used_percent = 0

    def action_view_subscriptions(self):
        """Affiche les abonnements du département."""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Abonnements - {self.name}',
            'res_model': 'clearspend.subscription',
            'view_mode': 'list,kanban,form',
            'domain': [('department_id', '=', self.id)],
            'context': {'default_department_id': self.id},
        }

    def action_view_invoices(self):
        """Affiche les factures du département."""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Factures - {self.name}',
            'res_model': 'clearspend.invoice',
            'view_mode': 'list,kanban,form',
            'domain': [('department_id', '=', self.id)],
        }


class SubscriptionDepartmentMixin(models.Model):
    """Ajoute le département aux abonnements."""
    _inherit = 'clearspend.subscription'
    
    department_id = fields.Many2one('clearspend.department', string='Département',
                                     tracking=True, index=True)
    department_manager_id = fields.Many2one('res.users', string='Responsable dept.',
                                            related='department_id.manager_id', store=True)


class InvoiceDepartmentMixin(models.Model):
    """Ajoute le département aux factures."""
    _inherit = 'clearspend.invoice'
    
    department_id = fields.Many2one('clearspend.department', string='Département',
                                     compute='_compute_department', store=True, readonly=False)

    @api.depends('subscription_id')
    def _compute_department(self):
        for record in self:
            if record.subscription_id and record.subscription_id.department_id:
                record.department_id = record.subscription_id.department_id
            elif not record.department_id:
                record.department_id = False


class BudgetDepartmentMixin(models.Model):
    """Ajoute le département aux budgets."""
    _inherit = 'clearspend.budget'
    
    department_id = fields.Many2one('clearspend.department', string='Département', index=True)


class ContractDepartmentMixin(models.Model):
    """Ajoute le département aux contrats."""
    _inherit = 'clearspend.contract'
    
    department_id = fields.Many2one('clearspend.department', string='Département',
                                     compute='_compute_department', store=True, readonly=False)

    @api.depends('subscription_id')
    def _compute_department(self):
        for record in self:
            if record.subscription_id and record.subscription_id.department_id:
                record.department_id = record.subscription_id.department_id
            elif not record.department_id:
                record.department_id = False
