# -*- coding: utf-8 -*-
from odoo import models, api
from datetime import date, timedelta

class ClearspendSubscriptionReport(models.AbstractModel):
    _name = 'report.clearspend.report_subscription_document'
    _description = 'Rapport des abonnements'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['clearspend.subscription'].browse(docids)
        
        # Calcul des totaux
        monthly_total = 0.0
        for sub in docs:
            if sub.billing_cycle == 'monthly':
                monthly_total += sub.amount
            elif sub.billing_cycle == 'quarterly':
                monthly_total += sub.amount / 3
            elif sub.billing_cycle == 'yearly':
                monthly_total += sub.amount / 12
        
        return {
            'doc_ids': docids,
            'doc_model': 'clearspend.subscription',
            'docs': docs,
            'total_monthly': monthly_total,
            'total_yearly': monthly_total * 12,
        }


class ClearspendMonthlyReport(models.AbstractModel):
    _name = 'report.clearspend.report_monthly_document'
    _description = 'Rapport mensuel ClearSpend'

    @api.model
    def _get_report_values(self, docids, data=None):
        Subscription = self.env['clearspend.subscription']
        Config = self.env['clearspend.config']
        
        config = Config.browse(docids[0]) if docids else Config.get_config()
        company = config.company_id or self.env.company
        
        # Abonnements actifs
        active_subs = Subscription.search([('state', 'in', ['active', 'validated'])])
        
        # Calcul du coût mensuel
        monthly_total = 0.0
        for sub in active_subs:
            amount = sub.amount_eur or sub.amount
            if sub.billing_cycle == 'monthly':
                monthly_total += amount
            elif sub.billing_cycle == 'quarterly':
                monthly_total += amount / 3
            elif sub.billing_cycle == 'yearly':
                monthly_total += amount / 12
        
        # Par priorité
        essential = active_subs.filtered(lambda s: s.category == 'essential')
        important = active_subs.filtered(lambda s: s.category == 'important')
        optional = active_subs.filtered(lambda s: s.category == 'optional')
        to_review = active_subs.filtered(lambda s: s.category == 'to_review')
        
        def calc_monthly(subs):
            total = 0.0
            for s in subs:
                amount = s.amount_eur or s.amount
                if s.billing_cycle == 'monthly':
                    total += amount
                elif s.billing_cycle == 'quarterly':
                    total += amount / 3
                elif s.billing_cycle == 'yearly':
                    total += amount / 12
            return total
        
        essential_amount = calc_monthly(essential)
        important_amount = calc_monthly(important)
        optional_amount = calc_monthly(optional)
        to_review_amount = calc_monthly(to_review)
        
        total_priority = essential_amount + important_amount + optional_amount + to_review_amount or 1
        
        # Renouvellements dans les 30 jours
        today = date.today()
        renewals = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('renewal_date', '>=', today),
            ('renewal_date', '<=', today + timedelta(days=30)),
        ], order='renewal_date')
        
        # Top 10 abonnements par coût mensuel
        all_subs_with_cost = []
        for sub in active_subs:
            amount = sub.amount_eur or sub.amount
            if sub.billing_cycle == 'monthly':
                monthly_cost = amount
            elif sub.billing_cycle == 'quarterly':
                monthly_cost = amount / 3
            elif sub.billing_cycle == 'yearly':
                monthly_cost = amount / 12
            else:
                monthly_cost = amount
            sub.monthly_cost = monthly_cost  # Ajout temporaire
            all_subs_with_cost.append((sub, monthly_cost))
        
        top_subscriptions = [s[0] for s in sorted(all_subs_with_cost, key=lambda x: -x[1])[:10]]
        
        # Score FinOps simplifié
        score = 100
        if len(to_review) > 2:
            score -= 10
        if len(essential) < len(active_subs) * 0.3:
            score -= 15
        if monthly_total > 0 and essential_amount / monthly_total < 0.3:
            score -= 10
        score = max(0, min(100, score))
        
        # Budget
        budget_monthly = config.budget_monthly or 0
        budget_percent = (monthly_total / budget_monthly * 100) if budget_monthly > 0 else 0
        
        return {
            'doc_ids': docids,
            'doc_model': 'clearspend.config',
            'docs': config,
            'company': company,
            'report_month': date.today().strftime('%B %Y'),
            'total_monthly': monthly_total,
            'total_yearly': monthly_total * 12,
            'subscription_count': len(active_subs),
            'finops_score': score,
            'budget_monthly': budget_monthly,
            'budget_percent': budget_percent,
            'essential_count': len(essential),
            'essential_amount': essential_amount,
            'essential_percent': (essential_amount / total_priority) * 100,
            'important_count': len(important),
            'important_amount': important_amount,
            'important_percent': (important_amount / total_priority) * 100,
            'optional_count': len(optional),
            'optional_amount': optional_amount,
            'optional_percent': (optional_amount / total_priority) * 100,
            'to_review_count': len(to_review),
            'to_review_amount': to_review_amount,
            'to_review_percent': (to_review_amount / total_priority) * 100,
            'renewals': renewals,
            'top_subscriptions': top_subscriptions,
        }
