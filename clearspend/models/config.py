# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ClearspendConfig(models.Model):
    _name = 'clearspend.config'
    _description = 'Configuration ClearSpend'

    name = fields.Char(string='Nom', default='Configuration')
    employee_count = fields.Integer(string='Nombre d\'employés', default=1)
    company_id = fields.Many2one('res.company', string='Société', 
                                  default=lambda self: self.env.company)
    
    # ==========================================
    # MODE SIMPLE / AVANCÉ
    # ==========================================
    mode = fields.Selection([
        ('simple', '🟢 Simple - PME'),
        ('advanced', '🔵 Avancé - Grandes entreprises'),
    ], string='Mode', default='simple', required=True,
       help="Mode Simple : Gestion basique des abonnements et budgets.\n"
            "Mode Avancé : Workflow d'approbation, intégrations API, OCR, prévisions.")
    
    # Fonctionnalités activables individuellement
    enable_workflow = fields.Boolean(string='Workflow d\'approbation', default=False,
                                      help="Active le circuit de validation Manager → CFO")
    enable_ocr = fields.Boolean(string='OCR Factures', default=False,
                                 help="Reconnaissance automatique des factures")
    enable_api = fields.Boolean(string='Intégrations API', default=False,
                                 help="Connexion Stripe, AWS, GitHub, etc.")
    enable_forecasts = fields.Boolean(string='Prévisions', default=False,
                                       help="Projections budgétaires 3-24 mois")
    enable_contracts = fields.Boolean(string='Gestion contrats', default=False,
                                       help="Suivi des contrats et engagements")
    enable_advanced_charts = fields.Boolean(string='Graphiques avancés', default=False,
                                             help="Graphiques Chart.js interactifs")
    
    # Nom de la société (modifiable)
    company_display_name = fields.Char(
        string='Nom affiché',
        related='company_id.name',
        readonly=False,
        help="Le nom de votre société tel qu'il apparaîtra dans ClearSpend"
    )
    
    # Budget
    budget_monthly = fields.Float(string='Budget mensuel (€)')
    budget_yearly = fields.Float(string='Budget annuel (€)', compute='_compute_budget_yearly', store=True)
    budget_alert_threshold = fields.Integer(string='Alerte si dépassement (%)', default=90,
                                             help="Alerter si les dépenses dépassent ce % du budget")
    
    # Seuil d'approbation CFO
    cfo_approval_threshold = fields.Float(string='Seuil approbation CFO (€/an)', default=1000.0,
                                           help="Montant annuel au-delà duquel l'approbation CFO est requise")
    
    # Alertes
    renewal_alert_days = fields.Integer(string='Alerte renouvellement (jours)', default=30,
                                         help="Alerter X jours avant le renouvellement")
    enable_email_notifications = fields.Boolean(string='Notifications email actives', default=True)
    
    # Devise par défaut
    default_currency_id = fields.Many2one('res.currency', string='Devise par défaut',
                                           default=lambda self: self.env.ref('base.EUR', raise_if_not_found=False))
    
    # Email
    email_recipients = fields.Char(string='Destinataires rapport mensuel',
                                    help="Emails séparés par des virgules")
    send_monthly_report = fields.Boolean(string='Envoyer rapport mensuel', default=False)
    send_alert_emails = fields.Boolean(string='Envoyer alertes par email', default=False)

    @api.onchange('mode')
    def _onchange_mode(self):
        """Active/désactive les fonctionnalités selon le mode."""
        if self.mode == 'simple':
            self.enable_workflow = False
            self.enable_ocr = False
            self.enable_api = False
            self.enable_forecasts = False
            self.enable_contracts = False
            self.enable_advanced_charts = False
        elif self.mode == 'advanced':
            self.enable_workflow = True
            self.enable_ocr = True
            self.enable_api = True
            self.enable_forecasts = True
            self.enable_contracts = True
            self.enable_advanced_charts = True

    def write(self, vals):
        """Surcharge write pour synchroniser le groupe Mode Avancé automatiquement."""
        res = super().write(vals)
        
        # Si le mode a changé, mettre à jour le groupe
        if 'mode' in vals:
            for record in self:
                record._update_advanced_mode_group(activate=(record.mode == 'advanced'))
        
        return res
    
    @api.model_create_multi
    def create(self, vals_list):
        """Surcharge create pour synchroniser le groupe Mode Avancé à la création."""
        records = super().create(vals_list)
        
        for record in records:
            record._update_advanced_mode_group(activate=(record.mode == 'advanced'))
        
        return records

    @api.depends('budget_monthly')
    def _compute_budget_yearly(self):
        for record in self:
            record.budget_yearly = record.budget_monthly * 12

    @api.model
    def get_config(self):
        """Récupère ou crée la configuration pour la société courante."""
        config = self.search([('company_id', '=', self.env.company.id)], limit=1)
        if not config:
            config = self.create({
                'name': f'Config {self.env.company.name}',
                'company_id': self.env.company.id,
            })
        return config

    @api.model
    def is_simple_mode(self):
        """Retourne True si en mode simple."""
        config = self.get_config()
        return config.mode == 'simple'

    @api.model
    def is_feature_enabled(self, feature):
        """Vérifie si une fonctionnalité est activée."""
        config = self.get_config()
        return getattr(config, f'enable_{feature}', False)

    @api.model
    def send_monthly_report_cron(self):
        """Envoi automatique du rapport mensuel (appelé par cron)."""
        configs = self.search([('send_monthly_report', '=', True)])
        for config in configs:
            config.action_send_monthly_report()

    def action_send_monthly_report(self):
        """Génère et envoie le rapport mensuel par email."""
        self.ensure_one()
        
        if not self.email_recipients:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Erreur',
                    'message': 'Veuillez configurer les destinataires du rapport.',
                    'type': 'warning',
                }
            }
        
        Subscription = self.env['clearspend.subscription']
        Alert = self.env['clearspend.alert']
        
        # Calculer les statistiques
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
        
        alert_count = Alert.search_count([('state', 'in', ['new', 'seen'])])
        
        # Renouvellements à venir
        from datetime import date, timedelta
        today = date.today()
        in_30_days = today + timedelta(days=30)
        upcoming = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('renewal_date', '>=', today),
            ('renewal_date', '<=', in_30_days),
        ])
        upcoming_list = [f"{s.name} - {s.renewal_date} ({s.amount} €)" for s in upcoming]
        
        # Budget
        budget_percent = 0
        if self.budget_monthly > 0:
            budget_percent = int((monthly_total / self.budget_monthly) * 100)
        
        # Nom du mois
        months = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        month_name = months[today.month - 1] + ' ' + str(today.year)
        
        # Envoyer l'email
        template = self.env.ref('clearspend.email_template_monthly_report', raise_if_not_found=False)
        if template:
            ctx = {
                'total_monthly': f"{monthly_total:.2f}",
                'subscription_count': len(active_subs),
                'alert_count': alert_count,
                'budget_monthly': f"{self.budget_monthly:.2f}",
                'budget_percent': budget_percent,
                'upcoming_renewals': upcoming_list,
                'month_name': month_name,
            }
            
            # Envoyer à chaque destinataire
            for email in self.email_recipients.split(','):
                email = email.strip()
                if email:
                    template.with_context(ctx).send_mail(
                        self.id, 
                        force_send=True,
                        email_values={'email_to': email}
                    )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Rapport envoyé',
                'message': f'Le rapport mensuel a été envoyé à {self.email_recipients}.',
                'type': 'success',
            }
        }

    def action_download_monthly_report(self):
        """Télécharge le rapport mensuel en PDF."""
        self.ensure_one()
        return self.env.ref('clearspend.action_report_monthly').report_action(self)

    def action_manage_users(self):
        """Ouvre la liste des utilisateurs avec les groupes ClearSpend."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Utilisateurs ClearSpend',
            'res_model': 'res.users',
            'view_mode': 'tree,form',
            'domain': [('share', '=', False)],
            'context': {
                'search_default_active': 1,
            },
        }
    
    def action_switch_to_simple(self):
        """Passe en mode simple et retire le groupe advanced_mode à tous les utilisateurs."""
        self.write({'mode': 'simple'})
        self._onchange_mode()
        self._update_advanced_mode_group(activate=False)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🟢 Mode Simple activé',
                'message': 'Interface simplifiée pour PME. Les menus avancés sont masqués.',
                'type': 'success',
            }
        }
    
    def action_switch_to_advanced(self):
        """Passe en mode avancé et assigne le groupe advanced_mode à tous les utilisateurs."""
        self.write({'mode': 'advanced'})
        self._onchange_mode()
        self._update_advanced_mode_group(activate=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🔵 Mode Avancé activé',
                'message': 'Toutes les fonctionnalités sont disponibles.',
                'type': 'success',
            }
        }
    
    def _update_advanced_mode_group(self, activate=True):
        """Assigne ou retire le groupe Mode Avancé à tous les utilisateurs internes."""
        self.ensure_one()
        group = self.env.ref('clearspend.group_advanced_mode', raise_if_not_found=False)
        if not group:
            return
        
        # Récupérer tous les utilisateurs internes (pas les portail/public)
        users = self.env['res.users'].search([
            ('share', '=', False),
            ('active', '=', True),
        ])
        
        if activate:
            # Ajouter le groupe à tous les utilisateurs
            users.write({'groups_id': [(4, group.id)]})
        else:
            # Retirer le groupe de tous les utilisateurs
            users.write({'groups_id': [(3, group.id)]})
    
    @api.model
    def _init_mode_group(self):
        """Initialise le groupe Mode Avancé selon la config actuelle (appelé à l'installation)."""
        config = self.get_config()
        config._update_advanced_mode_group(activate=(config.mode == 'advanced'))
    
    def action_sync_mode_group(self):
        """Action manuelle pour resynchroniser le groupe Mode Avancé."""
        self.ensure_one()
        self._update_advanced_mode_group(activate=(self.mode == 'advanced'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✅ Synchronisation effectuée',
                'message': f'Le groupe Mode Avancé a été {"assigné" if self.mode == "advanced" else "retiré"} à tous les utilisateurs.',
                'type': 'success',
            }
        }
