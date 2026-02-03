from . import models
from . import wizards


def _post_init_hook(env):
    """Initialise le groupe Mode Avancé selon la configuration actuelle.
    
    Appelé automatiquement après l'installation/mise à jour du module.
    """
    try:
        Config = env['clearspend.config']
        
        # Récupérer toutes les configurations existantes
        configs = Config.search([])
        for config in configs:
            config._update_advanced_mode_group(activate=(config.mode == 'advanced'))
    except Exception:
        # Si le modèle n'existe pas encore, ignorer
        pass
