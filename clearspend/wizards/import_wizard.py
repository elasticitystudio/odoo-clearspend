# -*- coding: utf-8 -*-
import base64
import csv
import io
import re
from odoo import models, fields, api
from odoo.exceptions import UserError

class ClearspendImportWizard(models.TransientModel):
    _name = 'clearspend.import.wizard'
    _description = 'Import Excel/CSV Abonnements'

    # Étape 1: Upload
    file = fields.Binary(string='Fichier', required=True)
    filename = fields.Char(string='Nom du fichier')
    
    # État du wizard
    state = fields.Selection([
        ('upload', 'Upload'),
        ('mapping', 'Mapping'),
        ('preview', 'Prévisualisation'),
        ('done', 'Terminé'),
    ], default='upload')
    
    # Mapping des colonnes (détecté automatiquement, modifiable)
    col_name = fields.Char(string='Colonne Nom')
    col_provider = fields.Char(string='Colonne Fournisseur')
    col_price = fields.Char(string='Colonne Prix')
    col_quantity = fields.Char(string='Colonne Quantité')
    col_cycle = fields.Char(string='Colonne Cycle')
    col_category = fields.Char(string='Colonne Priorité')
    col_department = fields.Char(string='Colonne Département')
    col_renewal = fields.Char(string='Colonne Renouvellement')
    col_notes = fields.Char(string='Colonne Notes')
    
    # Colonnes détectées
    detected_columns = fields.Text(string='Colonnes détectées')
    
    # Prévisualisation
    preview_html = fields.Html(string='Aperçu', readonly=True)
    preview_count = fields.Integer(string='Lignes à importer')
    
    # Résultat
    result_message = fields.Html(string='Résultat', readonly=True)
    
    # Données parsées (stockées temporairement)
    parsed_data = fields.Text(string='Données parsées')

    # Mapping intelligent des noms de colonnes
    COLUMN_PATTERNS = {
        'name': ['nom', 'name', 'titre', 'title', 'abonnement', 'subscription', 'service', 'outil', 'tool', 'logiciel', 'software'],
        'provider': ['fournisseur', 'provider', 'vendor', 'editeur', 'éditeur', 'marque', 'brand'],
        'price': ['prix', 'price', 'cout', 'coût', 'cost', 'montant', 'amount', 'tarif', 'prix_unitaire', 'unit_price'],
        'quantity': ['quantite', 'quantité', 'quantity', 'qty', 'nb', 'nombre', 'licences', 'licenses', 'users', 'utilisateurs', 'seats'],
        'cycle': ['cycle', 'frequence', 'fréquence', 'frequency', 'billing', 'facturation', 'periode', 'période', 'period'],
        'category': ['priorite', 'priorité', 'priority', 'categorie', 'catégorie', 'category', 'importance', 'criticite', 'criticité'],
        'department': ['departement', 'département', 'department', 'dept', 'service', 'equipe', 'équipe', 'team', 'bu', 'business_unit'],
        'renewal': ['renouvellement', 'renewal', 'echeance', 'échéance', 'expiration', 'date_fin', 'end_date', 'next_billing'],
        'notes': ['notes', 'note', 'commentaire', 'commentaires', 'comment', 'comments', 'description', 'remarque', 'remarques'],
    }

    def _parse_file(self):
        """Parse le fichier uploadé (CSV ou Excel)."""
        if not self.file:
            raise UserError("Veuillez sélectionner un fichier.")
        
        file_content = base64.b64decode(self.file)
        filename = (self.filename or '').lower()
        
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            return self._parse_excel(file_content)
        else:
            return self._parse_csv(file_content)
    
    def _parse_excel(self, file_content):
        """Parse un fichier Excel."""
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
            ws = wb.active
            
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                raise UserError("Le fichier Excel est vide.")
            
            # Première ligne = en-têtes
            headers = [str(h).strip().lower() if h else f'col_{i}' for i, h in enumerate(rows[0])]
            
            # Données
            data = []
            for row in rows[1:]:
                if any(cell for cell in row):  # Ignorer lignes vides
                    row_dict = {}
                    for i, cell in enumerate(row):
                        if i < len(headers):
                            row_dict[headers[i]] = str(cell).strip() if cell else ''
                    data.append(row_dict)
            
            return headers, data
            
        except ImportError:
            raise UserError("Le module 'openpyxl' n'est pas installé. Utilisez un fichier CSV ou installez openpyxl.")
        except Exception as e:
            raise UserError(f"Erreur lors de la lecture du fichier Excel: {str(e)}")
    
    def _parse_csv(self, file_content):
        """Parse un fichier CSV."""
        # Détecter l'encodage
        try:
            csv_text = file_content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                csv_text = file_content.decode('latin-1')
            except:
                csv_text = file_content.decode('utf-8', errors='ignore')
        
        # Détecter le délimiteur
        first_line = csv_text.split('\n')[0]
        delimiter = ';' if first_line.count(';') > first_line.count(',') else ','
        
        reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
        headers = [h.strip().lower() for h in reader.fieldnames] if reader.fieldnames else []
        data = [row for row in reader]
        
        return headers, data
    
    def _auto_map_columns(self, headers):
        """Mappe automatiquement les colonnes détectées."""
        mapping = {}
        headers_lower = [h.lower().strip() for h in headers]
        
        for field, patterns in self.COLUMN_PATTERNS.items():
            for pattern in patterns:
                for header in headers_lower:
                    # Match exact ou partiel
                    if pattern == header or pattern in header or header in pattern:
                        mapping[field] = headers[headers_lower.index(header)]
                        break
                if field in mapping:
                    break
        
        return mapping

    def action_analyze(self):
        """Analyse le fichier et propose un mapping."""
        headers, data = self._parse_file()
        
        if not headers:
            raise UserError("Impossible de détecter les colonnes du fichier.")
        
        # Auto-mapping
        mapping = self._auto_map_columns(headers)
        
        # Stocker les données parsées
        import json
        self.parsed_data = json.dumps(data, ensure_ascii=False)
        self.detected_columns = ', '.join(headers)
        
        # Appliquer le mapping détecté
        self.col_name = mapping.get('name', '')
        self.col_provider = mapping.get('provider', '')
        self.col_price = mapping.get('price', '')
        self.col_quantity = mapping.get('quantity', '')
        self.col_cycle = mapping.get('cycle', '')
        self.col_category = mapping.get('category', '')
        self.col_department = mapping.get('department', '')
        self.col_renewal = mapping.get('renewal', '')
        self.col_notes = mapping.get('notes', '')
        
        self.preview_count = len(data)
        self.state = 'mapping'
        
        return self._reload_wizard()
    
    def action_preview(self):
        """Génère une prévisualisation des données."""
        import json
        data = json.loads(self.parsed_data or '[]')
        
        if not data:
            raise UserError("Aucune donnée à importer.")
        
        # Générer le HTML de prévisualisation
        html = '''
        <div style="max-height: 400px; overflow-y: auto;">
        <table class="table table-sm table-striped" style="font-size: 0.85em;">
        <thead style="position: sticky; top: 0; background: #f8f9fa;">
            <tr>
                <th>#</th>
                <th>Nom</th>
                <th>Fournisseur</th>
                <th>Prix</th>
                <th>Qté</th>
                <th>Cycle</th>
                <th>Priorité</th>
            </tr>
        </thead>
        <tbody>
        '''
        
        for i, row in enumerate(data[:20], 1):
            name = self._get_value(row, self.col_name) or f'Ligne {i}'
            provider = self._get_value(row, self.col_provider) or '-'
            price = self._get_value(row, self.col_price) or '0'
            qty = self._get_value(row, self.col_quantity) or '1'
            cycle = self._get_value(row, self.col_cycle) or '-'
            category = self._get_value(row, self.col_category) or '-'
            
            html += f'''
            <tr>
                <td>{i}</td>
                <td><strong>{name}</strong></td>
                <td>{provider}</td>
                <td>{price} €</td>
                <td>{qty}</td>
                <td>{cycle}</td>
                <td>{category}</td>
            </tr>
            '''
        
        if len(data) > 20:
            html += f'<tr><td colspan="7" class="text-center text-muted">... et {len(data) - 20} autres lignes</td></tr>'
        
        html += '</tbody></table></div>'
        
        self.preview_html = html
        self.state = 'preview'
        
        return self._reload_wizard()
    
    def _get_value(self, row, col_name):
        """Récupère une valeur d'une ligne selon le nom de colonne."""
        if not col_name:
            return None
        col_lower = col_name.lower().strip()
        for key in row:
            if key.lower().strip() == col_lower:
                return row[key]
        return row.get(col_name, row.get(col_lower))

    def action_import(self):
        """Importe les abonnements."""
        import json
        data = json.loads(self.parsed_data or '[]')
        
        if not data:
            raise UserError("Aucune donnée à importer.")
        
        Subscription = self.env['clearspend.subscription']
        Provider = self.env['clearspend.saas.provider']
        
        created = 0
        errors = []
        
        for i, row in enumerate(data, 1):
            try:
                # Récupérer les valeurs
                name = self._get_value(row, self.col_name)
                if not name:
                    name = f'Import ligne {i}'
                
                # Fournisseur
                provider_id = False
                provider_name = self._get_value(row, self.col_provider)
                if provider_name:
                    provider = Provider.search([('name', 'ilike', provider_name)], limit=1)
                    if not provider:
                        provider = Provider.create({'name': provider_name})
                    provider_id = provider.id
                
                # Prix
                price_str = self._get_value(row, self.col_price) or '0'
                price = self._parse_number(price_str)
                
                # Quantité
                qty_str = self._get_value(row, self.col_quantity) or '1'
                quantity = int(self._parse_number(qty_str)) or 1
                
                # Cycle
                cycle_raw = (self._get_value(row, self.col_cycle) or 'monthly').lower()
                billing_cycle = self._map_cycle(cycle_raw)
                
                # Catégorie
                cat_raw = (self._get_value(row, self.col_category) or 'important').lower()
                category = self._map_category(cat_raw)
                
                # Créer l'abonnement
                vals = {
                    'name': name.strip(),
                    'provider_id': provider_id,
                    'unit_price': price,
                    'quantity': quantity,
                    'billing_cycle': billing_cycle,
                    'category': category,
                    'department': (self._get_value(row, self.col_department) or '').strip(),
                    'notes': (self._get_value(row, self.col_notes) or '').strip(),
                    'state': 'draft',
                }
                
                # Date de renouvellement
                renewal = self._get_value(row, self.col_renewal)
                if renewal:
                    parsed_date = self._parse_date(renewal)
                    if parsed_date:
                        vals['renewal_date'] = parsed_date
                
                Subscription.create(vals)
                created += 1
                
            except Exception as e:
                errors.append(f"Ligne {i}: {str(e)}")
        
        # Résultat
        html = f'''
        <div class="text-center p-4">
            <h2 style="color: #28a745;">✅ Import terminé</h2>
            <p style="font-size: 1.5em;"><strong>{created}</strong> abonnement(s) créé(s)</p>
        '''
        
        if errors:
            html += f'''
            <div class="alert alert-warning mt-3" style="text-align: left;">
                <strong>⚠️ {len(errors)} erreur(s):</strong><br/>
                {'<br/>'.join(errors[:5])}
                {'<br/>...' if len(errors) > 5 else ''}
            </div>
            '''
        
        html += '''
            <a href="/web#action=clearspend.action_subscription" class="btn btn-primary mt-3">
                Voir les abonnements
            </a>
        </div>
        '''
        
        self.result_message = html
        self.state = 'done'
        
        return self._reload_wizard()
    
    def _parse_number(self, value):
        """Parse un nombre depuis une string."""
        if not value:
            return 0.0
        # Nettoyer la valeur
        cleaned = re.sub(r'[^\d.,\-]', '', str(value))
        # Gérer les formats FR (1 234,56) et EN (1,234.56)
        if ',' in cleaned and '.' in cleaned:
            if cleaned.rfind(',') > cleaned.rfind('.'):
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                cleaned = cleaned.replace(',', '')
        elif ',' in cleaned:
            cleaned = cleaned.replace(',', '.')
        
        try:
            return float(cleaned)
        except:
            return 0.0
    
    def _parse_date(self, value):
        """Parse une date depuis différents formats."""
        if not value:
            return None
        
        import re
        from datetime import datetime
        
        value = str(value).strip()
        
        # Formats courants
        formats = [
            '%Y-%m-%d',      # 2026-01-21
            '%d/%m/%Y',      # 21/01/2026
            '%d-%m-%Y',      # 21-01-2026
            '%d.%m.%Y',      # 21.01.2026
            '%Y/%m/%d',      # 2026/01/21
            '%m/%d/%Y',      # 01/21/2026 (US)
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt).date()
            except:
                continue
        
        return None
    
    def _map_cycle(self, value):
        """Mappe un cycle de facturation."""
        value = value.lower().strip()
        mapping = {
            'mensuel': 'monthly', 'monthly': 'monthly', 'mois': 'monthly', 'month': 'monthly', 'm': 'monthly',
            'trimestriel': 'quarterly', 'quarterly': 'quarterly', 'trimestre': 'quarterly', 'quarter': 'quarterly', 'q': 'quarterly', '3 mois': 'quarterly',
            'annuel': 'yearly', 'yearly': 'yearly', 'annual': 'yearly', 'an': 'yearly', 'year': 'yearly', 'y': 'yearly', '12 mois': 'yearly',
        }
        return mapping.get(value, 'monthly')
    
    def _map_category(self, value):
        """Mappe une catégorie/priorité."""
        value = value.lower().strip()
        mapping = {
            'essentiel': 'essential', 'essential': 'essential', 'critique': 'essential', 'critical': 'essential', 'obligatoire': 'essential', '1': 'essential', 'high': 'essential',
            'important': 'important', 'moyen': 'important', 'medium': 'important', '2': 'important', 'normal': 'important',
            'optionnel': 'optional', 'optional': 'optional', 'faible': 'optional', 'low': 'optional', '3': 'optional', 'nice to have': 'optional',
            'a revoir': 'to_review', 'à revoir': 'to_review', 'to review': 'to_review', 'to_review': 'to_review', 'review': 'to_review', '4': 'to_review', 'unknown': 'to_review',
        }
        return mapping.get(value, 'important')

    def _reload_wizard(self):
        """Recharge le wizard."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'clearspend.import.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_back(self):
        """Retour à l'étape précédente."""
        if self.state == 'mapping':
            self.state = 'upload'
        elif self.state == 'preview':
            self.state = 'mapping'
        return self._reload_wizard()

    def action_download_template(self):
        """Télécharge le template CSV."""
        template_content = """nom;fournisseur;prix;quantite;cycle;priorite;departement;renouvellement;notes
Slack Business+;Slack;12.50;10;mensuel;essentiel;IT;2026-06-01;Communication équipe
GitHub Team;GitHub;4.00;5;mensuel;essentiel;Dev;;Repos privés
Notion Team;Notion;8.00;10;mensuel;important;Tous;;Wiki interne
Figma Professional;Figma;15.00;3;mensuel;important;Design;;UI/UX
Zoom Business;Zoom;199.90;1;annuel;important;Direction;2026-03-15;Visioconférences
"""
        attachment = self.env['ir.attachment'].create({
            'name': 'template_clearspend.csv',
            'type': 'binary',
            'datas': base64.b64encode(template_content.encode('utf-8')),
            'mimetype': 'text/csv',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
