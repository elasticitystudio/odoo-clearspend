# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import re
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

# Patterns de détection
AMOUNT_PATTERNS = [
    r'(?:total|montant|amount|ttc|net[^a-z]|à payer|due|balance)[^\d]*?(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2}))\s*(?:€|EUR|USD|\$)?',
    r'(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2}))\s*(?:€|EUR)',
    r'(?:€|EUR)\s*(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2}))',
]

DATE_PATTERNS = [
    r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})',
    r'(\d{1,2})\s+(?:jan|fév|mar|avr|mai|juin|juil|août|sep|oct|nov|déc|january|february|march|april|may|june|july|august|september|october|november|december)[a-z]*\s+(\d{2,4})',
]

INVOICE_NUMBER_PATTERNS = [
    r'(?:facture|invoice|n°|no\.?|#)\s*[:\s]*([A-Z0-9][-A-Z0-9]{3,20})',
    r'([A-Z]{2,4}[-/]?\d{4,10})',
]

# Mots-clés par fournisseur
PROVIDER_KEYWORDS = {
    'stripe': ['stripe', 'stripe.com', 'stripe payments'],
    'aws': ['amazon web services', 'aws', 'amazonaws'],
    'google': ['google cloud', 'gcp', 'google workspace', 'gsuite'],
    'microsoft': ['microsoft', 'azure', 'office 365', 'microsoft 365'],
    'github': ['github', 'github.com'],
    'gitlab': ['gitlab', 'gitlab.com'],
    'slack': ['slack', 'slack technologies'],
    'notion': ['notion', 'notion.so'],
    'figma': ['figma', 'figma.com'],
    'zoom': ['zoom', 'zoom video'],
    'dropbox': ['dropbox'],
    'mailchimp': ['mailchimp', 'intuit mailchimp'],
    'hubspot': ['hubspot'],
    'salesforce': ['salesforce'],
    'atlassian': ['atlassian', 'jira', 'confluence'],
    'digitalocean': ['digitalocean', 'digital ocean'],
    'heroku': ['heroku'],
    'vercel': ['vercel'],
    'netlify': ['netlify'],
    'cloudflare': ['cloudflare'],
    'ovh': ['ovh', 'ovhcloud'],
    'scaleway': ['scaleway'],
    'sendinblue': ['sendinblue', 'brevo'],
    'intercom': ['intercom'],
    'twilio': ['twilio'],
    'sendgrid': ['sendgrid'],
    'adobe': ['adobe', 'creative cloud'],
    'canva': ['canva'],
    'shopify': ['shopify'],
    'woocommerce': ['woocommerce'],
    'planethoster': ['planethoster'],
}


class OcrService(models.Model):
    _name = 'clearspend.ocr.service'
    _description = 'Service OCR Factures'

    name = fields.Char(string='Nom', default='Service OCR ClearSpend')
    ocr_engine = fields.Selection([
        ('basic', 'Extraction basique (regex)'),
        ('tesseract', 'Tesseract OCR'),
        ('google_vision', 'Google Cloud Vision'),
        ('azure_vision', 'Azure Computer Vision'),
    ], string='Moteur OCR', default='basic')
    
    api_key = fields.Char(string='Clé API OCR')
    total_processed = fields.Integer(string='Factures traitées', default=0)
    success_rate = fields.Float(string='Taux de succès (%)', default=0)
    
    @api.model
    def get_service(self):
        """Retourne ou crée le service OCR singleton."""
        service = self.search([], limit=1)
        if not service:
            service = self.create({'name': 'Service OCR ClearSpend'})
        return service

    def process_invoice_file(self, file_content, filename):
        """
        Traite un fichier facture et extrait les données.
        
        Args:
            file_content: Contenu du fichier en base64
            filename: Nom du fichier
            
        Returns:
            dict avec les données extraites
        """
        self.ensure_one()
        
        result = {
            'success': False,
            'confidence': 0,
            'data': {},
            'raw_text': '',
            'errors': [],
        }
        
        try:
            # Décoder le contenu
            content = base64.b64decode(file_content)
            
            # Extraire le texte selon le type de fichier
            if filename.lower().endswith('.pdf'):
                text = self._extract_text_from_pdf(content)
            elif filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                text = self._extract_text_from_image(content)
            elif filename.lower().endswith('.txt'):
                text = content.decode('utf-8', errors='ignore')
            else:
                result['errors'].append(f"Type de fichier non supporté: {filename}")
                return result
            
            result['raw_text'] = text
            
            if not text or len(text) < 10:
                result['errors'].append("Impossible d'extraire le texte du document")
                return result
            
            # Analyser le texte extrait
            extracted_data = self._analyze_text(text)
            result['data'] = extracted_data
            result['confidence'] = extracted_data.get('confidence', 0)
            result['success'] = result['confidence'] > 30
            
            # Mettre à jour les stats
            self.total_processed += 1
            if result['success']:
                self.success_rate = ((self.success_rate * (self.total_processed - 1)) + 100) / self.total_processed
            else:
                self.success_rate = ((self.success_rate * (self.total_processed - 1)) + 0) / self.total_processed
            
        except Exception as e:
            result['errors'].append(str(e))
            _logger.exception("Erreur OCR: %s", str(e))
        
        return result

    def _extract_text_from_pdf(self, content):
        """Extrait le texte d'un PDF."""
        text = ""
        
        try:
            # Essayer avec pdfplumber (meilleur pour les tableaux)
            import pdfplumber
            import io
            
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages[:5]:  # Limiter à 5 pages
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            
            if text.strip():
                return text
        except ImportError:
            _logger.warning("pdfplumber non installé, essai avec PyPDF2")
        except Exception as e:
            _logger.warning("Erreur pdfplumber: %s", str(e))
        
        try:
            # Fallback avec PyPDF2
            from PyPDF2 import PdfReader
            import io
            
            reader = PdfReader(io.BytesIO(content))
            for page in reader.pages[:5]:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        except ImportError:
            _logger.warning("PyPDF2 non installé")
        except Exception as e:
            _logger.warning("Erreur PyPDF2: %s", str(e))
        
        return text

    def _extract_text_from_image(self, content):
        """Extrait le texte d'une image via OCR."""
        text = ""
        
        if self.ocr_engine == 'tesseract':
            try:
                import pytesseract
                from PIL import Image
                import io
                
                image = Image.open(io.BytesIO(content))
                text = pytesseract.image_to_string(image, lang='fra+eng')
            except ImportError:
                _logger.warning("pytesseract ou PIL non installé")
            except Exception as e:
                _logger.warning("Erreur Tesseract: %s", str(e))
        
        elif self.ocr_engine == 'google_vision' and self.api_key:
            text = self._ocr_google_vision(content)
        
        elif self.ocr_engine == 'azure_vision' and self.api_key:
            text = self._ocr_azure_vision(content)
        
        # Fallback: pas d'OCR disponible pour les images
        if not text:
            _logger.info("OCR non disponible, extraction image impossible")
        
        return text

    def _ocr_google_vision(self, content):
        """OCR via Google Cloud Vision API."""
        import requests
        
        try:
            url = f"https://vision.googleapis.com/v1/images:annotate?key={self.api_key}"
            payload = {
                "requests": [{
                    "image": {"content": base64.b64encode(content).decode('utf-8')},
                    "features": [{"type": "TEXT_DETECTION"}]
                }]
            }
            
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                annotations = data.get('responses', [{}])[0].get('textAnnotations', [])
                if annotations:
                    return annotations[0].get('description', '')
        except Exception as e:
            _logger.error("Erreur Google Vision: %s", str(e))
        
        return ""

    def _ocr_azure_vision(self, content):
        """OCR via Azure Computer Vision API."""
        import requests
        
        try:
            # L'API key doit contenir "endpoint|key"
            parts = self.api_key.split('|')
            if len(parts) != 2:
                return ""
            
            endpoint, key = parts
            url = f"{endpoint}/vision/v3.2/read/analyze"
            headers = {
                'Ocp-Apim-Subscription-Key': key,
                'Content-Type': 'application/octet-stream'
            }
            
            response = requests.post(url, headers=headers, data=content, timeout=30)
            if response.status_code == 202:
                # Récupérer le résultat
                operation_url = response.headers.get('Operation-Location')
                import time
                for _ in range(10):
                    time.sleep(1)
                    result_response = requests.get(
                        operation_url,
                        headers={'Ocp-Apim-Subscription-Key': key},
                        timeout=30
                    )
                    result = result_response.json()
                    if result.get('status') == 'succeeded':
                        text = ""
                        for read_result in result.get('analyzeResult', {}).get('readResults', []):
                            for line in read_result.get('lines', []):
                                text += line.get('text', '') + "\n"
                        return text
        except Exception as e:
            _logger.error("Erreur Azure Vision: %s", str(e))
        
        return ""

    def _analyze_text(self, text):
        """Analyse le texte extrait pour identifier les données de facture."""
        text_lower = text.lower()
        result = {
            'amount': None,
            'currency': 'EUR',
            'invoice_number': None,
            'invoice_date': None,
            'provider_name': None,
            'provider_match': None,
            'confidence': 0,
        }
        
        confidence_points = 0
        
        # 1. Détecter le fournisseur
        for provider_key, keywords in PROVIDER_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    result['provider_name'] = provider_key.title()
                    result['provider_match'] = keyword
                    confidence_points += 25
                    break
            if result['provider_name']:
                break
        
        # 2. Extraire le montant
        for pattern in AMOUNT_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            if matches:
                # Prendre le montant le plus élevé (généralement le total)
                amounts = []
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    # Nettoyer et convertir
                    clean_amount = match.replace(' ', '').replace(',', '.')
                    try:
                        amounts.append(float(clean_amount))
                    except ValueError:
                        continue
                
                if amounts:
                    result['amount'] = max(amounts)
                    confidence_points += 30
                    break
        
        # 3. Extraire la date
        for pattern in DATE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    match = matches[0]
                    if len(match) == 3:
                        day, month, year = match
                        if len(year) == 2:
                            year = '20' + year
                        result['invoice_date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        confidence_points += 20
                        break
                except Exception:
                    continue
        
        # 4. Extraire le numéro de facture
        for pattern in INVOICE_NUMBER_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                result['invoice_number'] = matches[0] if isinstance(matches[0], str) else matches[0][0]
                confidence_points += 15
                break
        
        # 5. Détecter la devise
        if '$' in text or 'usd' in text_lower:
            result['currency'] = 'USD'
        elif '£' in text or 'gbp' in text_lower:
            result['currency'] = 'GBP'
        elif 'chf' in text_lower:
            result['currency'] = 'CHF'
        
        # Bonus si tout est trouvé
        if result['amount'] and result['provider_name'] and result['invoice_date']:
            confidence_points += 10
        
        result['confidence'] = min(100, confidence_points)
        
        return result


class InvoiceOcrMixin(models.Model):
    """Mixin pour ajouter l'OCR aux factures."""
    _inherit = 'clearspend.invoice'
    
    # Champs OCR
    ocr_processed = fields.Boolean(string='OCR traité', default=False)
    ocr_confidence = fields.Float(string='Confiance OCR (%)')
    ocr_raw_text = fields.Text(string='Texte OCR brut')
    ocr_detected_provider = fields.Char(string='Fournisseur détecté (OCR)')
    ocr_detected_amount = fields.Float(string='Montant détecté (OCR)')
    ocr_detected_date = fields.Date(string='Date détectée (OCR)')
    
    # Champs API
    external_id = fields.Char(string='ID externe')
    api_connection_id = fields.Many2one('clearspend.api.connection', string='Connexion API')
    
    def action_process_ocr(self):
        """Lance le traitement OCR sur la facture."""
        self.ensure_one()
        
        if not self.invoice_file:
            raise UserError("Aucun fichier attaché à cette facture")
        
        OcrService = self.env['clearspend.ocr.service']
        service = OcrService.get_service()
        
        # Traiter le fichier facture
        filename = self.invoice_filename or 'facture.pdf'
        result = service.process_invoice_file(self.invoice_file, filename)
        
        self.ocr_processed = True
        self.ocr_confidence = result.get('confidence', 0)
        self.ocr_raw_text = result.get('raw_text', '')[:5000]  # Limiter la taille
        
        if result.get('success'):
            data = result.get('data', {})
            
            self.ocr_detected_provider = data.get('provider_name')
            self.ocr_detected_amount = data.get('amount')
            
            if data.get('invoice_date'):
                try:
                    self.ocr_detected_date = data.get('invoice_date')
                except Exception:
                    pass
            
            # Auto-remplir si vide
            if not self.amount and data.get('amount'):
                self.amount = data.get('amount')
            
            if not self.invoice_date and data.get('invoice_date'):
                try:
                    self.invoice_date = data.get('invoice_date')
                except Exception:
                    pass
            
            if not self.name or self.name == 'Nouvelle facture':
                if data.get('invoice_number'):
                    self.name = data.get('invoice_number')
                elif data.get('provider_name'):
                    self.name = f"Facture {data.get('provider_name')}"
            
            # Essayer de matcher avec un fournisseur
            if data.get('provider_name') and not self.subscription_id:
                provider = self.env['clearspend.saas.provider'].search([
                    ('name', 'ilike', data.get('provider_name'))
                ], limit=1)
                
                if provider:
                    # Chercher un abonnement correspondant
                    subscription = self.env['clearspend.subscription'].search([
                        ('provider_id', '=', provider.id),
                        ('state', 'in', ['active', 'validated']),
                    ], limit=1)
                    
                    if subscription:
                        self.subscription_id = subscription.id
                        self.state = 'matched'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ OCR terminé',
                    'message': f"Confiance: {result.get('confidence')}% - Fournisseur: {data.get('provider_name', '?')} - Montant: {data.get('amount', '?')}€",
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '⚠️ OCR partiel',
                    'message': f"Confiance: {result.get('confidence')}% - Vérifiez les données manuellement",
                    'type': 'warning',
                    'sticky': False,
                }
            }

    @api.model
    def create(self, vals):
        """Override pour lancer l'OCR automatiquement si configuré."""
        record = super().create(vals)
        
        # Auto-OCR si fichier attaché et source = upload
        config = self.env['clearspend.config'].get_config()
        if config.auto_ocr and record.invoice_file and record.source == 'upload':
            try:
                record.action_process_ocr()
            except Exception as e:
                _logger.warning("Auto-OCR échoué: %s", str(e))
        
        return record


class SubscriptionApiMixin(models.Model):
    """Mixin pour ajouter les champs API aux abonnements."""
    _inherit = 'clearspend.subscription'
    
    external_id = fields.Char(string='ID externe', help='Identifiant dans le système source')
    api_connection_id = fields.Many2one('clearspend.api.connection', string='Connexion API')
    last_api_sync = fields.Datetime(string='Dernière sync API')
    
    def action_sync_from_api(self):
        """Resynchronise cet abonnement depuis l'API."""
        self.ensure_one()
        
        if not self.api_connection_id:
            raise UserError("Cet abonnement n'est pas lié à une connexion API")
        
        self.api_connection_id.action_sync_subscriptions()
        self.last_api_sync = fields.Datetime.now()


class ConfigOcrMixin(models.Model):
    """Ajoute les options OCR à la configuration."""
    _inherit = 'clearspend.config'
    
    auto_ocr = fields.Boolean(string='OCR automatique', default=True,
                              help='Lancer automatiquement l\'OCR sur les factures uploadées')
    ocr_engine = fields.Selection([
        ('basic', 'Extraction basique (regex)'),
        ('tesseract', 'Tesseract OCR'),
        ('google_vision', 'Google Cloud Vision'),
        ('azure_vision', 'Azure Computer Vision'),
    ], string='Moteur OCR', default='basic')
    ocr_api_key = fields.Char(string='Clé API OCR')
