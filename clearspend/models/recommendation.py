# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date

class ClearspendRecommendation(models.Model):
    _name = 'clearspend.recommendation'
    _description = 'Recommandation d\'économie'
    _order = 'potential_savings desc'

    name = fields.Char(string='Recommandation', required=True)
    recommendation_type = fields.Selection([
        ('duplicate', 'Doublon potentiel'),
        ('switch_yearly', 'Passer en annuel'),
        ('to_review', 'À revoir/supprimer'),
        ('unused', 'Peu utilisé'),
        ('renegotiate', 'Renégocier'),
        ('alternative', 'Alternative moins chère'),
    ], string='Type', required=True)
    description = fields.Text(string='Description')
    potential_savings = fields.Float(string='Économie potentielle (€/an)')
    subscription_ids = fields.Many2many('clearspend.subscription', string='Abonnements concernés')
    state = fields.Selection([
        ('new', 'Nouveau'),
        ('accepted', 'Accepté'),
        ('rejected', 'Rejeté'),
        ('done', 'Appliqué'),
    ], string='Statut', default='new')
    
    def action_accept(self):
        self.write({'state': 'accepted'})
    
    def action_reject(self):
        self.write({'state': 'rejected'})
    
    def action_done(self):
        self.write({'state': 'done'})

    @api.model
    def generate_recommendations(self):
        """Génère toutes les recommandations d'économies."""
        # Supprimer les anciennes recommandations non traitées
        self.search([('state', '=', 'new')]).unlink()
        
        created = 0
        total_savings = 0.0
        
        # 1. Détection des doublons (même catégorie de fournisseur)
        created += self._detect_duplicates()
        
        # 2. Suggestion annuel vs mensuel
        created += self._suggest_yearly_switch()
        
        # 3. Abonnements à revoir
        created += self._flag_to_review()
        
        # 4. Rappels de renégociation
        created += self._suggest_renegotiation()
        
        # 5. Alternatives moins chères
        created += self._suggest_alternatives()
        
        # Calculer le total des économies
        total_savings = sum(self.search([('state', '=', 'new')]).mapped('potential_savings'))
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Analyse terminée',
                'message': f'{created} recommandation(s) générée(s). Économies potentielles : {total_savings:.2f} €/an',
                'type': 'success',
            }
        }

    @api.model
    def _detect_duplicates(self):
        """Détecte les abonnements dans la même catégorie."""
        Subscription = self.env['clearspend.subscription']
        Provider = self.env['clearspend.saas.provider']
        
        created = 0
        active_subs = Subscription.search([('state', 'in', ['active', 'validated'])])
        
        # Grouper par catégorie de fournisseur
        category_subs = {}
        for sub in active_subs:
            if sub.provider_id and sub.provider_id.category:
                cat = sub.provider_id.category
                if cat not in category_subs:
                    category_subs[cat] = []
                category_subs[cat].append(sub)
        
        # Catégories avec labels
        cat_labels = {
            'productivity': 'Productivité',
            'communication': 'Communication',
            'marketing': 'Marketing',
            'finance': 'Finance',
            'hr': 'RH',
            'dev': 'Développement',
            'design': 'Design',
            'storage': 'Stockage',
            'security': 'Sécurité',
        }
        
        # Trouver les doublons
        for cat, subs in category_subs.items():
            if len(subs) > 1:
                # Calculer l'économie = le moins cher des outils
                amounts = [self._get_yearly_amount(s) for s in subs]
                min_amount = min(amounts)
                
                sub_names = ', '.join([s.name for s in subs])
                provider_names = ', '.join([s.provider_id.name for s in subs if s.provider_id])
                
                self.create({
                    'name': f"Doublons {cat_labels.get(cat, cat)} : {provider_names}",
                    'recommendation_type': 'duplicate',
                    'description': f"Vous avez {len(subs)} outils dans la catégorie '{cat_labels.get(cat, cat)}'.\n\n"
                                   f"Abonnements : {sub_names}\n\n"
                                   f"Envisagez de consolider sur un seul outil pour économiser.",
                    'potential_savings': min_amount,
                    'subscription_ids': [(6, 0, [s.id for s in subs])],
                })
                created += 1
        
        return created

    @api.model
    def _suggest_yearly_switch(self):
        """Suggère de passer en facturation annuelle (économie ~20%)."""
        Subscription = self.env['clearspend.subscription']
        created = 0
        
        monthly_subs = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('billing_cycle', '=', 'monthly'),
            ('amount', '>', 0),
        ])
        
        for sub in monthly_subs:
            yearly_amount = sub.amount * 12
            potential_savings = yearly_amount * 0.20  # 20% d'économie estimée
            
            if potential_savings >= 50:  # Seuil minimum 50€/an
                self.create({
                    'name': f"Passer {sub.name} en annuel",
                    'recommendation_type': 'switch_yearly',
                    'description': f"L'abonnement '{sub.name}' est facturé mensuellement ({sub.amount:.2f} €/mois).\n\n"
                                   f"Coût actuel : {yearly_amount:.2f} €/an\n"
                                   f"Coût estimé en annuel (-20%) : {yearly_amount * 0.80:.2f} €/an\n\n"
                                   f"La plupart des éditeurs SaaS offrent ~20% de réduction pour un engagement annuel.",
                    'potential_savings': potential_savings,
                    'subscription_ids': [(6, 0, [sub.id])],
                })
                created += 1
        
        return created

    @api.model
    def _flag_to_review(self):
        """Met en avant les abonnements marqués 'à revoir' ou 'optionnel'."""
        Subscription = self.env['clearspend.subscription']
        created = 0
        
        # Abonnements à revoir
        to_review = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('category', '=', 'to_review'),
        ])
        
        if to_review:
            total = sum([self._get_yearly_amount(s) for s in to_review])
            names = ', '.join([s.name for s in to_review])
            
            self.create({
                'name': f"{len(to_review)} abonnement(s) à revoir",
                'recommendation_type': 'to_review',
                'description': f"Ces abonnements sont marqués 'À revoir' :\n\n{names}\n\n"
                               f"Vérifiez s'ils sont encore nécessaires. "
                               f"Si vous les résiliez, vous économisez {total:.2f} €/an.",
                'potential_savings': total,
                'subscription_ids': [(6, 0, to_review.ids)],
            })
            created += 1
        
        # Abonnements optionnels
        optional = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('category', '=', 'optional'),
        ])
        
        if optional:
            total = sum([self._get_yearly_amount(s) for s in optional])
            names = ', '.join([s.name for s in optional])
            
            self.create({
                'name': f"{len(optional)} abonnement(s) optionnel(s)",
                'recommendation_type': 'to_review',
                'description': f"Ces abonnements sont marqués 'Optionnel' :\n\n{names}\n\n"
                               f"Réduire les outils optionnels peut économiser {total:.2f} €/an.",
                'potential_savings': total * 0.5,  # 50% car pas tout supprimer
                'subscription_ids': [(6, 0, optional.ids)],
            })
            created += 1
        
        return created

    @api.model
    def _suggest_renegotiation(self):
        """Suggère de renégocier les gros contrats annuels."""
        Subscription = self.env['clearspend.subscription']
        created = 0
        
        big_yearly = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('billing_cycle', '=', 'yearly'),
            ('amount', '>=', 1000),  # Plus de 1000€/an
        ])
        
        for sub in big_yearly:
            potential_savings = sub.amount * 0.10  # 10% de négociation possible
            
            self.create({
                'name': f"Renégocier {sub.name}",
                'recommendation_type': 'renegotiate',
                'description': f"L'abonnement '{sub.name}' coûte {sub.amount:.2f} €/an.\n\n"
                               f"Pour les contrats > 1000€, il est souvent possible de négocier 10-15% de réduction.\n\n"
                               f"Contactez votre commercial avant le renouvellement "
                               f"({sub.renewal_date or 'date non renseignée'}).",
                'potential_savings': potential_savings,
                'subscription_ids': [(6, 0, [sub.id])],
            })
            created += 1
        
        return created

    def _get_yearly_amount(self, sub):
        """Calcule le montant annuel d'un abonnement."""
        if sub.billing_cycle == 'monthly':
            return sub.amount * 12
        elif sub.billing_cycle == 'quarterly':
            return sub.amount * 4
        else:  # yearly
            return sub.amount

    @api.model
    def _suggest_alternatives(self):
        """Suggère des alternatives moins chères basées sur les fournisseurs."""
        Subscription = self.env['clearspend.subscription']
        created = 0
        
        active_subs = Subscription.search([
            ('state', 'in', ['active', 'validated']),
            ('provider_id', '!=', False),
        ])
        
        for sub in active_subs:
            provider = sub.provider_id
            
            # Vérifie si le fournisseur a des alternatives moins chères
            if provider.alternative_ids and provider.avg_price_monthly:
                for alt in provider.alternative_ids:
                    if alt.avg_price_monthly and alt.avg_price_monthly < provider.avg_price_monthly:
                        # Calculer l'économie potentielle
                        current_price = provider.avg_price_monthly
                        alt_price = alt.avg_price_monthly
                        diff_percent = ((current_price - alt_price) / current_price) * 100
                        
                        # Estimation sur base du montant actuel
                        yearly_current = self._get_yearly_amount(sub)
                        potential_savings = yearly_current * (diff_percent / 100)
                        
                        if potential_savings >= 50:  # Seuil minimum
                            self.create({
                                'name': f"Alternative à {provider.name} : {alt.name}",
                                'recommendation_type': 'alternative',
                                'description': f"Pour '{sub.name}' ({provider.name}), envisagez {alt.name}.\n\n"
                                               f"Prix moyen {provider.name} : {current_price:.2f} €/utilisateur/mois\n"
                                               f"Prix moyen {alt.name} : {alt_price:.2f} €/utilisateur/mois\n"
                                               f"Économie estimée : ~{diff_percent:.0f}%\n\n"
                                               f"Site web : {alt.website or 'Non renseigné'}",
                                'potential_savings': potential_savings,
                                'subscription_ids': [(6, 0, [sub.id])],
                            })
                            created += 1
                            break  # Une seule alternative par abonnement
        
        return created
