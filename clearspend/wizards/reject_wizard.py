# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class RejectSubscriptionWizard(models.TransientModel):
    _name = 'clearspend.reject.subscription.wizard'
    _description = 'Assistant de rejet d\'abonnement'

    subscription_id = fields.Many2one('clearspend.subscription', string='Abonnement', required=True)
    rejection_reason = fields.Text(string='Motif du rejet', required=True,
                                    help="Expliquez pourquoi cette demande est rejetée.")

    def action_reject(self):
        """Rejette l'abonnement avec le motif spécifié."""
        self.ensure_one()
        
        if not self.rejection_reason:
            raise UserError("Veuillez indiquer un motif de rejet.")
        
        self.subscription_id.write({
            'rejection_reason': self.rejection_reason,
        })
        
        return self.subscription_id.action_reject()
