# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ClearspendDashboard(models.TransientModel):
    _name = 'clearspend.dashboard'
    _description = 'Dashboard ClearSpend'

    name = fields.Char(string='Nom', compute='_compute_name', store=False)
    company_name = fields.Char(string='Société', compute='_compute_name', store=False)
    
    # Mode Simple / Avancé
    is_simple_mode = fields.Boolean(string='Mode Simple', compute='_compute_mode')
    is_advanced_mode = fields.Boolean(string='Mode Avancé', compute='_compute_mode')
    current_mode = fields.Char(string='Mode actuel', compute='_compute_mode')
    
    # Stats par département (pour CFO)
    department_stats = fields.Text(string='Stats départements', compute='_compute_department_stats')
    department_count = fields.Integer(string='Nb départements', compute='_compute_department_stats')
    departments_over_budget = fields.Integer(string='Dépassements budget', compute='_compute_department_stats')
    
    @api.depends_context('company')
    def _compute_mode(self):
        """Détermine le mode actuel depuis la configuration."""
        Config = self.env['clearspend.config']
        config = Config.get_config()
        for record in self:
            record.is_simple_mode = config.mode == 'simple'
            record.is_advanced_mode = config.mode == 'advanced'
            record.current_mode = '🟢 Simple' if config.mode == 'simple' else '🔵 Avancé'
    
    @api.depends_context('company')
    def _compute_name(self):
        for record in self:
            company_name = self.env.company.name or 'ClearSpend'
            record.company_name = company_name
            record.name = f"🎛️ {company_name}"
    
    @api.depends_context('uid')
    def _compute_department_stats(self):
        """Calcule les statistiques par département pour le CFO."""
        Department = self.env['clearspend.department']
        
        for record in self:
            departments = Department.search([])
            record.department_count = len(departments)
            record.departments_over_budget = len(departments.filtered(lambda d: d.budget_used_percent > 100))
            
            # Construire un résumé textuel
            stats = []
            for dept in departments.sorted(key=lambda d: d.total_monthly, reverse=True):
                status = "🔴" if dept.budget_used_percent > 100 else "🟠" if dept.budget_used_percent > 80 else "🟢"
                stats.append(f"{status} {dept.name}: {dept.total_monthly:.0f}€/mois ({dept.budget_used_percent:.0f}%)")
            
            record.department_stats = "\n".join(stats) if stats else "Aucun département configuré"

    @api.model
    def get_department_analysis(self):
        """Retourne les données d'analyse par département pour les graphiques."""
        Department = self.env['clearspend.department']
        Subscription = self.env['clearspend.subscription']
        
        departments = Department.search([])
        
        result = {
            'departments': [],
            'total_monthly': 0,
            'total_yearly': 0,
            'over_budget_count': 0,
            'categories_by_dept': {},
        }
        
        for dept in departments:
            dept_data = {
                'id': dept.id,
                'name': dept.name,
                'code': dept.code or '',
                'manager': dept.manager_id.name if dept.manager_id else '',
                'subscription_count': dept.subscription_count,
                'total_monthly': dept.total_monthly,
                'total_yearly': dept.total_yearly,
                'budget_monthly': dept.monthly_budget,
                'budget_yearly': dept.yearly_budget,
                'budget_used_percent': dept.budget_used_percent,
                'status': 'danger' if dept.budget_used_percent > 100 else 'warning' if dept.budget_used_percent > 80 else 'success',
            }
            
            # Répartition par catégorie pour ce département
            subs = Subscription.search([
                ('department_id', '=', dept.id),
                ('state', 'in', ['active', 'validated'])
            ])
            
            categories = {'essential': 0, 'important': 0, 'optional': 0, 'to_review': 0}
            for sub in subs:
                amount = sub.amount_eur or sub.amount
                if sub.billing_cycle == 'monthly':
                    monthly = amount
                elif sub.billing_cycle == 'quarterly':
                    monthly = amount / 3
                elif sub.billing_cycle == 'yearly':
                    monthly = amount / 12
                else:
                    monthly = amount
                
                if sub.category in categories:
                    categories[sub.category] += monthly
            
            dept_data['categories'] = categories
            result['departments'].append(dept_data)
            result['total_monthly'] += dept.total_monthly
            result['total_yearly'] += dept.total_yearly
            
            if dept.budget_used_percent > 100:
                result['over_budget_count'] += 1
        
        # Trier par coût mensuel décroissant
        result['departments'].sort(key=lambda x: x['total_monthly'], reverse=True)
        
        return result
    
    # Totaux
    total_monthly = fields.Float(string='Total mensuel', compute='_compute_totals')
    total_yearly = fields.Float(string='Total annuel', compute='_compute_totals')
    subscription_count = fields.Integer(string='Nombre d\'abonnements', compute='_compute_totals')
    provider_count = fields.Integer(string='Nombre de fournisseurs', compute='_compute_totals')
    alert_count = fields.Integer(string='Alertes en cours', compute='_compute_totals')
    
    # Par cycle
    monthly_sub_count = fields.Integer(string='Abonnements mensuels', compute='_compute_totals')
    quarterly_sub_count = fields.Integer(string='Abonnements trimestriels', compute='_compute_totals')
    yearly_sub_count = fields.Integer(string='Abonnements annuels', compute='_compute_totals')
    
    # Par priorité
    essential_count = fields.Integer(string='Essentiels', compute='_compute_totals')
    essential_amount = fields.Float(string='Montant essentiels', compute='_compute_totals')
    essential_percent = fields.Float(string='% Essentiels', compute='_compute_totals')
    important_count = fields.Integer(string='Importants', compute='_compute_totals')
    important_amount = fields.Float(string='Montant importants', compute='_compute_totals')
    important_percent = fields.Float(string='% Importants', compute='_compute_totals')
    optional_count = fields.Integer(string='Optionnels', compute='_compute_totals')
    optional_amount = fields.Float(string='Montant optionnels', compute='_compute_totals')
    optional_percent = fields.Float(string='% Optionnels', compute='_compute_totals')
    to_review_count = fields.Integer(string='À revoir', compute='_compute_totals')
    to_review_amount = fields.Float(string='Montant à revoir', compute='_compute_totals')
    to_review_percent = fields.Float(string='% À revoir', compute='_compute_totals')
    
    # Top fournisseurs (texte)
    top_providers = fields.Text(string='Top fournisseurs', compute='_compute_totals')
    
    # Économies
    recommendation_count = fields.Integer(string='Recommandations', compute='_compute_totals')
    potential_savings = fields.Float(string='Économies potentielles', compute='_compute_totals')
    
    # Score FinOps
    finops_score = fields.Integer(string='Score FinOps', compute='_compute_totals')
    finops_grade = fields.Char(string='Note', compute='_compute_totals')
    score_details = fields.Text(string='Détails du score', compute='_compute_totals')
    
    # Anomalies
    anomaly_count = fields.Integer(string='Anomalies', compute='_compute_totals')
    anomaly_critical = fields.Integer(string='Anomalies critiques', compute='_compute_totals')
    anomaly_impact = fields.Float(string='Impact anomalies (€/an)', compute='_compute_totals')
    
    # Contrats
    contract_count = fields.Integer(string='Contrats', compute='_compute_totals')
    contract_expiring_count = fields.Integer(string='Contrats expirant', compute='_compute_totals')
    
    # Factures inbox
    invoice_inbox_count = fields.Integer(string='Factures inbox', compute='_compute_totals')
    invoice_unmatched_count = fields.Integer(string='Factures non associées', compute='_compute_totals')
    
    # Prévisions (résumé)
    forecast_monthly = fields.Float(string='Coût mensuel projeté', compute='_compute_totals')
    forecast_variation = fields.Float(string='Variation prévue (%)', compute='_compute_totals')
    
    # Coût par employé
    employee_count = fields.Integer(string='Nombre d\'employés', compute='_compute_totals')
    cost_per_employee_monthly = fields.Float(string='Coût/employé (mois)', compute='_compute_totals')
    cost_per_employee_yearly = fields.Float(string='Coût/employé (an)', compute='_compute_totals')
    
    # Budget
    budget_monthly = fields.Float(string='Budget mensuel', compute='_compute_totals')
    budget_yearly = fields.Float(string='Budget annuel', compute='_compute_totals')
    budget_used_percent = fields.Float(string='Budget utilisé (%)', compute='_compute_totals')
    budget_remaining = fields.Float(string='Budget restant', compute='_compute_totals')
    budget_status = fields.Char(string='Statut budget', compute='_compute_totals')
    
    # Graphiques HTML
    chart_evolution_html = fields.Html(string='Évolution', compute='_compute_charts', sanitize=False)
    chart_category_html = fields.Html(string='Par catégorie', compute='_compute_charts', sanitize=False)
    chart_top_providers_html = fields.Html(string='Top fournisseurs', compute='_compute_charts', sanitize=False)

    @api.depends_context('uid')
    def _compute_totals(self):
        Subscription = self.env['clearspend.subscription']
        Provider = self.env['clearspend.saas.provider']
        Alert = self.env['clearspend.alert']
        Recommendation = self.env['clearspend.recommendation']
        Anomaly = self.env['clearspend.anomaly']
        Contract = self.env['clearspend.contract']
        Invoice = self.env['clearspend.invoice']
        
        active_subs = Subscription.search([('state', 'in', ['active', 'validated'])])
        
        monthly_total = 0.0
        for sub in active_subs:
            # Utiliser amount_eur pour conversion multi-devise
            amount = sub.amount_eur or sub.amount
            if sub.billing_cycle == 'monthly':
                monthly_total += amount
            elif sub.billing_cycle == 'quarterly':
                monthly_total += amount / 3
            elif sub.billing_cycle == 'yearly':
                monthly_total += amount / 12
        
        alert_count = Alert.search_count([('state', 'in', ['new', 'seen'])])
        
        # Anomalies
        active_anomalies = Anomaly.search([('resolved', '=', False)])
        anomaly_count = len(active_anomalies)
        anomaly_critical = len(active_anomalies.filtered(lambda a: a.severity == 'critical'))
        anomaly_impact = sum(active_anomalies.mapped('financial_impact'))
        
        # Contrats
        from datetime import date, timedelta
        today = date.today()
        all_contracts = Contract.search([('state', 'in', ['active', 'expiring'])])
        contract_count = len(all_contracts)
        contract_expiring = Contract.search([
            ('state', 'in', ['active', 'expiring']),
            ('end_date', '>=', today),
            ('end_date', '<=', today + timedelta(days=30)),
        ])
        contract_expiring_count = len(contract_expiring)
        
        # Factures inbox
        invoice_inbox_count = Invoice.search_count([('state', '=', 'inbox')])
        invoice_unmatched_count = Invoice.search_count([
            ('state', 'in', ['inbox', 'processing']),
            ('subscription_id', '=', False),
        ])
        
        # Prévisions simplifiées (12 mois avec 3% inflation)
        inflation_rate = 0.03  # 3% annuel
        forecast_monthly = monthly_total * (1 + inflation_rate)
        forecast_variation = inflation_rate * 100 if monthly_total > 0 else 0
        
        # Par cycle
        monthly_subs = active_subs.filtered(lambda s: s.billing_cycle == 'monthly')
        quarterly_subs = active_subs.filtered(lambda s: s.billing_cycle == 'quarterly')
        yearly_subs = active_subs.filtered(lambda s: s.billing_cycle == 'yearly')
        
        # Par priorité
        essential = active_subs.filtered(lambda s: s.category == 'essential')
        important = active_subs.filtered(lambda s: s.category == 'important')
        optional = active_subs.filtered(lambda s: s.category == 'optional')
        to_review = active_subs.filtered(lambda s: s.category == 'to_review')
        
        # Top fournisseurs
        provider_totals = {}
        for sub in active_subs:
            if sub.provider_id:
                name = sub.provider_id.name
                if name not in provider_totals:
                    provider_totals[name] = 0
                provider_totals[name] += (sub.amount_eur or sub.amount)
        
        sorted_providers = sorted(provider_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        top_text = '\n'.join([f"• {name}: {amount:.2f} €" for name, amount in sorted_providers])
        
        # Économies
        new_recommendations = Recommendation.search([('state', '=', 'new')])
        recommendation_count = len(new_recommendations)
        potential_savings = sum(new_recommendations.mapped('potential_savings'))
        
        for record in self:
            record.total_monthly = monthly_total
            record.total_yearly = monthly_total * 12
            record.subscription_count = len(active_subs)
            record.provider_count = Provider.search_count([])
            record.alert_count = alert_count
            
            record.monthly_sub_count = len(monthly_subs)
            record.quarterly_sub_count = len(quarterly_subs)
            record.yearly_sub_count = len(yearly_subs)
            
            record.essential_count = len(essential)
            record.essential_amount = sum([(s.amount_eur or s.amount) for s in essential])
            record.important_count = len(important)
            record.important_amount = sum([(s.amount_eur or s.amount) for s in important])
            record.optional_count = len(optional)
            record.optional_amount = sum([(s.amount_eur or s.amount) for s in optional])
            record.to_review_count = len(to_review)
            record.to_review_amount = sum([(s.amount_eur or s.amount) for s in to_review])
            
            # Calcul des pourcentages par priorité
            total_priority_amount = record.essential_amount + record.important_amount + record.optional_amount + record.to_review_amount
            if total_priority_amount > 0:
                record.essential_percent = (record.essential_amount / total_priority_amount) * 100
                record.important_percent = (record.important_amount / total_priority_amount) * 100
                record.optional_percent = (record.optional_amount / total_priority_amount) * 100
                record.to_review_percent = (record.to_review_amount / total_priority_amount) * 100
            else:
                record.essential_percent = 0
                record.important_percent = 0
                record.optional_percent = 0
                record.to_review_percent = 0
            
            record.top_providers = top_text or 'Aucun fournisseur'
            record.recommendation_count = recommendation_count
            record.potential_savings = potential_savings
            
            # Calcul Score FinOps (0-100)
            score = 100
            details = []
            
            # -10 points par doublon détecté
            duplicate_count = Recommendation.search_count([
                ('state', '=', 'new'),
                ('recommendation_type', '=', 'duplicate')
            ])
            if duplicate_count > 0:
                penalty = min(duplicate_count * 10, 30)
                score -= penalty
                details.append(f"• Doublons détectés: -{penalty} pts")
            
            # -5 points si moins de 30% d'essentiels
            if len(active_subs) > 0:
                essential_ratio = len(essential) / len(active_subs)
                if essential_ratio < 0.3:
                    score -= 15
                    details.append(f"• Peu d'essentiels ({essential_ratio*100:.0f}%): -15 pts")
                elif essential_ratio >= 0.5:
                    score += 5
                    details.append(f"• Bon ratio essentiels ({essential_ratio*100:.0f}%): +5 pts")
            
            # -10 points si beaucoup de "à revoir"
            if len(to_review) > 2:
                score -= 10
                details.append(f"• {len(to_review)} abonnements à revoir: -10 pts")
            
            # -5 points si beaucoup de mensuels (pas optimisé)
            if len(active_subs) > 0:
                monthly_ratio = len(monthly_subs) / len(active_subs)
                if monthly_ratio > 0.7:
                    score -= 10
                    details.append(f"• Trop de mensuels ({monthly_ratio*100:.0f}%): -10 pts")
            
            # -5 points si économies potentielles > 10% du budget
            if monthly_total > 0 and potential_savings > (monthly_total * 12 * 0.1):
                score -= 10
                details.append(f"• Économies > 10% du budget: -10 pts")
            
            # Bonus si peu de recommandations
            if recommendation_count == 0:
                score += 10
                details.append("• Aucune recommandation: +10 pts")
            
            score = max(0, min(100, score))
            
            # Note lettre
            if score >= 90:
                grade = 'A'
            elif score >= 75:
                grade = 'B'
            elif score >= 60:
                grade = 'C'
            elif score >= 40:
                grade = 'D'
            else:
                grade = 'E'
            
            record.finops_score = score
            record.finops_grade = grade
            record.score_details = '\n'.join(details) if details else 'Aucun ajustement'
            
            # Coût par employé
            Config = self.env['clearspend.config']
            config = Config.get_config()
            emp_count = config.employee_count or 1
            record.employee_count = emp_count
            record.cost_per_employee_monthly = monthly_total / emp_count
            record.cost_per_employee_yearly = (monthly_total * 12) / emp_count
            
            # Budget
            budget_monthly = config.budget_monthly or 0
            budget_yearly = config.budget_yearly or 0
            record.budget_monthly = budget_monthly
            record.budget_yearly = budget_yearly
            
            if budget_monthly > 0:
                used_percent = (monthly_total / budget_monthly) * 100
                record.budget_used_percent = used_percent
                record.budget_remaining = budget_monthly - monthly_total
                
                if used_percent >= 100:
                    record.budget_status = '🔴 Dépassé'
                elif used_percent >= config.budget_alert_threshold:
                    record.budget_status = '🟠 Attention'
                elif used_percent >= 50:
                    record.budget_status = '🟡 En cours'
                else:
                    record.budget_status = '🟢 OK'
            else:
                record.budget_used_percent = 0
                record.budget_remaining = 0
                record.budget_status = '⚪ Non défini'
            
            # Anomalies
            record.anomaly_count = anomaly_count
            record.anomaly_critical = anomaly_critical
            record.anomaly_impact = anomaly_impact
            
            # Contrats
            record.contract_count = contract_count
            record.contract_expiring_count = contract_expiring_count
            
            # Factures inbox
            record.invoice_inbox_count = invoice_inbox_count
            record.invoice_unmatched_count = invoice_unmatched_count
            
            # Prévisions
            record.forecast_monthly = forecast_monthly
            record.forecast_variation = forecast_variation

    @api.depends_context('uid')
    def _compute_charts(self):
        """Génère les graphiques HTML."""
        from datetime import date
        from dateutil.relativedelta import relativedelta
        
        Subscription = self.env['clearspend.subscription']
        active_subs = Subscription.search([('state', 'in', ['active', 'validated'])])
        
        for record in self:
            # ===== Graphique évolution 6 mois =====
            today = date.today()
            months_data = []
            
            for i in range(5, -1, -1):
                month_date = today - relativedelta(months=i)
                month_label = month_date.strftime('%b')
                
                # Calcul du coût mensuel (simulation basée sur les abos actuels)
                # En production, on prendrait l'historique réel
                variation = 1 + (0.02 * (5-i))  # Légère croissance simulée
                month_total = 0.0
                for sub in active_subs:
                    amount = sub.amount_eur or sub.amount
                    if sub.billing_cycle == 'monthly':
                        month_total += amount
                    elif sub.billing_cycle == 'quarterly':
                        month_total += amount / 3
                    elif sub.billing_cycle == 'yearly':
                        month_total += amount / 12
                
                month_total = month_total / variation if i > 0 else month_total
                months_data.append({'label': month_label, 'value': month_total})
            
            max_val = max([m['value'] for m in months_data]) if months_data else 1
            
            evolution_html = '''
            <div style="display: flex; align-items: flex-end; height: 150px; gap: 8px; padding: 10px 0;">
            '''
            
            for m in months_data:
                height_pct = (m['value'] / max_val * 100) if max_val > 0 else 0
                evolution_html += f'''
                <div style="flex: 1; display: flex; flex-direction: column; align-items: center;">
                    <div style="font-size: 10px; color: #666; margin-bottom: 4px;">{m['value']:,.0f}€</div>
                    <div style="width: 100%; background: linear-gradient(180deg, #667eea 0%, #764ba2 100%); 
                                height: {height_pct}%; min-height: 5px; border-radius: 4px 4px 0 0;"></div>
                    <div style="font-size: 11px; color: #999; margin-top: 4px;">{m['label']}</div>
                </div>
                '''
            
            evolution_html += '</div>'
            record.chart_evolution_html = evolution_html
            
            # ===== Graphique par catégorie (donut simplifié) =====
            categories = [
                {'name': 'Essentiels', 'color': '#dc3545', 'count': len(active_subs.filtered(lambda s: s.category == 'essential'))},
                {'name': 'Importants', 'color': '#fd7e14', 'count': len(active_subs.filtered(lambda s: s.category == 'important'))},
                {'name': 'Optionnels', 'color': '#ffc107', 'count': len(active_subs.filtered(lambda s: s.category == 'optional'))},
                {'name': 'À revoir', 'color': '#6c757d', 'count': len(active_subs.filtered(lambda s: s.category == 'to_review'))},
            ]
            
            total_count = sum([c['count'] for c in categories]) or 1
            
            category_html = '<div style="display: flex; flex-direction: column; gap: 10px;">'
            
            for cat in categories:
                pct = (cat['count'] / total_count) * 100
                category_html += f'''
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div style="width: 12px; height: 12px; background: {cat['color']}; border-radius: 3px;"></div>
                    <div style="flex: 1; font-size: 13px;">{cat['name']}</div>
                    <div style="width: 100px; height: 8px; background: #e9ecef; border-radius: 4px; overflow: hidden;">
                        <div style="width: {pct}%; height: 100%; background: {cat['color']};"></div>
                    </div>
                    <div style="width: 40px; text-align: right; font-size: 12px; color: #666;">{cat['count']}</div>
                </div>
                '''
            
            category_html += '</div>'
            record.chart_category_html = category_html
            
            # ===== Top 5 fournisseurs =====
            provider_totals = {}
            for sub in active_subs:
                if sub.provider_id:
                    name = sub.provider_id.name
                    if name not in provider_totals:
                        provider_totals[name] = 0
                    amount = sub.amount_eur or sub.amount
                    if sub.billing_cycle == 'monthly':
                        provider_totals[name] += amount
                    elif sub.billing_cycle == 'quarterly':
                        provider_totals[name] += amount / 3
                    elif sub.billing_cycle == 'yearly':
                        provider_totals[name] += amount / 12
            
            sorted_providers = sorted(provider_totals.items(), key=lambda x: x[1], reverse=True)[:5]
            max_provider = sorted_providers[0][1] if sorted_providers else 1
            
            colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#ffecd2']
            
            providers_html = '<div style="display: flex; flex-direction: column; gap: 8px;">'
            
            for i, (name, amount) in enumerate(sorted_providers):
                pct = (amount / max_provider) * 100 if max_provider > 0 else 0
                color = colors[i % len(colors)]
                providers_html += f'''
                <div>
                    <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 2px;">
                        <span>{name[:20]}{"..." if len(name) > 20 else ""}</span>
                        <span style="color: #666;">{amount:,.0f} €/mois</span>
                    </div>
                    <div style="height: 6px; background: #e9ecef; border-radius: 3px; overflow: hidden;">
                        <div style="width: {pct}%; height: 100%; background: {color};"></div>
                    </div>
                </div>
                '''
            
            if not sorted_providers:
                providers_html += '<div style="color: #999; font-style: italic;">Aucun fournisseur</div>'
            
            providers_html += '</div>'
            record.chart_top_providers_html = providers_html

    @api.model
    def open_dashboard(self):
        """Ouvre le dashboard ou lance l'onboarding si nécessaire."""
        # Vérifier si l'onboarding est complété
        onboarding_complete = self.env['ir.config_parameter'].sudo().get_param(
            'clearspend.onboarding_complete', 'False'
        )
        
        # Vérifier aussi s'il y a des abonnements
        has_subscriptions = self.env['clearspend.subscription'].search_count([]) > 0
        
        if onboarding_complete != 'True' and not has_subscriptions:
            # Lancer l'onboarding
            wizard = self.env['clearspend.onboarding.wizard'].create({})
            return {
                'type': 'ir.actions.act_window',
                'name': '🚀 Assistant de démarrage',
                'res_model': 'clearspend.onboarding.wizard',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
            }
        
        # Sinon, ouvrir le dashboard normalement
        dashboard = self.search([], limit=1) or self.create({})
        company_name = self.env.company.name or 'ClearSpend'
        return {
            'type': 'ir.actions.act_window',
            'name': f'🎛️ {company_name}',
            'res_model': 'clearspend.dashboard',
            'view_mode': 'form',
            'res_id': dashboard.id,
            'target': 'current',
        }

    def action_open_subscriptions(self):
        """Ouvre la liste des abonnements."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Abonnements',
            'res_model': 'clearspend.subscription',
            'view_mode': 'list,form',
            'domain': [('state', 'in', ['active', 'validated'])],
            'target': 'current',
        }

    def action_open_alerts(self):
        """Ouvre les alertes à traiter."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Alertes',
            'res_model': 'clearspend.alert',
            'view_mode': 'list,form',
            'domain': [('state', 'in', ['new', 'seen'])],
            'target': 'current',
        }

    def action_open_providers(self):
        """Ouvre la liste des fournisseurs."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fournisseurs SaaS',
            'res_model': 'clearspend.saas.provider',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_essential(self):
        """Ouvre les abonnements essentiels."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Abonnements essentiels',
            'res_model': 'clearspend.subscription',
            'view_mode': 'list,form',
            'domain': [('category', '=', 'essential'), ('state', 'in', ['active', 'validated'])],
            'target': 'current',
        }

    def action_open_to_review(self):
        """Ouvre les abonnements à revoir."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Abonnements à revoir',
            'res_model': 'clearspend.subscription',
            'view_mode': 'list,form',
            'domain': [('category', '=', 'to_review'), ('state', 'in', ['active', 'validated'])],
            'target': 'current',
        }

    def action_open_recommendations(self):
        """Ouvre les recommandations d'économies."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Recommandations d\'économies',
            'res_model': 'clearspend.recommendation',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'new')],
            'target': 'current',
        }

    def action_open_anomalies(self):
        """Ouvre les anomalies détectées."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Anomalies détectées',
            'res_model': 'clearspend.anomaly',
            'view_mode': 'list,form',
            'domain': [('resolved', '=', False)],
            'target': 'current',
        }

    def action_open_contracts(self):
        """Ouvre les contrats."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Contrats',
            'res_model': 'clearspend.contract',
            'view_mode': 'list,kanban,form',
            'domain': [('state', 'in', ['active', 'expiring'])],
            'target': 'current',
        }

    def action_open_contracts_expiring(self):
        """Ouvre les contrats qui expirent bientôt."""
        from datetime import date, timedelta
        today = date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Contrats expirant',
            'res_model': 'clearspend.contract',
            'view_mode': 'list,kanban,form',
            'domain': [
                ('state', 'in', ['active', 'expiring']),
                ('end_date', '>=', today),
                ('end_date', '<=', today + timedelta(days=30)),
            ],
            'target': 'current',
        }

    def action_open_invoice_inbox(self):
        """Ouvre l'inbox factures."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Inbox Factures',
            'res_model': 'clearspend.invoice',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'inbox')],
            'target': 'current',
        }

    def action_open_invoices_unmatched(self):
        """Ouvre les factures non associées."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Factures non associées',
            'res_model': 'clearspend.invoice',
            'view_mode': 'list,form',
            'domain': [
                ('state', 'in', ['inbox', 'processing']),
                ('subscription_id', '=', False),
            ],
            'target': 'current',
        }

    def action_sync_odoo_invoices(self):
        """Synchronise les factures depuis Odoo."""
        Invoice = self.env['clearspend.invoice']
        return Invoice.action_manual_sync()

    def action_open_budgets(self):
        """Ouvre les budgets."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Budgets',
            'res_model': 'clearspend.budget',
            'view_mode': 'list,form,graph',
            'target': 'current',
        }

    def action_open_graphs(self):
        """Ouvre les graphiques d'analyse."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Analyses graphiques',
            'res_model': 'clearspend.subscription',
            'view_mode': 'graph,pivot,list',
            'domain': [('state', 'in', ['active', 'validated'])],
            'target': 'current',
        }

    def action_open_charts_interactive(self):
        """Ouvre les graphiques interactifs Chart.js."""
        return {
            'type': 'ir.actions.client',
            'tag': 'clearspend_charts',
            'name': '📊 Graphiques Interactifs',
        }

    def action_detect_anomalies(self):
        """Lance la détection des anomalies."""
        return self.env['clearspend.anomaly'].detect_all_anomalies()

    def action_open_forecast(self):
        """Ouvre les prévisions."""
        return self.env['clearspend.forecast'].open_forecast()

    @api.model
    def get_charts_data(self):
        """Retourne les données pour les graphiques Chart.js."""
        from datetime import date
        from dateutil.relativedelta import relativedelta
        
        Subscription = self.env['clearspend.subscription']
        Config = self.env['clearspend.config']
        
        active_subs = Subscription.search([('state', 'in', ['active', 'validated'])])
        config = Config.get_config()
        
        # === Calculs de base ===
        def get_monthly_cost(sub):
            amount = sub.amount_eur or sub.amount
            if sub.billing_cycle == 'monthly':
                return amount
            elif sub.billing_cycle == 'quarterly':
                return amount / 3
            elif sub.billing_cycle == 'yearly':
                return amount / 12
            return amount
        
        total_monthly = sum(get_monthly_cost(s) for s in active_subs)
        
        # === Évolution sur 6 mois ===
        today = date.today()
        evolution_labels = []
        evolution_values = []
        
        # Simulation d'évolution (en prod, on prendrait l'historique réel)
        for i in range(5, -1, -1):
            month_date = today - relativedelta(months=i)
            month_label = month_date.strftime('%b %Y')
            
            # Variation simulée basée sur l'ancienneté des abos
            variation = 1 + (0.015 * (5-i))  # Légère croissance
            month_total = total_monthly / variation if i > 0 else total_monthly
            
            evolution_labels.append(month_label)
            evolution_values.append(round(month_total, 2))
        
        # === Par catégorie (montants mensuels) ===
        categories = {
            'essential': sum(get_monthly_cost(s) for s in active_subs.filtered(lambda x: x.category == 'essential')),
            'important': sum(get_monthly_cost(s) for s in active_subs.filtered(lambda x: x.category == 'important')),
            'optional': sum(get_monthly_cost(s) for s in active_subs.filtered(lambda x: x.category == 'optional')),
            'to_review': sum(get_monthly_cost(s) for s in active_subs.filtered(lambda x: x.category == 'to_review')),
        }
        
        # === Par cycle (nombre d'abonnements) ===
        cycles = {
            'monthly': len(active_subs.filtered(lambda x: x.billing_cycle == 'monthly')),
            'quarterly': len(active_subs.filtered(lambda x: x.billing_cycle == 'quarterly')),
            'yearly': len(active_subs.filtered(lambda x: x.billing_cycle == 'yearly')),
        }
        
        # === Top 10 fournisseurs ===
        provider_costs = {}
        for sub in active_subs:
            if sub.provider_id:
                name = sub.provider_id.name
                if name not in provider_costs:
                    provider_costs[name] = 0
                provider_costs[name] += get_monthly_cost(sub)
        
        sorted_providers = sorted(provider_costs.items(), key=lambda x: -x[1])[:10]
        provider_names = [p[0] for p in sorted_providers]
        provider_values = [round(p[1], 2) for p in sorted_providers]
        
        # === Score FinOps simplifié ===
        score = 100
        essential_count = len(active_subs.filtered(lambda x: x.category == 'essential'))
        to_review_count = len(active_subs.filtered(lambda x: x.category == 'to_review'))
        
        if len(active_subs) > 0:
            if essential_count / len(active_subs) < 0.3:
                score -= 15
        if to_review_count > 2:
            score -= 10
        score = max(0, min(100, score))
        
        return {
            'kpis': {
                'total_monthly': round(total_monthly, 0),
                'total_yearly': round(total_monthly * 12, 0),
                'subscription_count': len(active_subs),
                'finops_score': score,
            },
            'evolution': {
                'labels': evolution_labels,
                'values': evolution_values,
            },
            'categories': categories,
            'cycles': cycles,
            'providers': {
                'names': provider_names,
                'values': provider_values,
            },
        }
