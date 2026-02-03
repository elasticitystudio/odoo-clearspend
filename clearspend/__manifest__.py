# -*- coding: utf-8 -*-
{
    'name': 'ClearSpend',
    'version': '17.0.1.0.0',
    'summary': 'Gestion intelligente des abonnements SaaS & dépenses récurrentes',
    'description': '''
ClearSpend - Module FinOps pour Odoo 17
=======================================

Gérez efficacement vos abonnements SaaS et dépenses récurrentes:

🟢 MODE SIMPLE (PME)
- Dashboard épuré avec KPIs essentiels
- Gestion des abonnements
- Budget global et alertes
- Import Excel/CSV
- Rapport PDF mensuel

🔵 MODE AVANCÉ (Grandes entreprises)
- Dashboard complet avec toutes les analyses
- Workflow d'approbation (Demande → Manager → CFO)
- Intégrations API (Stripe, AWS, GitHub)
- OCR automatique des factures
- Prévisions budgétaires 3-24 mois
- Gestion des contrats
- Graphiques Chart.js interactifs
- Détection anomalies et doublons
- Recommandations d'économies

Le menu et le dashboard s'adaptent automatiquement au mode choisi !
Passez d'un mode à l'autre en un clic dans les paramètres.
    ''',
    'author': 'Rise Up Éditions',
    'website': 'https://elasticity.studio',
    'category': 'Accounting/Expenses',
    'depends': ['base', 'mail', 'web'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'wizards/import_wizard_views.xml',
        'wizards/onboarding_wizard_views.xml',
        'wizards/reject_wizard_views.xml',
        'views/department_views.xml',
        'views/saas_provider_views.xml',
        'views/subscription_views.xml',
        'views/alert_views.xml',
        'views/anomaly_views.xml',
        'views/contract_views.xml',
        'views/budget_views.xml',
        'views/invoice_views.xml',
        'views/recommendation_views.xml',
        'views/expense_history_views.xml',
        'views/forecast_views.xml',
        'views/api_connection_views.xml',
        'views/config_views.xml',
        'views/widget_views.xml',
        'views/dashboard_views.xml',
        'views/menu.xml',
        'data/saas_providers.xml',
        'data/cron.xml',
        'data/email_templates.xml',
        'report/report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'clearspend/static/src/css/clearspend.css',
            'clearspend/static/src/js/clearspend_charts.js',
            'clearspend/static/src/xml/clearspend_charts.xml',
        ],
    },
    'images': ['static/description/banner.png'],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
    'post_init_hook': '_post_init_hook',
    'external_dependencies': {
        'python': ['openpyxl', 'requests'],
    },
}
