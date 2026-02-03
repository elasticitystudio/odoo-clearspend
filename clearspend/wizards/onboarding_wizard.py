# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date, timedelta
import random


class ClearspendOnboardingWizard(models.TransientModel):
    _name = 'clearspend.onboarding.wizard'
    _description = 'Assistant de démarrage ClearSpend'

    # Étape courante
    step = fields.Selection([
        ('welcome', '1. Bienvenue'),
        ('setup', '2. Configuration'),
        ('import_choice', '3. Vos données'),
        ('first_sub', '4. Premier abonnement'),
        ('budget', '5. Budget'),
        ('alerts', '6. Alertes'),
        ('done', '7. Terminé'),
    ], default='welcome', string='Étape')
    
    # Étape 2: Configuration entreprise
    company_name = fields.Char(string='Nom de votre entreprise', 
                                default=lambda self: self.env.company.name)
    currency_id = fields.Many2one('res.currency', string='Devise principale',
                                   default=lambda self: self.env.ref('base.EUR', raise_if_not_found=False))
    
    # Étape 3: Choix import
    import_choice = fields.Selection([
        ('demo', '🎮 Données de démonstration'),
        ('import', '📥 Importer un fichier'),
        ('manual', '✏️ Saisie manuelle'),
    ], string='Comment souhaitez-vous démarrer ?', default='demo')
    
    # Étape 4: Premier abonnement (si manuel)
    first_sub_name = fields.Char(string='Nom de l\'abonnement', 
                                  placeholder='Ex: Slack, Office 365, Adobe CC...')
    first_sub_amount = fields.Float(string='Montant')
    first_sub_cycle = fields.Selection([
        ('monthly', 'Mensuel'),
        ('quarterly', 'Trimestriel'),
        ('yearly', 'Annuel'),
    ], string='Cycle de facturation', default='monthly')
    first_sub_category = fields.Selection([
        ('essential', '🔴 Essentiel'),
        ('important', '🟠 Important'),
        ('optional', '🟡 Optionnel'),
        ('to_review', '⚪ À revoir'),
    ], string='Priorité', default='important')
    
    # Étape 5: Budget
    monthly_budget = fields.Float(string='Budget mensuel cible (€)', default=1000)
    
    # Étape 6: Alertes
    alert_renewal_days = fields.Integer(string='Alerte renouvellement (jours avant)', default=30)
    alert_budget_threshold = fields.Integer(string='Alerte budget (% du budget)', default=80)
    enable_email_alerts = fields.Boolean(string='Recevoir les alertes par email', default=True)
    
    # Compteur pour affichage
    step_number = fields.Integer(compute='_compute_step_number')
    progress_percent = fields.Integer(compute='_compute_step_number')
    
    @api.depends('step')
    def _compute_step_number(self):
        steps = ['welcome', 'setup', 'import_choice', 'first_sub', 'budget', 'alerts', 'done']
        for record in self:
            idx = steps.index(record.step) if record.step in steps else 0
            record.step_number = idx + 1
            record.progress_percent = int((idx / (len(steps) - 1)) * 100)

    def action_next(self):
        """Passer à l'étape suivante."""
        self.ensure_one()
        
        steps_flow = {
            'welcome': 'setup',
            'setup': 'import_choice',
            'import_choice': self._get_next_after_import_choice(),
            'first_sub': 'budget',
            'budget': 'alerts',
            'alerts': 'done',
        }
        
        # Exécuter les actions de l'étape courante
        if self.step == 'setup':
            self._save_company_settings()
        elif self.step == 'import_choice':
            self._process_import_choice()
        elif self.step == 'first_sub':
            self._create_first_subscription()
        elif self.step == 'budget':
            self._create_budget()
        elif self.step == 'alerts':
            self._configure_alerts()
        
        next_step = steps_flow.get(self.step, 'done')
        self.step = next_step
        
        if self.step == 'done':
            self._mark_onboarding_complete()
        
        return self._reload_wizard()
    
    def _save_company_settings(self):
        """Sauvegarde les paramètres de la société."""
        company = self.env.company
        if self.company_name and self.company_name != company.name:
            company.sudo().write({'name': self.company_name})
        if self.currency_id and self.currency_id != company.currency_id:
            company.sudo().write({'currency_id': self.currency_id.id})
    
    def _get_next_after_import_choice(self):
        """Détermine l'étape suivante selon le choix d'import."""
        if self.import_choice == 'manual':
            return 'first_sub'
        return 'budget'
    
    def action_previous(self):
        """Revenir à l'étape précédente."""
        self.ensure_one()
        
        steps_back = {
            'setup': 'welcome',
            'import_choice': 'setup',
            'first_sub': 'import_choice',
            'budget': 'first_sub' if self.import_choice == 'manual' else 'import_choice',
            'alerts': 'budget',
            'done': 'alerts',
        }
        
        self.step = steps_back.get(self.step, 'welcome')
        return self._reload_wizard()
    
    def action_skip(self):
        """Passer cette étape."""
        return self.action_next()
    
    def _reload_wizard(self):
        """Recharger le wizard."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'clearspend.onboarding.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def _process_import_choice(self):
        """Traite le choix d'import."""
        if self.import_choice == 'demo':
            self._generate_demo_data()
        elif self.import_choice == 'import':
            # Ouvrir le wizard d'import après
            pass
    
    def _generate_demo_data(self):
        """Génère des données de démonstration réalistes."""
        Subscription = self.env['clearspend.subscription']
        Provider = self.env['clearspend.saas.provider']
        
        # Données de démo réalistes
        demo_subs = [
            {'name': 'Slack Business+', 'provider': 'Slack', 'amount': 12.50, 'qty': 15, 'cycle': 'monthly', 'cat': 'essential'},
            {'name': 'Microsoft 365 Business', 'provider': 'Microsoft', 'amount': 12.50, 'qty': 20, 'cycle': 'monthly', 'cat': 'essential'},
            {'name': 'Adobe Creative Cloud', 'provider': 'Adobe', 'amount': 59.99, 'qty': 5, 'cycle': 'monthly', 'cat': 'important'},
            {'name': 'Notion Team', 'provider': 'Notion', 'amount': 8, 'qty': 15, 'cycle': 'monthly', 'cat': 'important'},
            {'name': 'Zoom Pro', 'provider': 'Zoom', 'amount': 149.90, 'qty': 1, 'cycle': 'yearly', 'cat': 'important'},
            {'name': 'GitHub Team', 'provider': 'GitHub', 'amount': 4, 'qty': 10, 'cycle': 'monthly', 'cat': 'essential'},
            {'name': 'AWS Cloud', 'provider': 'Amazon Web Services', 'amount': 450, 'qty': 1, 'cycle': 'monthly', 'cat': 'essential'},
            {'name': 'Figma Professional', 'provider': 'Figma', 'amount': 15, 'qty': 3, 'cycle': 'monthly', 'cat': 'important'},
            {'name': 'HubSpot Marketing', 'provider': 'HubSpot', 'amount': 800, 'qty': 1, 'cycle': 'monthly', 'cat': 'important'},
            {'name': 'Dropbox Business', 'provider': 'Dropbox', 'amount': 12, 'qty': 10, 'cycle': 'monthly', 'cat': 'optional'},
            {'name': 'Canva Pro', 'provider': 'Canva', 'amount': 119.99, 'qty': 1, 'cycle': 'yearly', 'cat': 'optional'},
            {'name': 'Mailchimp Standard', 'provider': 'Mailchimp', 'amount': 45, 'qty': 1, 'cycle': 'monthly', 'cat': 'to_review'},
        ]
        
        today = date.today()
        
        for sub_data in demo_subs:
            # Chercher le fournisseur
            provider = Provider.search([('name', 'ilike', sub_data['provider'])], limit=1)
            
            # Date de renouvellement aléatoire dans les 90 prochains jours
            renewal = today + timedelta(days=random.randint(5, 90))
            
            Subscription.create({
                'name': sub_data['name'],
                'provider_id': provider.id if provider else False,
                'unit_price': sub_data['amount'],
                'quantity': sub_data['qty'],
                'billing_cycle': sub_data['cycle'],
                'category': sub_data['cat'],
                'state': 'active',
                'start_date': today - timedelta(days=random.randint(30, 365)),
                'renewal_date': renewal,
                'responsible_id': self.env.user.id,
            })
        
        # Générer quelques alertes
        self.env['clearspend.alert'].generate_renewal_alerts()
        
        # Générer les recommandations
        self.env['clearspend.recommendation'].generate_recommendations()
        
        # Détecter les anomalies
        self.env['clearspend.anomaly'].detect_all_anomalies()
    
    def _create_first_subscription(self):
        """Crée le premier abonnement saisi manuellement."""
        if not self.first_sub_name or not self.first_sub_amount:
            return
        
        self.env['clearspend.subscription'].create({
            'name': self.first_sub_name,
            'unit_price': self.first_sub_amount,
            'quantity': 1,
            'billing_cycle': self.first_sub_cycle,
            'category': self.first_sub_category,
            'state': 'active',
            'start_date': date.today(),
            'responsible_id': self.env.user.id,
        })
    
    def _create_budget(self):
        """Crée le budget initial."""
        if self.monthly_budget <= 0:
            return
        
        # 1. Mettre à jour le budget dans la config (pour le cockpit)
        Config = self.env['clearspend.config']
        config = Config.search([('company_id', '=', self.env.company.id)], limit=1)
        if config:
            config.write({'budget_monthly': self.monthly_budget})
        else:
            Config.create({
                'name': f'Config {self.env.company.name}',
                'company_id': self.env.company.id,
                'budget_monthly': self.monthly_budget,
            })
        
        # 2. Créer aussi un budget mensuel pour le suivi
        Budget = self.env['clearspend.budget']
        today = date.today()
        
        existing = Budget.search([
            ('year', '=', today.year),
            ('month', '=', str(today.month)),
        ], limit=1)
        
        if existing:
            existing.write({'budget_total': self.monthly_budget})
        else:
            Budget.create({
                'year': today.year,
                'month': str(today.month),
                'budget_total': self.monthly_budget,
            })
    
    def _configure_alerts(self):
        """Configure les paramètres d'alertes."""
        Config = self.env['clearspend.config']
        
        # Utiliser la config de la société courante
        config = Config.search([('company_id', '=', self.env.company.id)], limit=1)
        if config:
            config.write({
                'renewal_alert_days': self.alert_renewal_days,
                'budget_alert_threshold': self.alert_budget_threshold,
                'enable_email_notifications': self.enable_email_alerts,
            })
        else:
            # Créer avec le budget si défini
            Config.create({
                'name': f'Config {self.env.company.name}',
                'company_id': self.env.company.id,
                'budget_monthly': self.monthly_budget,
                'renewal_alert_days': self.alert_renewal_days,
                'budget_alert_threshold': self.alert_budget_threshold,
                'enable_email_notifications': self.enable_email_alerts,
            })
    
    def _mark_onboarding_complete(self):
        """Marque l'onboarding comme terminé."""
        self.env['ir.config_parameter'].sudo().set_param(
            'clearspend.onboarding_complete', 'True'
        )
    
    def action_finish(self):
        """Terminer et aller au cockpit."""
        self._mark_onboarding_complete()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🎉 Bienvenue dans ClearSpend !',
                'message': 'Votre espace est configuré. Explorez le cockpit pour commencer.',
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'clearspend.dashboard',
                    'view_mode': 'form',
                    'target': 'current',
                }
            }
        }
    
    def action_open_import_wizard(self):
        """Ouvre le wizard d'import."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'clearspend.import.wizard',
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_go_to_cockpit(self):
        """Aller directement au cockpit."""
        self._mark_onboarding_complete()
        return self.env['clearspend.dashboard'].open_dashboard()
