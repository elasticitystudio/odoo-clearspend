# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import json
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class ApiConnection(models.Model):
    _name = 'clearspend.api.connection'
    _description = 'Connexion API Fournisseur'
    _order = 'name'

    name = fields.Char(string='Nom', required=True)
    provider_type = fields.Selection([
        ('stripe', 'Stripe'),
        ('aws', 'Amazon Web Services'),
        ('gcp', 'Google Cloud Platform'),
        ('azure', 'Microsoft Azure'),
        ('digitalocean', 'DigitalOcean'),
        ('heroku', 'Heroku'),
        ('vercel', 'Vercel'),
        ('github', 'GitHub'),
        ('gitlab', 'GitLab'),
        ('slack', 'Slack'),
        ('notion', 'Notion'),
        ('custom', 'API Personnalisée'),
    ], string='Type de fournisseur', required=True, default='stripe')
    
    api_key = fields.Char(string='Clé API', help='Clé API secrète')
    api_secret = fields.Char(string='Secret API', help='Secret API (si requis)')
    api_endpoint = fields.Char(string='Endpoint personnalisé', help='URL de l\'API (pour type personnalisé)')
    
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('testing', 'Test en cours'),
        ('connected', 'Connecté'),
        ('error', 'Erreur'),
    ], string='État', default='draft')
    
    last_sync = fields.Datetime(string='Dernière synchronisation')
    last_error = fields.Text(string='Dernière erreur')
    sync_frequency = fields.Selection([
        ('manual', 'Manuelle'),
        ('daily', 'Quotidienne'),
        ('weekly', 'Hebdomadaire'),
        ('monthly', 'Mensuelle'),
    ], string='Fréquence de sync', default='manual')
    
    subscription_count = fields.Integer(string='Abonnements liés', compute='_compute_subscription_count')
    invoice_count = fields.Integer(string='Factures importées', compute='_compute_invoice_count')
    
    provider_id = fields.Many2one('clearspend.saas.provider', string='Fournisseur ClearSpend')
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    
    # Données synchronisées
    external_customer_id = fields.Char(string='ID Client externe')
    external_data = fields.Text(string='Données brutes', help='Dernières données reçues de l\'API')

    def _compute_subscription_count(self):
        for record in self:
            record.subscription_count = self.env['clearspend.subscription'].search_count([
                ('api_connection_id', '=', record.id)
            ])

    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = self.env['clearspend.invoice'].search_count([
                ('api_connection_id', '=', record.id)
            ])

    def action_test_connection(self):
        """Teste la connexion API."""
        self.ensure_one()
        self.state = 'testing'
        
        try:
            if self.provider_type == 'stripe':
                result = self._test_stripe_connection()
            elif self.provider_type == 'aws':
                result = self._test_aws_connection()
            elif self.provider_type == 'gcp':
                result = self._test_gcp_connection()
            elif self.provider_type == 'github':
                result = self._test_github_connection()
            else:
                result = self._test_generic_connection()
            
            if result.get('success'):
                self.state = 'connected'
                self.last_error = False
                self.external_customer_id = result.get('customer_id', '')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '✅ Connexion réussie',
                        'message': result.get('message', 'API connectée avec succès'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self.state = 'error'
                self.last_error = result.get('error', 'Erreur inconnue')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '❌ Échec de connexion',
                        'message': self.last_error,
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except Exception as e:
            self.state = 'error'
            self.last_error = str(e)
            _logger.exception("Erreur test connexion API %s", self.name)
            raise UserError(f"Erreur de connexion: {str(e)}")

    def _test_stripe_connection(self):
        """Test connexion Stripe."""
        if not self.api_key:
            return {'success': False, 'error': 'Clé API Stripe requise'}
        
        try:
            response = requests.get(
                'https://api.stripe.com/v1/customers',
                auth=(self.api_key, ''),
                params={'limit': 1},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                customer_id = data.get('data', [{}])[0].get('id', '') if data.get('data') else ''
                return {
                    'success': True,
                    'message': f'Stripe connecté - {len(data.get("data", []))} client(s) trouvé(s)',
                    'customer_id': customer_id
                }
            elif response.status_code == 401:
                return {'success': False, 'error': 'Clé API invalide'}
            else:
                return {'success': False, 'error': f'Erreur Stripe: {response.status_code}'}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': f'Erreur réseau: {str(e)}'}

    def _test_aws_connection(self):
        """Test connexion AWS (simulation)."""
        if not self.api_key or not self.api_secret:
            return {'success': False, 'error': 'Access Key ID et Secret Access Key requis'}
        # AWS nécessite boto3, on simule pour l'instant
        return {'success': True, 'message': 'AWS configuré (vérification complète nécessite boto3)'}

    def _test_gcp_connection(self):
        """Test connexion GCP (simulation)."""
        if not self.api_key:
            return {'success': False, 'error': 'Clé de service JSON requise'}
        return {'success': True, 'message': 'GCP configuré (vérification complète nécessite google-cloud)'}

    def _test_github_connection(self):
        """Test connexion GitHub."""
        if not self.api_key:
            return {'success': False, 'error': 'Token GitHub requis'}
        
        try:
            response = requests.get(
                'https://api.github.com/user',
                headers={'Authorization': f'token {self.api_key}'},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'message': f'GitHub connecté - Compte: {data.get("login", "?")}',
                    'customer_id': data.get('login', '')
                }
            else:
                return {'success': False, 'error': f'Erreur GitHub: {response.status_code}'}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': f'Erreur réseau: {str(e)}'}

    def _test_generic_connection(self):
        """Test connexion générique."""
        return {'success': True, 'message': 'Configuration enregistrée'}

    def action_sync_subscriptions(self):
        """Synchronise les abonnements depuis l'API."""
        self.ensure_one()
        
        if self.state != 'connected':
            raise UserError("Veuillez d'abord tester et connecter l'API")
        
        try:
            if self.provider_type == 'stripe':
                result = self._sync_stripe_subscriptions()
            else:
                result = {'created': 0, 'updated': 0, 'message': 'Sync non implémentée pour ce fournisseur'}
            
            self.last_sync = fields.Datetime.now()
            self.last_error = False
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '🔄 Synchronisation terminée',
                    'message': f"Créés: {result.get('created', 0)}, Mis à jour: {result.get('updated', 0)}",
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            self.last_error = str(e)
            _logger.exception("Erreur sync API %s", self.name)
            raise UserError(f"Erreur de synchronisation: {str(e)}")

    def _sync_stripe_subscriptions(self):
        """Synchronise les abonnements Stripe."""
        Subscription = self.env['clearspend.subscription']
        Invoice = self.env['clearspend.invoice']
        
        created = 0
        updated = 0
        
        # Récupérer les abonnements Stripe
        response = requests.get(
            'https://api.stripe.com/v1/subscriptions',
            auth=(self.api_key, ''),
            params={'limit': 100, 'status': 'all'},
            timeout=30
        )
        
        if response.status_code != 200:
            raise UserError(f"Erreur Stripe: {response.status_code}")
        
        data = response.json()
        self.external_data = json.dumps(data, indent=2)
        
        for sub_data in data.get('data', []):
            external_id = sub_data.get('id')
            
            # Chercher si l'abonnement existe déjà
            existing = Subscription.search([
                ('external_id', '=', external_id),
                ('api_connection_id', '=', self.id)
            ], limit=1)
            
            # Extraire les données
            amount = sub_data.get('items', {}).get('data', [{}])[0].get('price', {}).get('unit_amount', 0) / 100
            currency = sub_data.get('currency', 'eur').upper()
            interval = sub_data.get('items', {}).get('data', [{}])[0].get('price', {}).get('recurring', {}).get('interval', 'month')
            
            billing_cycle = 'monthly'
            if interval == 'year':
                billing_cycle = 'yearly'
            elif interval == 'week':
                billing_cycle = 'monthly'  # Approximation
            
            status = sub_data.get('status')
            state = 'active' if status == 'active' else 'cancelled' if status == 'canceled' else 'draft'
            
            # Trouver ou créer le fournisseur
            provider = self.provider_id
            if not provider:
                provider = self.env['clearspend.saas.provider'].search([('name', 'ilike', 'stripe')], limit=1)
            
            vals = {
                'name': f"Stripe - {sub_data.get('id', 'Abonnement')[:20]}",
                'amount': amount,
                'currency': currency,
                'billing_cycle': billing_cycle,
                'state': state,
                'external_id': external_id,
                'api_connection_id': self.id,
                'provider_id': provider.id if provider else False,
                'start_date': datetime.fromtimestamp(sub_data.get('start_date', 0)).date() if sub_data.get('start_date') else False,
                'notes': f"Importé depuis Stripe\nID: {external_id}\nStatut: {status}",
            }
            
            if existing:
                existing.write(vals)
                updated += 1
            else:
                Subscription.create(vals)
                created += 1
        
        # Récupérer les factures récentes
        inv_response = requests.get(
            'https://api.stripe.com/v1/invoices',
            auth=(self.api_key, ''),
            params={'limit': 50},
            timeout=30
        )
        
        if inv_response.status_code == 200:
            inv_data = inv_response.json()
            for inv in inv_data.get('data', []):
                external_inv_id = inv.get('id')
                
                existing_inv = Invoice.search([
                    ('external_id', '=', external_inv_id)
                ], limit=1)
                
                if not existing_inv:
                    # Trouver l'abonnement lié
                    sub_id = inv.get('subscription')
                    linked_sub = Subscription.search([
                        ('external_id', '=', sub_id),
                        ('api_connection_id', '=', self.id)
                    ], limit=1) if sub_id else False
                    
                    Invoice.create({
                        'name': inv.get('number') or f"Stripe-{external_inv_id[:10]}",
                        'amount': inv.get('amount_paid', 0) / 100,
                        'currency': inv.get('currency', 'eur').upper(),
                        'invoice_date': datetime.fromtimestamp(inv.get('created', 0)).date() if inv.get('created') else False,
                        'state': 'matched' if linked_sub else 'inbox',
                        'subscription_id': linked_sub.id if linked_sub else False,
                        'external_id': external_inv_id,
                        'api_connection_id': self.id,
                        'source': 'api',
                    })
        
        return {'created': created, 'updated': updated}

    def action_view_subscriptions(self):
        """Affiche les abonnements liés."""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Abonnements - {self.name}',
            'res_model': 'clearspend.subscription',
            'view_mode': 'list,form',
            'domain': [('api_connection_id', '=', self.id)],
            'context': {'default_api_connection_id': self.id},
        }

    def action_view_invoices(self):
        """Affiche les factures liées."""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Factures - {self.name}',
            'res_model': 'clearspend.invoice',
            'view_mode': 'list,form',
            'domain': [('api_connection_id', '=', self.id)],
        }

    @api.model
    def _cron_sync_all(self):
        """Cron de synchronisation automatique."""
        today = fields.Date.today()
        
        # Sync quotidienne
        daily_connections = self.search([
            ('state', '=', 'connected'),
            ('sync_frequency', '=', 'daily'),
            ('active', '=', True),
        ])
        
        # Sync hebdomadaire (lundi)
        weekly_connections = self.env['clearspend.api.connection']
        if today.weekday() == 0:
            weekly_connections = self.search([
                ('state', '=', 'connected'),
                ('sync_frequency', '=', 'weekly'),
                ('active', '=', True),
            ])
        
        # Sync mensuelle (1er du mois)
        monthly_connections = self.env['clearspend.api.connection']
        if today.day == 1:
            monthly_connections = self.search([
                ('state', '=', 'connected'),
                ('sync_frequency', '=', 'monthly'),
                ('active', '=', True),
            ])
        
        all_connections = daily_connections | weekly_connections | monthly_connections
        
        for conn in all_connections:
            try:
                conn.action_sync_subscriptions()
                _logger.info("Sync réussie pour %s", conn.name)
            except Exception as e:
                _logger.error("Erreur sync %s: %s", conn.name, str(e))
