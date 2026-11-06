from django.utils import timezone


def generer_numero_devis(user):
    from .models import Devis
    annee = timezone.now().year
    mois = timezone.now().month
    
    # Compter les devis de l'utilisateur ce mois
    count = Devis.objects.filter(
        utilisateur=user,
        date_creation__year=annee,
        date_creation__month=mois
    ).count()
    
    numero = f"DEV-{annee}{mois:02d}-{(count + 1):04d}"
    
    # S'assurer que le numéro est unique
    while Devis.objects.filter(numero=numero).exists():
        count += 1
        numero = f"DEV-{annee}{mois:02d}-{(count + 1):04d}"
    
    return numero


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
