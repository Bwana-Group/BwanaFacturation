from django.utils import timezone


def generer_numero_devis(user):
    """DEV-AAAAMMJJ-NNNN : date du jour, puis numéro d'ordre du jour (repart à 0001 chaque jour)."""
    from .models import Devis
    prefixe = f"DEV-{timezone.localdate():%Y%m%d}-"
    rang = Devis.objects.filter(numero__startswith=prefixe).count() + 1
    while Devis.objects.filter(numero=f"{prefixe}{rang:04d}").exists():
        rang += 1
    return f"{prefixe}{rang:04d}"


def generer_numero_facture(user):
    from factures.models import Facture
    annee = timezone.now().year
    mois = timezone.now().month
    
    count = Facture.objects.filter(
        utilisateur=user,
        date_creation__year=annee,
        date_creation__month=mois
    ).count()
    
    numero = f"FAC-{annee}{mois:02d}-{(count + 1):04d}"
    
    while Facture.objects.filter(numero=numero).exists():
        count += 1
        numero = f"FAC-{annee}{mois:02d}-{(count + 1):04d}"
    
    return numero

def email_documents_configure():
    """Vrai si un compte SMTP est disponible pour envoyer devis et factures
    (configuration active en base, ou identifiants dans le .env)."""
    from django.conf import settings
    from users.admin_models import ConfigurationEmail
    if ConfigurationEmail.objects.filter(type_email='factures', actif=True).exists():
        return True
    return bool(getattr(settings, 'FACTURE_EMAIL_HOST_USER', ''))


MESSAGE_EMAIL_NON_CONFIGURE = (
    "Aucun compte email n'est configuré pour l'envoi des devis et factures. "
    "Un administrateur doit l'ajouter dans Administration → Configuration email "
    "(type « Email dédié — factures et devis »)."
)


def expliquer_erreur_email(exc):
    """Traduit une erreur SMTP en message compréhensible pour l'utilisateur."""
    import smtplib
    import socket
    if isinstance(exc, (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused)):
        return ("Le serveur email a refusé l'identification. Vérifiez l'adresse et le "
                "mot de passe dans Administration → Configuration email (pour Gmail, "
                "utilisez un mot de passe d'application).")
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "L'adresse du destinataire a été refusée. Vérifiez qu'elle est correcte."
    if isinstance(exc, (socket.timeout, TimeoutError, ConnectionError, socket.gaierror)):
        return "Impossible de joindre le serveur email (vérifiez le serveur SMTP, le port et la connexion internet)."
    return f"Erreur lors de l'envoi : {exc}"
