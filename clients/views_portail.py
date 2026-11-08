# clients/views_portail.py
import time
from functools import wraps

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from devis.models import Devis
from factures.models import Facture
from . import portail

SESSION_ACCES = 'portail_acces'
SESSION_ATTENTE = 'portail_attente'

CONNEXION = {'client': 'portail_connexion', 'comptable': 'portail_comptable_connexion'}
ESPACE = {'client': 'portail_client', 'comptable': 'portail_comptable'}


def _acces_courant(request):
    """L'accès en cours, relu en base à chaque page : un identifiant changé ou un
    comptable retiré du profil perd son accès immédiatement."""
    acces = request.session.get(SESSION_ACCES)
    if not acces:
        return None
    if time.time() - acces['vu'] > portail.INACTIVITE_SECONDES:
        del request.session[SESSION_ACCES]
        return None

    resultat = {'type': acces['type'], 'cible': acces['cible'], 'client': None, 'comptes': None}
    if acces['type'] == 'client':
        resultat['client'] = portail.client_du_portail(acces['cible'])
        valide = resultat['client'] is not None
    else:
        resultat['comptes'] = list(portail.comptes_du_comptable(acces['cible']))
        valide = bool(resultat['comptes'])
    if not valide:
        del request.session[SESSION_ACCES]
        return None

    acces['vu'] = time.time()
    request.session[SESSION_ACCES] = acces
    return resultat


def _espace_requis(type_acces):
    def decorateur(vue):
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            acces = _acces_courant(request)
            if acces is None or acces['type'] != type_acces:
                messages.info(request, "Votre session est terminée. Veuillez vous identifier.")
                return redirect(CONNEXION[type_acces])
            request.acces_portail = acces
            return vue(request, *args, **kwargs)
        return enveloppe
    return decorateur


def _demander_code(request, type_acces, cible):
    """Envoie un code si la cible existe. La réponse ne révèle pas si elle existe."""
    if type_acces == 'client':
        client = portail.client_du_portail(cible)
        destinataire = client.email if client else ''
    else:
        destinataire = cible if portail.comptes_du_comptable(cible).exists() else ''
    if not destinataire:
        return True
    return portail.envoyer_code(type_acces, cible, destinataire, portail.adresse_ip(request))


def _page_connexion(request, type_acces):
    acces = _acces_courant(request)
    if acces is not None and acces['type'] == type_acces:
        return redirect(ESPACE[type_acces])

    erreur = ''
    if request.method == 'POST':
        saisie = request.POST.get('identifiant', '').strip()
        if type_acces == 'client':
            cible = portail.normaliser_identifiant(saisie)
            if not cible:
                erreur = "Format incorrect. Votre identifiant ressemble à BW-7K2M-X9QP."
        else:
            cible = saisie.lower()
            try:
                validate_email(cible)
            except ValidationError:
                erreur = "Adresse email invalide."
        if not erreur:
            if _demander_code(request, type_acces, cible):
                request.session[SESSION_ATTENTE] = {'type': type_acces, 'cible': cible}
                return redirect('portail_code')
            erreur = "L'envoi du code a échoué. Veuillez réessayer dans quelques minutes."

    return render(request, 'portail/connexion.html', {'type_acces': type_acces, 'erreur': erreur})


@never_cache
def connexion_client(request):
    return _page_connexion(request, 'client')


@never_cache
def connexion_comptable(request):
    return _page_connexion(request, 'comptable')


@never_cache
def saisie_code(request):
    attente = request.session.get(SESSION_ATTENTE)
    if not attente:
        return redirect('portail_connexion')

    type_acces, cible = attente['type'], attente['cible']
    erreur = ''
    if request.method == 'POST':
        ip = portail.adresse_ip(request)
        resultat = portail.verifier_code(type_acces, cible, request.POST.get('code', '').strip(), ip)
        client = portail.client_du_portail(cible) if type_acces == 'client' else None
        email = cible if type_acces == 'comptable' else ''
        if resultat == 'ok':
            del request.session[SESSION_ATTENTE]
            request.session.cycle_key()
            request.session[SESSION_ACCES] = {'type': type_acces, 'cible': cible, 'vu': time.time()}
            portail.journaliser(type_acces, 'connexion', ip, client=client, email=email)
            return redirect(ESPACE[type_acces])
        if client is not None or (email and portail.comptes_du_comptable(email).exists()):
            portail.journaliser(type_acces, 'echec', ip, client=client, email=email)
        erreur = ("Trop d'essais. Veuillez réessayer dans 15 minutes." if resultat == 'bloque'
                  else "Code incorrect ou expiré.")

    return render(request, 'portail/code.html', {'type_acces': type_acces, 'erreur': erreur})


@never_cache
@require_POST
def renvoyer_code(request):
    attente = request.session.get(SESSION_ATTENTE)
    if not attente:
        return redirect('portail_connexion')
    if _demander_code(request, attente['type'], attente['cible']):
        messages.info(request, "Si votre accès est valide, un nouveau code vient d'être envoyé.")
    else:
        messages.warning(request, "L'envoi du code a échoué. Veuillez réessayer dans quelques minutes.")
    return redirect('portail_code')


@never_cache
@_espace_requis('client')
def espace_client(request):
    client = request.acces_portail['client']
    return render(request, 'portail/espace_client.html', {
        'client': client,
        'devis': portail.devis_du_client(client).select_related('client__pays_obj').order_by('-date_creation'),
        'factures': portail.factures_du_client(client).select_related('client__pays_obj').order_by('-date_creation'),
    })


@never_cache
@_espace_requis('comptable')
def espace_comptable(request):
    comptes = request.acces_portail['comptes']
    type_doc = 'devis' if request.GET.get('type') == 'devis' else 'factures'
    modele = Devis if type_doc == 'devis' else Facture
    documents = modele.objects.filter(utilisateur__in=comptes)

    statut = request.GET.get('statut', '')
    if statut in dict(modele.STATUT_CHOICES):
        documents = documents.filter(statut=statut)
    else:
        statut = ''

    recherche = request.GET.get('q', '').strip()
    if recherche:
        documents = documents.filter(
            Q(numero__icontains=recherche)
            | Q(client__nom__icontains=recherche)
            | Q(client__entreprise__icontains=recherche)
        )

    periode = {}
    for nom, filtre in (('du', 'date_creation__date__gte'), ('au', 'date_creation__date__lte')):
        try:
            valeur = parse_date(request.GET.get(nom, ''))
        except ValueError:
            valeur = None
        if valeur:
            documents = documents.filter(**{filtre: valeur})
        periode[nom] = valeur.isoformat() if valeur else ''

    page = Paginator(
        documents.select_related('client__pays_obj', 'utilisateur__profil').order_by('-date_creation'), 25
    ).get_page(request.GET.get('page'))

    filtres = request.GET.copy()
    filtres.pop('page', None)
    return render(request, 'portail/espace_comptable.html', {
        'page': page,
        'type_doc': type_doc,
        'statut': statut,
        'statuts': modele.STATUT_CHOICES,
        'recherche': recherche,
        'du': periode['du'],
        'au': periode['au'],
        'plusieurs_comptes': len(comptes) > 1,
        'filtres': filtres.urlencode(),
    })


def _document_autorise(acces, type_doc, pk):
    if type_doc == 'devis':
        documents = (portail.devis_du_client(acces['client']) if acces['type'] == 'client'
                     else Devis.objects.filter(utilisateur__in=acces['comptes']))
    else:
        documents = (portail.factures_du_client(acces['client']) if acces['type'] == 'client'
                     else Facture.objects.filter(utilisateur__in=acces['comptes']))
    document = documents.filter(pk=pk).first()
    if document is None:
        raise Http404
    return document


@never_cache
def pdf_document(request, type_doc, pk):
    if type_doc not in ('devis', 'facture'):
        raise Http404
    acces = _acces_courant(request)
    if acces is None:
        messages.info(request, "Votre session est terminée. Veuillez vous identifier.")
        return redirect('portail_connexion')

    document = _document_autorise(acces, type_doc, pk)
    if type_doc == 'devis':
        from devis.pdf import generer_pdf_devis
        buffer = generer_pdf_devis(document)
    else:
        from factures.pdf import generer_pdf_facture
        buffer = generer_pdf_facture(document)

    portail.journaliser(acces['type'], 'pdf', portail.adresse_ip(request), client=acces['client'],
                        email=acces['cible'] if acces['type'] == 'comptable' else '', detail=document.numero)
    mode = 'attachment' if request.GET.get('telecharger') else 'inline'
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'{mode}; filename="{type_doc}_{document.numero}.pdf"'
    return response


@never_cache
@require_POST
def deconnexion(request):
    acces = _acces_courant(request)
    if acces is None:
        return redirect('portail_connexion')
    portail.journaliser(acces['type'], 'deconnexion', portail.adresse_ip(request), client=acces['client'],
                        email=acces['cible'] if acces['type'] == 'comptable' else '')
    del request.session[SESSION_ACCES]
    return redirect(CONNEXION[acces['type']])
