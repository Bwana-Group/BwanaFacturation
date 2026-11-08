"""Envoi d'emails centralisé.

Une seule source de vérité pour la connexion SMTP :
  1. la configuration active saisie dans Administration → Configuration email
     (type « principal » ou « factures »),
  2. à défaut, les variables d'environnement lues dans settings.py
     (EMAIL_* pour « principal », FACTURE_* pour « factures »).
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

logger = logging.getLogger(__name__)


def get_email_config(type_email='principal'):
    """Configuration email active en base, ou None."""
    try:
        from users.admin_models import ConfigurationEmail
        return ConfigurationEmail.objects.filter(type_email=type_email, actif=True).first()
    except Exception:
        logger.exception("Lecture de la configuration email (%s) impossible", type_email)
        return None


def _params_depuis_settings(type_email):
    prefixe = 'FACTURE_' if type_email == 'factures' else ''
    return {
        'host': getattr(settings, f'{prefixe}EMAIL_HOST', settings.EMAIL_HOST),
        'port': getattr(settings, f'{prefixe}EMAIL_PORT', settings.EMAIL_PORT),
        'username': getattr(settings, f'{prefixe}EMAIL_HOST_USER', ''),
        'password': getattr(settings, f'{prefixe}EMAIL_HOST_PASSWORD', ''),
        'use_ssl': getattr(settings, f'{prefixe}EMAIL_USE_SSL', False),
        'use_tls': getattr(settings, f'{prefixe}EMAIL_USE_TLS', False),
    }


def get_email_connection(type_email='principal'):
    """Connexion SMTP prête à l'emploi (config en base, sinon settings)."""
    config = get_email_config(type_email)
    if config:
        params = {
            'host': config.host, 'port': config.port,
            'username': config.username, 'password': config.password,
            'use_ssl': config.use_ssl, 'use_tls': config.use_tls,
        }
    else:
        params = _params_depuis_settings(type_email)

    # SSL et TLS sont mutuellement exclusifs : on tranche selon le port
    # (465 => SSL implicite, sinon STARTTLS) au lieu de planter à l'envoi.
    if params['use_ssl'] and params['use_tls']:
        if int(params['port']) == 465:
            params['use_tls'] = False
        else:
            params['use_ssl'] = False

    return get_connection(timeout=getattr(settings, 'EMAIL_TIMEOUT', None), **params)


def get_from_email(type_email='principal'):
    """Adresse d'expédition (config en base, sinon settings)."""
    config = get_email_config(type_email)
    if config and config.from_email:
        return config.from_email
    if type_email == 'factures':
        return getattr(settings, 'FACTURE_DEFAULT_FROM_EMAIL', settings.DEFAULT_FROM_EMAIL)
    return settings.DEFAULT_FROM_EMAIL


def envoyer_mail(subject, message, recipient_list, type_email='principal',
                 html_message=None, fail_silently=False):
    """Équivalent de send_mail() qui utilise la configuration SMTP de l'application.

    Avec fail_silently=True, l'erreur n'interrompt pas le traitement mais elle
    est enregistrée dans les logs (plus d'échec invisible).
    Renvoie le nombre d'emails envoyés (0 en cas d'échec silencieux).
    """
    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=get_from_email(type_email),
            to=list(recipient_list),
            connection=get_email_connection(type_email),
        )
        if html_message:
            email.attach_alternative(html_message, 'text/html')
        return email.send(fail_silently=False)
    except Exception:
        logger.exception("Échec d'envoi de l'email « %s » à %s", subject, recipient_list)
        if fail_silently:
            return 0
        raise
