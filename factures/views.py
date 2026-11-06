# factures/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django import forms as django_forms
from .models import Facture, LigneFacture 
from .forms import FactureForm, LigneFactureForm, LigneFactureFormSet, BaseLigneFactureFormSet
from produits.models import Produit
from devis.utils import generer_numero_facture, email_documents_configure, expliquer_erreur_email, MESSAGE_EMAIL_NON_CONFIGURE
from django.http import HttpResponse, Http404
from django.db.models import Q
import os
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from django.core.mail import send_mail, get_connection, EmailMessage
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import json
from decimal import Decimal


# ✅ Helper pour obtenir la configuration email depuis la base de données
def get_email_config(type_email='factures'):
    """Récupère la configuration email depuis la base de données"""
    try:
        from users.admin_models import ConfigurationEmail
        config = ConfigurationEmail.objects.get(type_email=type_email, actif=True)
        return config
    except Exception:
        return None


def get_email_connection(type_email='factures'):
    """Retourne une connexion SMTP basée sur la configuration en base"""
    config = get_email_config(type_email)
    if config:
        return get_connection(
            host=config.host,
            port=config.port,
            username=config.username,
            password=config.password,
            use_tls=config.use_tls,
            use_ssl=config.use_ssl,
        )
    # Fallback sur les settings
    return get_connection(
        host=getattr(settings, 'FACTURE_EMAIL_HOST', 'smtp.gmail.com'),
        port=getattr(settings, 'FACTURE_EMAIL_PORT', 587),
        username=getattr(settings, 'FACTURE_EMAIL_HOST_USER', ''),
        password=getattr(settings, 'FACTURE_EMAIL_HOST_PASSWORD', ''),
        use_tls=True,
    )


def get_from_email(type_email='factures'):
    """Retourne l'adresse d'expédition depuis la base ou les settings"""
    config = get_email_config(type_email)
    if config:
        return config.from_email
    return getattr(settings, 'FACTURE_DEFAULT_FROM_EMAIL', settings.DEFAULT_FROM_EMAIL)


@login_required
def liste_factures(request):
    statut = request.GET.get('statut', '')
    recherche = request.GET.get('q', '')

    factures = Facture.objects.filter(utilisateur=request.user)

    if statut:
        factures = factures.filter(statut=statut)
    if recherche:
        factures = factures.filter(numero__icontains=recherche) | \
                   factures.filter(client__nom__icontains=recherche)

    return render(request, 'factures/liste_factures.html', {
        'factures': factures,
        'statut': statut,
        'recherche': recherche,
        'nb_total': Facture.objects.filter(utilisateur=request.user).count(),
        'nb_non_payees': Facture.objects.filter(utilisateur=request.user, statut='non_payee').count(),
        'nb_payees': Facture.objects.filter(utilisateur=request.user, statut='payee').count(),
        'nb_annulees': Facture.objects.filter(utilisateur=request.user, statut='annulee').count(),
    })


@login_required
def ajouter_facture(request):
    if request.method == 'POST':
        form = FactureForm(request.user, request.POST)
        formset = LigneFactureFormSet(request.POST, prefix='lignes', user=request.user)

        if form.is_valid() and formset.is_valid():
            facture = form.save(commit=False)
            facture.utilisateur = request.user
            facture.numero = generer_numero_facture(request.user)
            
            # Sauvegarder la devise choisie
            devise_choisie = form.cleaned_data.get('devise')
            if devise_choisie:
                facture.devise_choisie = devise_choisie
            
            # Générer les tokens pour l'approbation
            facture.generer_tokens()
            
            # Récupérer les taxes personnalisées
            taxes_perso = request.POST.get('taxes_personnalisees', '')
            if taxes_perso:
                try:
                    taxes_data = json.loads(taxes_perso)
                    facture.taxes_personnalisees = taxes_data
                except json.JSONDecodeError:
                    facture.taxes_personnalisees = {}
            else:
                facture.taxes_personnalisees = {}
            
            # Désactiver l'ancien système si des taxes personnalisées existent
            if facture.taxes_personnalisees and (facture.taxes_personnalisees.get('ids') or facture.taxes_personnalisees.get('personnalisees')):
                facture.taux_taxe = 0
                facture.type_taxe = ''
            else:
                facture.taux_taxe = form.cleaned_data.get('taux_taxe', 0)
                facture.type_taxe = form.cleaned_data.get('type_taxe', 'TVA')
            
            facture.save()
            
            # Sauvegarder les taxes sélectionnées (ManyToMany)
            if form.cleaned_data.get('taxes'):
                facture.taxes.set(form.cleaned_data['taxes'])

            # Sauvegarder les lignes
            lignes_sauvegardees = 0
            for ligne_form in formset:
                if ligne_form.cleaned_data and not ligne_form.cleaned_data.get('DELETE'):
                    ligne = ligne_form.save(commit=False)
                    ligne.facture = facture
                    ligne.save()
                    lignes_sauvegardees += 1

            if lignes_sauvegardees == 0:
                facture.delete()
                messages.error(request, 'Veuillez ajouter au moins un produit ou service.')
                return render_creation_facture(request, form, formset)

            messages.success(request, f'Facture {facture.numero} créée !')
            
            return redirect('gestion_liens_facture', pk=facture.pk)
        else:
            messages.error(request, 'Veuillez corriger les erreurs.')
            print(f"ERREURS FORM: {form.errors}")
            print(f"ERREURS FORMSET: {formset.errors}")
    else:
        form = FactureForm(request.user)
        formset = LigneFactureFormSet(prefix='lignes', user=request.user)

    return render_creation_facture(request, form, formset)


def render_creation_facture(request, form, formset):
    """Helper pour le rendu de la création"""
    produits = Produit.objects.filter(
        user=request.user, actif=True
    ).select_related('pays').order_by('nom')

    return render(request, 'factures/form_facture.html', {
        'form': form,
        'formset': formset,
        'produits': produits,
        'lignes_existantes': [],
        'titre': 'Créer une facture',
        'bouton': 'Créer la facture'
    })


@login_required
def gestion_liens_facture(request, pk):
    """Page pour gérer les liens d'approbation et client"""
    facture = get_object_or_404(Facture, pk=pk, utilisateur=request.user)

    # Documents anciens créés sans liens publics
    if not facture.token_client or not facture.token_approbation:
        facture.generer_tokens()
        facture.save(update_fields=['token_client', 'token_approbation'])
    
    base_url = request.build_absolute_uri('/')[:-1]
    lien_approbation = f"{base_url}{reverse('visualiser_facture_approbation', args=[facture.token_approbation])}"
    lien_client = f"{base_url}{reverse('visualiser_facture_client', args=[facture.token_client])}"
    
    return render(request, 'factures/gestion_liens.html', {
        'facture': facture,
        'lien_approbation': lien_approbation,
        'lien_client': lien_client,
    })


def visualiser_facture_approbation(request, token):
    """Page publique pour que le supérieur approuve la facture"""
    facture = get_object_or_404(Facture, token_approbation=token)

    # Une seule décision possible, tant que la facture est en attente
    if facture.statut != 'en_attente':
        if facture.statut == 'rejetee':
            message = 'Cette facture a déjà été rejetée.'
        elif facture.statut == 'annulee':
            message = 'Cette facture a été annulée.'
        else:
            message = 'Cette facture a déjà été approuvée.'
        return render(request, 'factures/public/approbation.html', {
            'facture': facture,
            'deja_traite': True,
            'message_warning': message,
        })
    
    if request.method == 'POST':
        action = request.POST.get('action')
        commentaire = request.POST.get('commentaire', '')
        
        if action == 'approuver':
            facture.approuve_par = request.user if request.user.is_authenticated else None
            facture.approuve_le = timezone.now()
            facture.commentaire_approbation = commentaire
            facture.statut = 'approuvee'
            facture.save()
            
            try:
                send_mail(
                    subject=f'Facture {facture.numero} approuvée',
                    message=f'Votre facture {facture.numero} a été approuvée.\n\nCommentaire : {commentaire}',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[facture.utilisateur.email],
                    fail_silently=True,
                )
            except:
                pass
            
            return render(request, 'factures/public/approbation.html', {
                'facture': facture,
                'action_effectuee': 'approuver',
                'message_success': f'Facture {facture.numero} approuvée avec succès !',
                'commentaire': commentaire
            })
            
        elif action == 'rejeter':
            facture.statut = 'rejetee'
            facture.approuve_le = timezone.now()
            facture.commentaire_approbation = commentaire
            facture.save()
            
            try:
                send_mail(
                    subject=f'Facture {facture.numero} rejetée',
                    message=f'Votre facture {facture.numero} a été rejetée.\n\nMotif : {commentaire}',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[facture.utilisateur.email],
                    fail_silently=True,
                )
            except:
                pass
            
            return render(request, 'factures/public/approbation.html', {
                'facture': facture,
                'action_effectuee': 'rejeter',
                'message_success': f'Facture {facture.numero} rejetée.',
                'commentaire': commentaire
            })
    
    return render(request, 'factures/public/approbation.html', {
        'facture': facture,
        'deja_traite': False
    })


def visualiser_facture_client(request, token):
    """Page publique pour que le client accepte la facture"""
    facture = get_object_or_404(Facture, token_client=token)

    # Vérifier d'abord si le client a déjà répondu (le statut a changé depuis)
    if facture.accepte_par_client is not None:
        return render(request, 'factures/public/client.html', {
            'facture': facture,
            'deja_repondu': True,
            'message_warning': 'Vous avez déjà répondu à cette facture.'
        })

    if facture.statut != 'approuvee':
        return render(request, 'factures/public/client.html', {
            'facture': facture,
            'message_warning': 'Cette facture n\'a pas encore été approuvée en interne.',
            'en_attente': True
        })
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'accepter':
            facture.accepte_par_client = True
            facture.accepte_client_le = timezone.now()
            facture.statut = 'non_payee'
            facture.save()
            
            try:
                send_mail(
                    subject=f'Facture {facture.numero} acceptée',
                    message=f'Le client {facture.client.nom} a accepté la facture {facture.numero}.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[facture.utilisateur.email],
                    fail_silently=True,
                )
            except:
                pass
            
            return render(request, 'factures/public/client.html', {
                'facture': facture,
                'action_effectuee': 'accepter',
                'message_success': f'Merci ! Votre acceptation a été enregistrée.'
            })
            
        elif action == 'refuser':
            facture.accepte_par_client = False
            facture.accepte_client_le = timezone.now()
            facture.statut = 'rejetee'
            facture.save()
            
            try:
                send_mail(
                    subject=f'Facture {facture.numero} refusée',
                    message=f'Le client {facture.client.nom} a refusé la facture {facture.numero}.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[facture.utilisateur.email],
                    fail_silently=True,
                )
            except:
                pass
            
            return render(request, 'factures/public/client.html', {
                'facture': facture,
                'action_effectuee': 'refuser',
                'message_success': f'Nous avons bien enregistré votre refus.'
            })
    
    return render(request, 'factures/public/client.html', {
        'facture': facture,
    })


@login_required
def detail_facture(request, pk):
    facture = get_object_or_404(
        Facture.objects.select_related('client__pays_obj'),
        pk=pk, 
        utilisateur=request.user
    )
    lignes = facture.lignes.all()

    return render(request, 'factures/detail_facture.html', {
        'facture': facture,
        'lignes': lignes,
    })


@login_required
def modifier_facture(request, pk):
    facture = get_object_or_404(
        Facture.objects.select_related('client__pays_obj'),
        pk=pk, 
        utilisateur=request.user
    )

    if facture.statut == 'payee':
        messages.error(request, 'Une facture payée ne peut pas être modifiée.')
        return redirect('detail_facture', pk=pk)

    if request.method == 'POST':
        form = FactureForm(request.user, request.POST, instance=facture)
        formset = LigneFactureFormSet(request.POST, prefix='lignes', user=request.user)

        if form.is_valid() and formset.is_valid():
            facture = form.save(commit=False)

            # Une facture rejetée qui est corrigée repart en approbation
            if facture.statut == 'rejetee':
                facture.statut = 'en_attente'
                facture.approuve_par = None
                facture.approuve_le = None
                facture.accepte_par_client = None
                facture.accepte_client_le = None

            # Récupérer les taxes personnalisées
            taxes_perso = request.POST.get('taxes_personnalisees', '')
            if taxes_perso:
                try:
                    taxes_data = json.loads(taxes_perso)
                    facture.taxes_personnalisees = taxes_data
                except json.JSONDecodeError:
                    facture.taxes_personnalisees = {}
            else:
                facture.taxes_personnalisees = {}

            # Désactiver l'ancien système si des taxes personnalisées existent
            if facture.taxes_personnalisees and (facture.taxes_personnalisees.get('ids') or facture.taxes_personnalisees.get('personnalisees')):
                facture.taux_taxe = 0
                facture.type_taxe = ''
            else:
                facture.taux_taxe = form.cleaned_data.get('taux_taxe', 0)
                facture.type_taxe = form.cleaned_data.get('type_taxe', 'TVA')

            facture.save()

            # Sauvegarder les taxes ManyToMany
            if form.cleaned_data.get('taxes'):
                facture.taxes.set(form.cleaned_data['taxes'])
            else:
                facture.taxes.clear()
            
            facture.lignes.all().delete()

            lignes_sauvegardees = 0
            for ligne_form in formset:
                if ligne_form.cleaned_data and not ligne_form.cleaned_data.get('DELETE'):
                    ligne = ligne_form.save(commit=False)
                    ligne.facture = facture
                    ligne.save()
                    lignes_sauvegardees += 1

            if lignes_sauvegardees == 0:
                messages.error(request, 'Veuillez ajouter au moins un produit ou service.')
                return render_modification_facture(request, facture, form, formset)

            messages.success(request, f'Facture {facture.numero} modifiée !')
            return redirect('detail_facture', pk=facture.pk)
        else:
            messages.error(request, 'Veuillez corriger les erreurs.')
            print(f"ERREURS FORM: {form.errors}")
            print(f"ERREURS FORMSET: {formset.errors}")
        
        lignes_existantes = []
    else:
        form = FactureForm(request.user, instance=facture)
        formset = LigneFactureFormSet(prefix='lignes', user=request.user)
        lignes_existantes = list(facture.lignes.all())

    return render_modification_facture(request, facture, form, formset, lignes_existantes)


def render_modification_facture(request, facture, form, formset, lignes_existantes=None):
    if lignes_existantes is None:
        lignes_existantes = []
    
    produits = Produit.objects.filter(
        user=request.user, actif=True
    ).select_related('pays').order_by('nom')

    return render(request, 'factures/form_facture.html', {
        'form': form,
        'formset': formset,
        'produits': produits,
        'lignes_existantes': lignes_existantes,
        'titre': f'Modifier - {facture.numero}',
        'bouton': 'Enregistrer',
        'facture': facture
    })


@login_required
def supprimer_facture(request, pk):
    facture = get_object_or_404(Facture, pk=pk, utilisateur=request.user)

    if request.method == 'POST':
        numero = facture.numero
        facture.delete()
        messages.success(request, f'Facture {numero} supprimée.')
        return redirect('liste_factures')

    return render(request, 'factures/confirmer_suppression.html', {'facture': facture})


@login_required
def changer_statut_facture(request, pk):
    facture = get_object_or_404(Facture, pk=pk, utilisateur=request.user)

    if request.method == 'POST':
        nouveau_statut = request.POST.get('statut')
        if nouveau_statut in ['non_payee', 'payee', 'annulee']:
            facture.statut = nouveau_statut
            facture.save()
            messages.success(request, f'Statut mis à jour : {facture.get_statut_display()}')

    return redirect('detail_facture', pk=pk)


@login_required
def telecharger_pdf_facture(request, pk):
    facture = get_object_or_404(
        Facture.objects.select_related('client__pays_obj'),
        pk=pk, 
        utilisateur=request.user
    )
    from .pdf import generer_pdf_facture

    buffer = generer_pdf_facture(facture)

    nom_fichier = f"facture_{facture.numero}.pdf"
    chemin_relatif = f"factures/pdf/{nom_fichier}"
    chemin_complet = os.path.join(settings.MEDIA_ROOT, chemin_relatif)

    os.makedirs(os.path.dirname(chemin_complet), exist_ok=True)

    with open(chemin_complet, 'wb') as f:
        f.write(buffer.getvalue())

    facture.fichier_pdf = chemin_relatif
    facture.save()

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{nom_fichier}"'
    return response


# ============================================================
# ENVOI DE FACTURE PAR EMAIL (AVEC CONFIGURATION BASE DE DONNÉES)
# ============================================================

def telecharger_pdf_facture_public(request, token):
    """PDF de la facture sans compte : accessible avec le jeton du lien client ou d'approbation."""
    facture = Facture.objects.filter(Q(token_client=token) | Q(token_approbation=token)).first()
    if facture is None:
        raise Http404
    from .pdf import generer_pdf_facture
    buffer = generer_pdf_facture(facture)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="facture_{facture.numero}.pdf"'
    return response


@login_required
def envoyer_facture_email(request, pk):
    """Envoie la facture par email avec choix du destinataire"""
    facture = get_object_or_404(Facture, pk=pk, utilisateur=request.user)

    # Documents anciens créés sans liens publics
    if not facture.token_client or not facture.token_approbation:
        facture.generer_tokens()
        facture.save(update_fields=['token_client', 'token_approbation'])
    
    # Récupérer l'option choisie par l'utilisateur
    option_destinataire = request.POST.get('option_destinataire')
    
    # Déterminer l'adresse email du destinataire
    if option_destinataire == 'client':
        email_destinataire = facture.client.email
        if not email_destinataire:
            messages.error(request, f"Le client {facture.client.nom} n'a pas d'adresse email enregistrée.")
            return redirect('liste_factures')
    else:
        email_destinataire = request.POST.get('email_autre')
        if not email_destinataire:
            messages.error(request, "Veuillez saisir une adresse email.")
            return redirect('liste_factures')
    
    if not email_documents_configure():
        messages.error(request, MESSAGE_EMAIL_NON_CONFIGURE)
        return redirect('liste_factures')

    # Vérifier que le PDF existe, sinon le générer
    if not facture.fichier_pdf or not os.path.exists(facture.fichier_pdf.path):
        from .pdf import generer_pdf_facture
        buffer = generer_pdf_facture(facture)
        nom_fichier = f"facture_{facture.numero}.pdf"
        chemin_relatif = f"factures/pdf/{nom_fichier}"
        chemin_complet = os.path.join(settings.MEDIA_ROOT, chemin_relatif)
        os.makedirs(os.path.dirname(chemin_complet), exist_ok=True)
        with open(chemin_complet, 'wb') as f:
            f.write(buffer.getvalue())
        facture.fichier_pdf = chemin_relatif
        facture.save()
    
    # Déterminer la devise
    devise = facture.get_devise()
    
    # URLs complètes
    base_url = request.build_absolute_uri('/')[:-1]
    lien_facture = f"{base_url}{reverse('visualiser_facture_client', args=[facture.token_client])}"
    lien_pdf = f"{base_url}{reverse('pdf_facture_public', args=[facture.token_client])}"
    
    # Contexte pour le template email
    context = {
        'facture': facture,
        'client': facture.client,
        'total_ht': facture.calculer_total_ht(),
        'total_ttc': facture.calculer_total_ttc(),
        'tva': facture.calculer_tva(),
        'devise': devise,
        'date_echeance': facture.date_echeance,
        'lien_facture': lien_facture,
        'lien_pdf': lien_pdf,
        'utilisateur': request.user,
        'taxes_details': facture.get_taxes_details(),
    }
    
    # Rendre le template HTML
    html_message = render_to_string('factures/emails/facture_email.html', context)
    plain_message = strip_tags(html_message)
    
    # ✅ Utiliser la configuration depuis la base de données
    sujet = f"Facture {facture.numero} - {facture.client.nom}"
    
    # Récupérer la connexion et l'expéditeur depuis la base de données
    connection = get_email_connection('factures')
    from_email = get_from_email('factures')
    
    email = EmailMessage(
        subject=sujet,
        body=html_message,
        from_email=from_email,
        to=[email_destinataire],
        reply_to=[request.user.email],
        connection=connection,
    )
    email.content_subtype = 'html'
    
    # Ajouter le PDF en pièce jointe
    with open(facture.fichier_pdf.path, 'rb') as pdf_file:
        email.attach(f"facture_{facture.numero}.pdf", pdf_file.read(), 'application/pdf')
    
    # Envoyer l'email
    try:
        email.send(fail_silently=False)
        # Enregistrer la date d'envoi
        facture.date_envoi_email = timezone.now()
        facture.save(update_fields=['date_envoi_email'])
        messages.success(request, f"Facture {facture.numero} envoyée par email à {email_destinataire}")
    except Exception as e:
        messages.error(request, expliquer_erreur_email(e))
    
    return redirect('liste_factures')