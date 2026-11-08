# clients/portail.py
"""Accès sans compte au portail client et à l'espace comptable : codes par email,
limitation des essais, documents visibles et historique."""
import ipaddress
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import Client
from .portail_models import BlocagePortail, CodePortail, JournalPortail

logger = logging.getLogger(__name__)

DUREE_CODE = timedelta(minutes=10)
ESSAIS_PAR_CODE = 5
ECHECS_PAR_IDENTIFIANT = 5
ECHECS_PAR_IP = 20
DUREE_BLOCAGE = timedelta(minutes=15)
DELAI_ENTRE_CODES = timedelta(seconds=60)
CODES_PAR_IP_PAR_HEURE = 20
INACTIVITE_SECONDES = 30 * 60

# Statuts qu'un client peut voir : jamais les documents encore internes
DEVIS_VISIBLES = ('approuve_superieur', 'accepte', 'refuse')
FACTURES_VISIBLES = ('approuvee', 'non_payee', 'payee')


def adresse_ip(request):
    brute = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
             or request.META.get('REMOTE_ADDR', ''))
    try:
        return str(ipaddress.ip_address(brute))
    except ValueError:
        return request.META.get('REMOTE_ADDR') or None


def normaliser_identifiant(saisie):
    """Accepte « bw 7k2m x9qp » comme « BW-7K2M-X9QP ». Renvoie '' si le format est faux."""
    brut = re.sub(r'[^A-Z0-9]', '', (saisie or '').upper())
    if len(brut) != 10 or not brut.startswith('BW'):
        return ''
    return f"BW-{brut[2:6]}-{brut[6:]}"


def client_du_portail(identifiant):
    return Client.objects.filter(identifiant_portail=identifiant).exclude(email='').first()


def comptes_du_comptable(email):
    if not email:
        return User.objects.none()
    return User.objects.filter(is_active=True, profil__comptable_email__iexact=email)


def url_portail_public():
    """Adresse du portail pour les PDF, générés sans requête. '' si le domaine est inconnu."""
    hotes = [getattr(settings, 'SITE_DOMAIN', '')] + list(settings.ALLOWED_HOSTS)
    for hote in hotes:
        hote = (hote or '').lstrip('.')
        if hote and hote not in ('*', 'localhost', '127.0.0.1'):
            return f"https://{hote}{reverse('portail_connexion')}"
    return ''


# ── Limitation des essais ──
def _est_bloque(cle):
    return BlocagePortail.objects.filter(cle=cle, bloque_jusqua__gt=timezone.now()).exists()


def _enregistrer_echec(cle, seuil):
    maintenant = timezone.now()
    with transaction.atomic():
        ligne, _ = BlocagePortail.objects.select_for_update().get_or_create(cle=cle)
        if ligne.bloque_jusqua and ligne.bloque_jusqua <= maintenant:
            ligne.echecs = 0
            ligne.bloque_jusqua = None
        ligne.echecs += 1
        if ligne.echecs >= seuil:
            ligne.bloque_jusqua = maintenant + DUREE_BLOCAGE
        ligne.save()


def _cle_cible(type_acces, cible):
    return f'{type_acces}:{cible}'


def _empreinte(type_acces, cible, code):
    return salted_hmac('clients.portail.code', f'{type_acces}:{cible}:{code}',
                       algorithm='sha256').hexdigest()


# ── Envoi et vérification des codes ──
def _envoyer_email(destinataire, sujet, template, contexte):
    from devis.views import get_email_connection, get_from_email
    email = EmailMessage(
        subject=sujet,
        body=render_to_string(template, contexte),
        from_email=get_from_email('factures'),
        to=[destinataire],
        connection=get_email_connection('factures'),
    )
    email.content_subtype = 'html'
    email.send()


def envoyer_code(type_acces, cible, destinataire, ip):
    """Crée et envoie un code. Renvoie False seulement si l'envoi de l'email échoue :
    une demande limitée ne doit pas se distinguer d'un envoi réussi."""
    maintenant = timezone.now()
    CodePortail.objects.filter(cree_le__lt=maintenant - timedelta(days=1)).delete()
    BlocagePortail.objects.filter(maj_le__lt=maintenant - timedelta(days=1)).delete()

    existants = CodePortail.objects.filter(type_acces=type_acces, cible=cible)
    if (_est_bloque(_cle_cible(type_acces, cible))
            or existants.filter(cree_le__gt=maintenant - DELAI_ENTRE_CODES).exists()
            or (ip and CodePortail.objects.filter(ip=ip, cree_le__gt=maintenant - timedelta(hours=1)).count()
                >= CODES_PAR_IP_PAR_HEURE)):
        return True

    code = f'{secrets.randbelow(1_000_000):06d}'
    existants.filter(utilise=False).update(utilise=True)
    ligne = CodePortail.objects.create(
        type_acces=type_acces, cible=cible, ip=ip,
        code_hash=_empreinte(type_acces, cible, code),
        expire_le=maintenant + DUREE_CODE,
    )
    try:
        _envoyer_email(destinataire, f'Votre code de connexion : {code}',
                       'portail/emails/code.html', {'code': code, 'minutes': int(DUREE_CODE.total_seconds() / 60)})
    except Exception:
        logger.exception("Portail : échec de l'envoi du code")
        ligne.delete()
        return False
    return True


def verifier_code(type_acces, cible, saisie, ip):
    """Renvoie 'ok', 'invalide' ou 'bloque'."""
    cle = _cle_cible(type_acces, cible)
    cle_ip = f'ip:{ip}'
    if _est_bloque(cle) or _est_bloque(cle_ip):
        return 'bloque'

    with transaction.atomic():
        ligne = (CodePortail.objects.select_for_update()
                 .filter(type_acces=type_acces, cible=cible, utilise=False, expire_le__gt=timezone.now())
                 .order_by('-cree_le').first())
        valide = (ligne is not None and ligne.essais < ESSAIS_PAR_CODE
                  and constant_time_compare(ligne.code_hash, _empreinte(type_acces, cible, saisie)))
        if valide:
            ligne.utilise = True
            ligne.save(update_fields=['utilise'])
        elif ligne is not None:
            ligne.essais += 1
            ligne.save(update_fields=['essais'])

    if valide:
        BlocagePortail.objects.filter(cle=cle).delete()
        return 'ok'
    _enregistrer_echec(cle, ECHECS_PAR_IDENTIFIANT)
    _enregistrer_echec(cle_ip, ECHECS_PAR_IP)
    return 'bloque' if _est_bloque(cle) or _est_bloque(cle_ip) else 'invalide'


# ── Documents accessibles ──
def devis_du_client(client):
    return client.devis.filter(
        Q(statut__in=DEVIS_VISIBLES)
        | Q(statut='expire', approuve_le__isnull=False)
        | Q(accepte_par_client__isnull=False)
    )


def factures_du_client(client):
    return client.factures.filter(
        Q(statut__in=FACTURES_VISIBLES)
        | Q(statut='annulee', approuve_le__isnull=False)
        | Q(statut='annulee', date_envoi_email__isnull=False)
        | Q(accepte_par_client__isnull=False)
    )


def inviter_comptable(request, profil):
    """Prévient le comptable de son accès. Renvoie False si l'email n'a pas pu partir."""
    try:
        _envoyer_email(
            profil.comptable_email,
            f'Accès aux documents de {profil.nom_affichage}',
            'portail/emails/invitation_comptable.html',
            {
                'profil': profil,
                'lien': request.build_absolute_uri(reverse('portail_comptable_connexion')),
            },
        )
    except Exception:
        logger.exception("Portail : échec de l'invitation du comptable")
        return False
    return True


def journaliser(type_acces, action, ip, client=None, email='', detail=''):
    JournalPortail.objects.create(type_acces=type_acces, action=action, ip=ip,
                                  client=client, email=email, detail=detail[:100])
