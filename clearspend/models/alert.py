# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date, timedelta

class ClearspendAlert(models.Model):
    _name = 'clearspend.alert'
    _description = 'Alerte ClearSpend'
    _order = 'priority desc, alert_date'

    name = fields.Char(string='Titre', required=True)
    subscription_id = fields.Many2one('clearspend.subscription', string='Abonnement')
    department_id = fields.Many2one('clearspend.department', string='Département')
    alert_type = fields.Selection([
        ('renewal', 'Renouvellement proche'),
        ('expiring', 'Expiration proche'),
        ('price_increase', 'Augmentation de prix'),
        ('unused', 'Peu utilisé'),
        ('duplicate', 'Doublon potentiel'),
        ('budget', 'Dépassement budget global'),
        ('budget_dept', 'Dépassement budget département'),
        ('other', 'Autre'),
    ], string='Type', default='renewal')
    alert_date = fields.Date(string='Date alerte', default=fields.Date.today)
    due_date = fields.Date(string='Échéance')
    priority = fields.Selection([
        ('0', 'Basse'),
        ('1', 'Normale'),
        ('2', 'Haute'),
        ('3', 'Urgente'),
    ], string='Priorité', default='1')
    state = fields.Selection([
        ('new', 'Nouveau'),
        ('seen', 'Vu'),
        ('done', 'Traité'),
        ('dismissed', 'Ignoré'),
    ], string='Statut', default='new')
    description = fields.Text(string='Description')
    
    # Pour les alertes budget
    budget_amount = fields.Float(string='Budget')
    current_amount = fields.Float(string='Dépenses actuelles')
    overage_percent = fields.Float(string='Dépassement %')
    
    def action_mark_seen(self):
        self.write({'state': 'seen'})
        self.update_menu_badge()
    
    def action_mark_done(self):
        self.write({'state': 'done'})
        self.update_menu_badge()
    
    def action_dismiss(self):
        self.write({'state': 'dismissed'})
        self.update_menu_badge()

    def action_view_department(self):
        """Ouvre le département concerné."""
        self.ensure_one()
        if self.department_id:
            return {
                'type': 'ir.actions.act_window',
                'name': self.department_id.name,
                'res_model': 'clearspend.department',
                'res_id': self.department_id.id,
                'view_mode': 'form',
            }

    def action_view_subscriptions(self):
        """Affiche les abonnements du département concerné."""
        self.ensure_one()
        if self.department_id:
            return {
                'type': 'ir.actions.act_window',
                'name': f'Abonnements - {self.department_id.name}',
                'res_model': 'clearspend.subscription',
                'view_mode': 'list,form',
                'domain': [('department_id', '=', self.department_id.id)],
                'context': {'search_default_filter_active': 1},
            }

    def action_send_email(self):
        """Envoie l'alerte par email au responsable."""
        template = self.env.ref('clearspend.email_template_alert_renewal', raise_if_not_found=False)
        if template:
            for record in self:
                if record.subscription_id and record.subscription_id.responsible_id.email:
                    template.send_mail(record.id, force_send=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Email envoyé',
                'message': 'L\'alerte a été envoyée par email.',
                'type': 'success',
            }
        }

    @api.model
    def generate_renewal_alerts(self):
        """Génère des alertes pour les renouvellements à venir (30 jours)."""
        Subscription = self.env['clearspend.subscription']
        today = date.today()
        in_30_days = today + timedelta(days=30)
        
        # Abonnements avec renouvellement dans les 30 jours
        subs = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('renewal_date', '>=', today),
            ('renewal_date', '<=', in_30_days),
        ])
        
        created = 0
        for sub in subs:
            # Vérifie si alerte existe déjà
            existing = self.search([
                ('subscription_id', '=', sub.id),
                ('alert_type', '=', 'renewal'),
                ('state', 'in', ['new', 'seen']),
            ])
            if not existing:
                days_left = (sub.renewal_date - today).days
                priority = '3' if days_left <= 7 else ('2' if days_left <= 14 else '1')
                self.create({
                    'name': f"Renouvellement : {sub.name}",
                    'subscription_id': sub.id,
                    'alert_type': 'renewal',
                    'due_date': sub.renewal_date,
                    'priority': priority,
                    'description': f"L'abonnement {sub.name} sera renouvelé dans {days_left} jours ({sub.renewal_date}).\nMontant : {sub.amount} € / {sub.billing_cycle}",
                })
                created += 1
        
        # Vérifier le budget global
        created += self._check_budget_alert()
        
        # Vérifier les budgets par département
        created += self._check_department_budget_alerts()
        
        # Mettre à jour le badge du menu
        self.update_menu_badge()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Alertes générées',
                'message': f'{created} nouvelle(s) alerte(s) créée(s).',
                'type': 'success',
            }
        }

    @api.model
    def _check_department_budget_alerts(self):
        """Vérifie les dépassements de budget par département."""
        Department = self.env['clearspend.department']
        departments = Department.search([('monthly_budget', '>', 0)])
        
        created = 0
        for dept in departments:
            # Recalculer les stats (force le compute)
            dept._compute_stats()
            
            # Si dépassement > 80%
            if dept.budget_used_percent >= 80:
                # Vérifier si alerte existe déjà pour ce département
                existing = self.search([
                    ('department_id', '=', dept.id),
                    ('alert_type', '=', 'budget_dept'),
                    ('state', 'in', ['new', 'seen']),
                ])
                
                if not existing:
                    if dept.budget_used_percent >= 100:
                        status = 'DÉPASSÉ'
                        priority = '3'
                        emoji = '🔴'
                    else:
                        status = 'en alerte'
                        priority = '2'
                        emoji = '🟠'
                    
                    overage = dept.total_monthly - dept.monthly_budget
                    
                    self.create({
                        'name': f"{emoji} Budget {dept.name} {status} ({dept.budget_used_percent:.0f}%)",
                        'department_id': dept.id,
                        'alert_type': 'budget_dept',
                        'priority': priority,
                        'budget_amount': dept.monthly_budget,
                        'current_amount': dept.total_monthly,
                        'overage_percent': dept.budget_used_percent,
                        'description': f"Le budget du département {dept.name} est {status}.\n\n"
                                      f"📊 Budget mensuel : {dept.monthly_budget:.2f} €\n"
                                      f"💸 Dépenses actuelles : {dept.total_monthly:.2f} €\n"
                                      f"📈 Utilisation : {dept.budget_used_percent:.0f}%\n"
                                      f"{'⚠️ Dépassement : ' + str(round(overage, 2)) + ' €' if overage > 0 else ''}\n\n"
                                      f"👥 Responsable : {dept.manager_id.name if dept.manager_id else 'Non défini'}\n"
                                      f"📦 Abonnements : {dept.subscription_count}",
                    })
                    created += 1
                elif existing and dept.budget_used_percent < 80:
                    # Fermer l'alerte si le budget est revenu à la normale
                    existing.write({'state': 'done'})
        
        return created

    @api.model
    def _check_budget_alert(self):
        """Vérifie si le budget global est dépassé et crée une alerte."""
        Config = self.env['clearspend.config']
        config = Config.get_config()
        
        if not config.budget_monthly:
            return 0
        
        Subscription = self.env['clearspend.subscription']
        active_subs = Subscription.search([('state', 'in', ['active', 'validated'])])
        
        monthly_total = 0.0
        for sub in active_subs:
            amount = sub.amount_eur or sub.amount
            if sub.billing_cycle == 'monthly':
                monthly_total += amount
            elif sub.billing_cycle == 'quarterly':
                monthly_total += amount / 3
            elif sub.billing_cycle == 'yearly':
                monthly_total += amount / 12
        
        used_percent = (monthly_total / config.budget_monthly) * 100
        
        # Vérifier si alerte existe déjà
        existing = self.search([
            ('alert_type', '=', 'budget'),
            ('state', 'in', ['new', 'seen']),
        ])
        
        if used_percent >= config.budget_alert_threshold and not existing:
            status = 'dépassé' if used_percent >= 100 else f'à {used_percent:.0f}%'
            self.create({
                'name': f"Budget global {status}",
                'alert_type': 'budget',
                'priority': '3' if used_percent >= 100 else '2',
                'budget_amount': config.budget_monthly,
                'current_amount': monthly_total,
                'overage_percent': used_percent,
                'description': f"Le budget SaaS mensuel est {status}.\n\n"
                              f"Budget : {config.budget_monthly:.2f} €\n"
                              f"Dépenses : {monthly_total:.2f} €\n"
                              f"Écart : {monthly_total - config.budget_monthly:.2f} €",
            })
            return 1
        
        return 0

    @api.model
    def cleanup_old_alerts(self):
        """Supprime les alertes traitées/ignorées de plus de 90 jours."""
        cutoff_date = date.today() - timedelta(days=90)
        old_alerts = self.search([
            ('state', 'in', ['done', 'dismissed']),
            ('alert_date', '<', cutoff_date),
        ])
        count = len(old_alerts)
        old_alerts.unlink()
        return count

    @api.model
    def update_menu_badge(self):
        """Met à jour le nom du menu avec le nombre d'alertes."""
        alert_count = self.search_count([('state', 'in', ['new', 'seen'])])
        menu = self.env.ref('clearspend.menu_alerts', raise_if_not_found=False)
        if menu:
            if alert_count > 0:
                menu.name = f"🔔 Alertes ({alert_count})"
            else:
                menu.name = "Alertes"
        return True
