# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

class ClearspendForecast(models.TransientModel):
    _name = 'clearspend.forecast'
    _description = 'Prévisions des coûts'

    name = fields.Char(string='Nom', compute='_compute_name')
    
    # Période de prévision
    forecast_months = fields.Selection([
        ('3', '3 mois'),
        ('6', '6 mois'),
        ('12', '12 mois'),
        ('24', '24 mois'),
    ], string='Horizon', default='12')
    
    # Hypothèses
    inflation_rate = fields.Float(string='Taux d\'inflation annuel (%)', default=3.0)
    include_renewals = fields.Boolean(string='Inclure renouvellements', default=True)
    include_new_estimates = fields.Boolean(string='Inclure estimations nouvelles dépenses', default=False)
    growth_rate = fields.Float(string='Croissance estimée (%)', default=5.0,
                                help="Taux de croissance des dépenses SaaS (nouveaux outils)")
    
    # Résultats globaux
    current_monthly = fields.Float(string='Coût mensuel actuel', compute='_compute_forecast')
    current_yearly = fields.Float(string='Coût annuel actuel', compute='_compute_forecast')
    
    projected_total = fields.Float(string='Total projeté', compute='_compute_forecast')
    projected_monthly_avg = fields.Float(string='Moyenne mensuelle projetée', compute='_compute_forecast')
    projected_yearly = fields.Float(string='Coût annuel projeté', compute='_compute_forecast')
    
    variation_amount = fields.Float(string='Variation (€)', compute='_compute_forecast')
    variation_percent = fields.Float(string='Variation (%)', compute='_compute_forecast')
    
    # Détail par mois (stocké en JSON pour affichage)
    forecast_data = fields.Text(string='Données prévision', compute='_compute_forecast')
    
    # Détail par catégorie
    forecast_by_category = fields.Text(string='Par catégorie', compute='_compute_forecast')
    
    # Alertes prévisions
    renewal_alerts = fields.Text(string='Renouvellements à venir', compute='_compute_forecast')
    contract_endings = fields.Text(string='Fins de contrat', compute='_compute_forecast')
    
    # Compteurs
    subscription_count = fields.Integer(string='Abonnements actifs', compute='_compute_forecast')
    renewal_count = fields.Integer(string='Renouvellements prévus', compute='_compute_forecast')
    contract_ending_count = fields.Integer(string='Contrats se terminant', compute='_compute_forecast')

    def _compute_name(self):
        for record in self:
            record.name = f"Prévisions {record.forecast_months} mois"

    @api.depends('forecast_months', 'inflation_rate', 'include_renewals', 'include_new_estimates', 'growth_rate')
    def _compute_forecast(self):
        for record in self:
            Subscription = self.env['clearspend.subscription']
            Contract = self.env['clearspend.contract']
            
            # Récupérer les abonnements actifs
            subscriptions = Subscription.search([('state', 'in', ['active', 'validated'])])
            record.subscription_count = len(subscriptions)
            
            # Calculer le coût mensuel actuel
            current_monthly = 0.0
            for sub in subscriptions:
                amount = sub.amount_eur or sub.amount
                if sub.billing_cycle == 'monthly':
                    current_monthly += amount
                elif sub.billing_cycle == 'quarterly':
                    current_monthly += amount / 3
                elif sub.billing_cycle == 'yearly':
                    current_monthly += amount / 12
            
            current_yearly = current_monthly * 12
            record.current_monthly = current_monthly
            record.current_yearly = current_yearly
            
            # Paramètres
            months = int(record.forecast_months)
            monthly_inflation = (record.inflation_rate / 100) / 12
            monthly_growth = (record.growth_rate / 100) / 12 if record.include_new_estimates else 0
            
            today = date.today()
            
            # Calculer mois par mois
            monthly_forecasts = []
            renewals_list = []
            contracts_ending = []
            category_totals = {}
            
            for month_offset in range(months):
                forecast_date = today + relativedelta(months=month_offset)
                month_key = forecast_date.strftime('%Y-%m')
                month_label = forecast_date.strftime('%b %Y')
                
                month_total = 0
                month_renewals = []
                
                for sub in subscriptions:
                    # Coût de base mensuel (calculé selon le cycle)
                    amount = sub.amount_eur or sub.amount
                    if sub.billing_cycle == 'monthly':
                        base_cost = amount
                    elif sub.billing_cycle == 'quarterly':
                        base_cost = amount / 3
                    elif sub.billing_cycle == 'yearly':
                        base_cost = amount / 12
                    else:
                        base_cost = amount
                    
                    # Appliquer inflation progressive
                    inflated_cost = base_cost * (1 + monthly_inflation) ** month_offset
                    
                    # Vérifier si renouvellement ce mois-ci
                    is_renewal_month = False
                    if record.include_renewals and sub.renewal_date:
                        renewal_date = sub.renewal_date
                        # Projeter les renouvellements futurs selon le cycle
                        cycle_months = {'monthly': 1, 'quarterly': 3, 'yearly': 12}.get(sub.billing_cycle, 1)
                        
                        temp_date = renewal_date
                        while temp_date <= forecast_date:
                            if temp_date.year == forecast_date.year and temp_date.month == forecast_date.month:
                                is_renewal_month = True
                                if month_offset > 0:  # Pas le mois actuel
                                    month_renewals.append({
                                        'name': sub.name,
                                        'amount': sub.amount,
                                        'cycle': sub.billing_cycle,
                                    })
                                break
                            temp_date = temp_date + relativedelta(months=cycle_months)
                    
                    month_total += inflated_cost
                    
                    # Agrégation par catégorie
                    cat = sub.category or 'saas'
                    if cat not in category_totals:
                        category_totals[cat] = 0
                    category_totals[cat] += inflated_cost
                
                # Ajouter croissance estimée (nouveaux outils)
                if record.include_new_estimates:
                    growth_addition = current_monthly * monthly_growth * month_offset
                    month_total += growth_addition
                
                monthly_forecasts.append({
                    'month': month_label,
                    'amount': round(month_total, 2),
                    'renewals': len(month_renewals),
                })
                
                if month_renewals:
                    renewals_list.extend([{**r, 'month': month_label} for r in month_renewals])
            
            # Contrats se terminant dans la période
            end_date = today + relativedelta(months=months)
            ending_contracts = Contract.search([
                ('state', '=', 'active'),
                ('end_date', '>=', today),
                ('end_date', '<=', end_date),
            ])
            record.contract_ending_count = len(ending_contracts)
            
            for contract in ending_contracts:
                contracts_ending.append({
                    'name': contract.name,
                    'end_date': contract.end_date.strftime('%d/%m/%Y') if contract.end_date else '',
                    'provider': contract.provider_id.name if contract.provider_id else '',
                })
            
            # Calculs finaux
            total_projected = sum(f['amount'] for f in monthly_forecasts)
            avg_monthly = total_projected / months if months else 0
            projected_yearly = avg_monthly * 12
            
            record.projected_total = total_projected
            record.projected_monthly_avg = avg_monthly
            record.projected_yearly = projected_yearly
            
            record.variation_amount = projected_yearly - current_yearly
            record.variation_percent = ((projected_yearly - current_yearly) / current_yearly * 100) if current_yearly else 0
            
            record.renewal_count = len(renewals_list)
            
            # Formater les données de manière simple et lisible
            # Projection mois par mois - format tableau simple
            forecast_lines = []
            for i, f in enumerate(monthly_forecasts):
                # Indicateur de tendance
                if i == 0:
                    trend = ""
                else:
                    diff = f['amount'] - monthly_forecasts[i-1]['amount']
                    trend = " ↗" if diff > 0 else " ↘" if diff < 0 else ""
                
                renewal_text = f"  •  {f['renewals']} renouv." if f['renewals'] > 0 else ""
                line = f"{f['month']}   {f['amount']:,.0f} €{trend}{renewal_text}"
                forecast_lines.append(line)
            record.forecast_data = "\n".join(forecast_lines)
            
            # Par catégorie - simple et clair
            category_labels = {
                'essential': '🔴 Essentiels',
                'important': '🟠 Importants', 
                'optional': '🟡 Optionnels',
                'to_review': '⚪ À revoir',
                'saas': '💻 SaaS',
            }
            total_cat = sum(category_totals.values()) or 1
            category_lines = []
            for cat, total in sorted(category_totals.items(), key=lambda x: -x[1]):
                label = category_labels.get(cat, cat.capitalize())
                avg = total / months if months else 0
                pct = (total / total_cat) * 100
                category_lines.append(f"{label}\n{avg:,.0f} € / mois  ({pct:.0f}%)")
            record.forecast_by_category = "\n\n".join(category_lines) if category_lines else "Aucune donnée"
            
            # Renouvellements à venir - groupés par mois, plus compact
            if renewals_list:
                renewals_by_month = {}
                for r in renewals_list[:20]:
                    month = r['month']
                    if month not in renewals_by_month:
                        renewals_by_month[month] = []
                    renewals_by_month[month].append(r)
                
                renewal_lines = []
                for month, items in list(renewals_by_month.items())[:6]:  # Max 6 mois
                    total_month = sum(r['amount'] for r in items)
                    renewal_lines.append(f"▸ {month} — {len(items)} renouv. ({total_month:,.0f} €)")
                    for r in items[:4]:  # Max 4 items par mois
                        renewal_lines.append(f"   {r['name']}: {r['amount']:,.0f} €")
                    if len(items) > 4:
                        renewal_lines.append(f"   + {len(items) - 4} autres...")
                    renewal_lines.append("")
                record.renewal_alerts = "\n".join(renewal_lines).strip()
            else:
                record.renewal_alerts = "✅ Aucun renouvellement majeur prévu"
            
            # Contrats se terminant
            if contracts_ending:
                contract_lines = [f"▸ {c['name']} — fin le {c['end_date']}" for c in contracts_ending]
                record.contract_endings = "\n".join(contract_lines)
            else:
                record.contract_endings = "✅ Aucun contrat ne se termine"

    @api.model
    def open_forecast(self):
        """Ouvre la vue des prévisions."""
        forecast = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': '📈 Prévisions des coûts',
            'res_model': 'clearspend.forecast',
            'view_mode': 'form',
            'res_id': forecast.id,
            'target': 'current',
        }

    def action_refresh(self):
        """Rafraîchit les calculs."""
        self._compute_forecast()
        return {
            'type': 'ir.actions.act_window',
            'name': '📈 Prévisions des coûts',
            'res_model': 'clearspend.forecast',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_export_pdf(self):
        """Export PDF des prévisions (à implémenter)."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '📄 Export PDF',
                'message': 'Fonctionnalité à venir',
                'type': 'info',
                'sticky': False,
            }
        }
