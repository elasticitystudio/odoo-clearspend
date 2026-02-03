# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date, timedelta

class ClearspendAnomaly(models.Model):
    _name = 'clearspend.anomaly'
    _description = 'Anomalie détectée'
    _order = 'severity desc, detected_on desc'

    name = fields.Char(string='Anomalie', required=True)
    anomaly_type = fields.Selection([
        ('duplicate', 'Doublon détecté'),
        ('price_increase', 'Hausse de prix'),
        ('no_renewal', 'Pas de date renouvellement'),
        ('budget_overrun', 'Dépassement budget'),
        ('unused_licenses', 'Licences inutilisées'),
        ('long_inactive', 'Inactif depuis longtemps'),
        ('missing_responsible', 'Pas de responsable'),
        ('expensive_monthly', 'Mensuel coûteux'),
        ('other', 'Autre'),
    ], string='Type', required=True)
    
    severity = fields.Selection([
        ('low', '🟢 Faible'),
        ('medium', '🟡 Moyenne'),
        ('high', '🟠 Haute'),
        ('critical', '🔴 Critique'),
    ], string='Sévérité', default='medium')
    
    description = fields.Text(string='Description')
    subscription_id = fields.Many2one('clearspend.subscription', string='Abonnement concerné')
    subscription_ids = fields.Many2many('clearspend.subscription', string='Abonnements concernés')
    
    detected_on = fields.Date(string='Détecté le', default=fields.Date.today)
    resolved = fields.Boolean(string='Résolu', default=False)
    resolved_on = fields.Date(string='Résolu le')
    resolved_by = fields.Many2one('res.users', string='Résolu par')
    resolution_note = fields.Text(string='Note de résolution')
    
    # Impact financier
    financial_impact = fields.Float(string='Impact financier (€/an)', 
                                     help="Coût potentiel ou économie possible")
    
    state = fields.Selection([
        ('new', 'Nouveau'),
        ('investigating', 'En cours'),
        ('resolved', 'Résolu'),
        ('ignored', 'Ignoré'),
    ], string='Statut', default='new')

    def action_investigate(self):
        self.write({'state': 'investigating'})

    def action_resolve(self):
        self.write({
            'state': 'resolved',
            'resolved': True,
            'resolved_on': fields.Date.today(),
            'resolved_by': self.env.user.id,
        })

    def action_ignore(self):
        self.write({'state': 'ignored', 'resolved': True})

    def action_open_subscription(self):
        """Ouvre l'abonnement concerné."""
        self.ensure_one()
        if self.subscription_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'clearspend.subscription',
                'res_id': self.subscription_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    # =============================================
    # DÉTECTION AUTOMATIQUE DES ANOMALIES
    # =============================================
    
    @api.model
    def detect_all_anomalies(self):
        """Lance toutes les détections d'anomalies."""
        # Archiver les anciennes anomalies non résolues (optionnel)
        # self.search([('state', '=', 'new'), ('detected_on', '<', fields.Date.today() - timedelta(days=30))]).write({'state': 'ignored'})
        
        created = 0
        created += self._detect_duplicates()
        created += self._detect_price_increases()
        created += self._detect_no_renewal()
        created += self._detect_budget_overrun()
        created += self._detect_missing_responsible()
        created += self._detect_expensive_monthly()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🔍 Détection terminée',
                'message': f'{created} anomalie(s) détectée(s).',
                'type': 'success' if created == 0 else 'warning',
            }
        }

    @api.model
    def _detect_duplicates(self):
        """Détecte les abonnements en doublon (même fournisseur)."""
        Subscription = self.env['clearspend.subscription']
        created = 0
        
        # Grouper par fournisseur
        active_subs = Subscription.search([('state', 'in', ['active', 'validated'])])
        provider_subs = {}
        
        for sub in active_subs:
            if sub.provider_id:
                pid = sub.provider_id.id
                if pid not in provider_subs:
                    provider_subs[pid] = []
                provider_subs[pid].append(sub)
        
        for pid, subs in provider_subs.items():
            if len(subs) > 1:
                # Vérifier si anomalie existe déjà
                existing = self.search([
                    ('anomaly_type', '=', 'duplicate'),
                    ('subscription_id', 'in', [s.id for s in subs]),
                    ('resolved', '=', False),
                ])
                if not existing:
                    provider_name = subs[0].provider_id.name
                    total_cost = sum([s.amount for s in subs])
                    sub_names = ', '.join([s.name for s in subs])
                    
                    self.create({
                        'name': f"Doublons {provider_name}",
                        'anomaly_type': 'duplicate',
                        'severity': 'high' if total_cost > 500 else 'medium',
                        'description': f"Vous avez {len(subs)} abonnements chez {provider_name}:\n\n"
                                       f"{sub_names}\n\n"
                                       f"Coût total: {total_cost:.2f} €\n"
                                       f"Envisagez de consolider ces abonnements.",
                        'subscription_id': subs[0].id,
                        'subscription_ids': [(6, 0, [s.id for s in subs])],
                        'financial_impact': min([s.amount for s in subs]) * 12,
                    })
                    created += 1
        
        return created

    @api.model
    def _detect_price_increases(self):
        """Détecte les hausses de prix significatives."""
        History = self.env['clearspend.expense.history']
        created = 0
        
        # Comparer les 2 derniers mois
        today = date.today()
        last_month = today.replace(day=1) - timedelta(days=1)
        prev_month = last_month.replace(day=1) - timedelta(days=1)
        
        current = History.search([
            ('date', '>=', last_month.replace(day=1)),
            ('date', '<=', last_month),
        ], limit=1)
        
        previous = History.search([
            ('date', '>=', prev_month.replace(day=1)),
            ('date', '<=', prev_month),
        ], limit=1)
        
        if current and previous and previous.total_monthly > 0:
            increase_pct = ((current.total_monthly - previous.total_monthly) / previous.total_monthly) * 100
            
            if increase_pct >= 10:  # Hausse de 10% ou plus
                existing = self.search([
                    ('anomaly_type', '=', 'price_increase'),
                    ('resolved', '=', False),
                    ('detected_on', '>=', today - timedelta(days=30)),
                ])
                if not existing:
                    self.create({
                        'name': f"Hausse des coûts de {increase_pct:.0f}%",
                        'anomaly_type': 'price_increase',
                        'severity': 'critical' if increase_pct >= 25 else 'high',
                        'description': f"Vos dépenses SaaS ont augmenté de {increase_pct:.1f}% ce mois.\n\n"
                                       f"Mois précédent: {previous.total_monthly:.2f} €\n"
                                       f"Ce mois: {current.total_monthly:.2f} €\n"
                                       f"Différence: +{current.total_monthly - previous.total_monthly:.2f} €\n\n"
                                       f"Vérifiez les nouveaux abonnements ou les augmentations de tarifs.",
                        'financial_impact': (current.total_monthly - previous.total_monthly) * 12,
                    })
                    created += 1
        
        return created

    @api.model
    def _detect_no_renewal(self):
        """Détecte les abonnements sans date de renouvellement."""
        Subscription = self.env['clearspend.subscription']
        created = 0
        
        no_renewal = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('renewal_date', '=', False),
            ('amount', '>', 0),
        ])
        
        for sub in no_renewal:
            existing = self.search([
                ('anomaly_type', '=', 'no_renewal'),
                ('subscription_id', '=', sub.id),
                ('resolved', '=', False),
            ])
            if not existing:
                self.create({
                    'name': f"Pas de renouvellement: {sub.name}",
                    'anomaly_type': 'no_renewal',
                    'severity': 'low',
                    'description': f"L'abonnement '{sub.name}' n'a pas de date de renouvellement définie.\n\n"
                                   f"Sans cette date, vous risquez d'être renouvelé automatiquement "
                                   f"sans pouvoir renégocier ou résilier à temps.",
                    'subscription_id': sub.id,
                })
                created += 1
        
        return created

    @api.model
    def _detect_budget_overrun(self):
        """Détecte le dépassement de budget."""
        Config = self.env['clearspend.config']
        Subscription = self.env['clearspend.subscription']
        created = 0
        
        config = Config.get_config()
        if not config.budget_monthly:
            return 0
        
        # Calculer dépenses actuelles
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
        
        if monthly_total > config.budget_monthly:
            existing = self.search([
                ('anomaly_type', '=', 'budget_overrun'),
                ('resolved', '=', False),
            ])
            if not existing:
                overrun = monthly_total - config.budget_monthly
                overrun_pct = (overrun / config.budget_monthly) * 100
                
                self.create({
                    'name': f"Budget dépassé de {overrun_pct:.0f}%",
                    'anomaly_type': 'budget_overrun',
                    'severity': 'critical',
                    'description': f"Votre budget SaaS mensuel est dépassé!\n\n"
                                   f"Budget: {config.budget_monthly:.2f} €\n"
                                   f"Dépenses: {monthly_total:.2f} €\n"
                                   f"Dépassement: +{overrun:.2f} € (+{overrun_pct:.1f}%)\n\n"
                                   f"Revoyez vos abonnements optionnels ou à revoir.",
                    'financial_impact': overrun * 12,
                })
                created += 1
        
        return created

    @api.model
    def _detect_missing_responsible(self):
        """Détecte les abonnements sans responsable."""
        Subscription = self.env['clearspend.subscription']
        created = 0
        
        no_responsible = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('responsible_id', '=', False),
            ('amount', '>=', 50),  # Seulement ceux > 50€
        ])
        
        if no_responsible:
            existing = self.search([
                ('anomaly_type', '=', 'missing_responsible'),
                ('resolved', '=', False),
            ])
            if not existing:
                names = ', '.join([s.name for s in no_responsible[:5]])
                if len(no_responsible) > 5:
                    names += f" et {len(no_responsible) - 5} autres"
                
                self.create({
                    'name': f"{len(no_responsible)} abonnement(s) sans responsable",
                    'anomaly_type': 'missing_responsible',
                    'severity': 'medium',
                    'description': f"Ces abonnements n'ont pas de responsable assigné:\n\n"
                                   f"{names}\n\n"
                                   f"Assignez un responsable pour un meilleur suivi.",
                    'subscription_ids': [(6, 0, no_responsible.ids)],
                })
                created += 1
        
        return created

    @api.model
    def _detect_expensive_monthly(self):
        """Détecte les abonnements mensuels coûteux (suggérer annuel)."""
        Subscription = self.env['clearspend.subscription']
        created = 0
        
        expensive = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('billing_cycle', '=', 'monthly'),
            ('amount', '>=', 100),  # Plus de 100€/mois
        ])
        
        for sub in expensive:
            existing = self.search([
                ('anomaly_type', '=', 'expensive_monthly'),
                ('subscription_id', '=', sub.id),
                ('resolved', '=', False),
            ])
            if not existing:
                yearly_cost = sub.amount * 12
                potential_savings = yearly_cost * 0.20  # 20% économie estimée
                
                self.create({
                    'name': f"Mensuel coûteux: {sub.name}",
                    'anomaly_type': 'expensive_monthly',
                    'severity': 'medium',
                    'description': f"L'abonnement '{sub.name}' coûte {sub.amount:.2f} €/mois "
                                   f"({yearly_cost:.2f} €/an).\n\n"
                                   f"En passant en facturation annuelle, vous pourriez économiser "
                                   f"environ {potential_savings:.2f} €/an (20% de réduction estimée).",
                    'subscription_id': sub.id,
                    'financial_impact': potential_savings,
                })
                created += 1
        
        return created
