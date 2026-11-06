from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from functools import wraps
from django.urls import reverse
from django.views.decorators.http import require_POST
from .admin_models import LoginHistory, Annonce, MaintenanceMode, ConfigurationEmail  # ✅ Ajout ConfigurationEmail
from django.core.mail import get_connection, EmailMessage  # ✅ Pour les tests email


# ══════════════════════════════════════════
# DÉCORATEUR SUPER ADMIN
# ══════════════════════════════════════════
def superadmin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('connexion')
        if not request.user.is_superuser:
            messages.error(request, "Accès refusé — zone administrateur.")
            return redirect('tableau_de_bord')
        return view_func(request, *args, **kwargs)
    return wrapper


# ══════════════════════════════════════════
# DASHBOARD ADMIN
# ══════════════════════════════════════════
@superadmin_required
def admin_dashboard(request):
    from devis.models import Devis
    from factures.models import Facture
    from clients.models import Client

    users         = User.objects.all().order_by('-date_joined')
    nb_users      = users.count()
    nb_actifs     = users.filter(is_active=True).count()
    nb_inactifs   = users.filter(is_active=False).count()
    nb_superusers = users.filter(is_superuser=True).count()

    nb_devis    = Devis.objects.count()
    nb_factures = Facture.objects.count()
    nb_clients  = Client.objects.count()

    factures_payees = Facture.objects.filter(statut='payee')
    ca_total = sum(f.calculer_total_ttc() for f in factures_payees)

    derniers_users = users[:5]

    users_actifs = User.objects.annotate(
        nb_devis=Count('devis', distinct=True),
        nb_factures=Count('factures', distinct=True),
    ).order_by('-nb_devis')[:10]

    maintenance   = MaintenanceMode.get_instance()
    annonces      = Annonce.objects.filter(active=True).count()
    connexions_aujourd = LoginHistory.objects.filter(
        date__date=timezone.now().date()
    ).count()

    return render(request, 'admin_bwana/dashboard.html', {
        'nb_users':           nb_users,
        'nb_actifs':          nb_actifs,
        'nb_inactifs':        nb_inactifs,
        'nb_superusers':      nb_superusers,
        'nb_devis':           nb_devis,
        'nb_factures':        nb_factures,
        'nb_clients':         nb_clients,
        'ca_total':           ca_total,
        'derniers_users':     derniers_users,
        'users_actifs':       users_actifs,
        'maintenance':        maintenance,
        'nb_annonces':        annonces,
        'connexions_aujourd': connexions_aujourd,
    })


# ══════════════════════════════════════════
# LISTE UTILISATEURS
# ══════════════════════════════════════════
@superadmin_required
def admin_liste_users(request):
    recherche = request.GET.get('q', '')
    filtre    = request.GET.get('filtre', '')

    users = User.objects.annotate(
        nb_devis=Count('devis', distinct=True),
        nb_factures=Count('factures', distinct=True),
    ).order_by('-date_joined')

    if recherche:
        users = users.filter(
            username__icontains=recherche
        ) | User.objects.filter(
            email__icontains=recherche
        ).annotate(
            nb_devis=Count('devis', distinct=True),
            nb_factures=Count('factures', distinct=True),
        )

    if filtre == 'actifs':
        users = users.filter(is_active=True)
    elif filtre == 'inactifs':
        users = users.filter(is_active=False)
    elif filtre == 'superusers':
        users = users.filter(is_superuser=True)

    return render(request, 'admin_bwana/liste_users.html', {
        'users':     users,
        'recherche': recherche,
        'filtre':    filtre,
    })


# ══════════════════════════════════════════
# DÉTAIL UTILISATEUR
# ══════════════════════════════════════════
@superadmin_required
def admin_detail_user(request, pk):
    from devis.models import Devis
    from factures.models import Facture
    from clients.models import Client

    user     = get_object_or_404(User, pk=pk)
    devis    = Devis.objects.filter(utilisateur=user).order_by('-date_creation')
    factures = Facture.objects.filter(utilisateur=user).order_by('-date_creation')
    clients  = Client.objects.filter(utilisateur=user)
    historique = LoginHistory.objects.filter(user=user)[:20]

    factures_payees = factures.filter(statut='payee')
    ca_user = sum(f.calculer_total_ttc() for f in factures_payees)

    return render(request, 'admin_bwana/detail_user.html', {
        'u':           user,
        'devis':       devis,
        'factures':    factures,
        'clients':     clients,
        'historique':  historique,
        'ca_user':     ca_user,
        'nb_devis':    devis.count(),
        'nb_factures': factures.count(),
        'nb_clients':  clients.count(),
    })


# ══════════════════════════════════════════
# ACTIVER / DÉSACTIVER
# ══════════════════════════════════════════
@superadmin_required
@require_POST
def admin_toggle_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser:
        messages.error(request, "Impossible de désactiver un superadmin.")
        return redirect('admin_liste_users')
    user.is_active = not user.is_active
    user.save()
    statut = "activé" if user.is_active else "désactivé"
    messages.success(request, f"Compte de {user.get_full_name() or user.username} {statut}.")
    return redirect('admin_detail_user', pk=pk)


# ══════════════════════════════════════════
# PROMOUVOIR / RÉTROGRADER SUPERUSER
# ══════════════════════════════════════════
@superadmin_required
@require_POST
def admin_toggle_superuser(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, "Vous ne pouvez pas modifier votre propre statut.")
        return redirect('admin_detail_user', pk=pk)
    user.is_superuser = not user.is_superuser
    user.is_staff     = user.is_superuser
    user.save()
    statut = "promu administrateur" if user.is_superuser else "rétrogradé utilisateur"
    messages.success(request, f"{user.get_full_name() or user.username} {statut}.")
    return redirect('admin_detail_user', pk=pk)


# ══════════════════════════════════════════
# SUPPRIMER UTILISATEUR
# ══════════════════════════════════════════
@superadmin_required
def admin_supprimer_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser:
        messages.error(request, "Impossible de supprimer un superadmin.")
        return redirect('admin_liste_users')
    if user == request.user:
        messages.error(request, "Vous ne pouvez pas vous supprimer vous-même.")
        return redirect('admin_liste_users')
    if request.method == 'POST':
        nom = user.get_full_name() or user.username
        user.delete()
        messages.success(request, f"Utilisateur {nom} supprimé.")
        return redirect('admin_liste_users')
    return render(request, 'admin_bwana/confirmer_suppression_user.html', {'u': user})


# ══════════════════════════════════════════
# RÉINITIALISER MOT DE PASSE
# ══════════════════════════════════════════
@superadmin_required
@require_POST
def admin_reset_password(request, pk):
    user  = get_object_or_404(User, pk=pk)
    uid   = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = request.build_absolute_uri(reverse('password_reset_confirm', args=[uid, token]))
    try:
        from django.template.loader import render_to_string
        html_message = render_to_string(
            'users/emails/reset_password_email.html',
            {'user': user, 'reset_url': reset_url}
        )
        send_mail(
            subject='Bwana Facturation — Réinitialisation de votre mot de passe',
            message=f'Reset : {reset_url}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        messages.success(request, f"Email de réinitialisation envoyé à {user.email}.")
    except Exception as e:
        messages.error(request, f"Erreur envoi email : {e}")
    return redirect('admin_detail_user', pk=pk)


# ══════════════════════════════════════════
# IMPERSONNER UN UTILISATEUR
# ══════════════════════════════════════════
@superadmin_required
@require_POST
def admin_impersonate(request, pk):
    from django.contrib.auth import login
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser:
        messages.error(request, "Impossible d'impersonner un superadmin.")
        return redirect('admin_liste_users')
    admin_id = request.user.pk
    # login() vide la session quand l'utilisateur change :
    # admin_id doit être enregistré APRÈS la connexion.
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session['admin_id'] = admin_id
    messages.warning(request, f"Mode impersonation — vous êtes connecté en tant que {user.get_full_name() or user.username}.")
    return redirect('tableau_de_bord')


@login_required
def admin_stop_impersonate(request):
    from django.contrib.auth import login
    admin_id = request.session.get('admin_id')
    if not admin_id:
        return redirect('tableau_de_bord')
    admin = get_object_or_404(User, pk=admin_id, is_superuser=True)
    del request.session['admin_id']
    login(request, admin, backend='django.contrib.auth.backends.ModelBackend')
    messages.success(request, "Retour à votre compte administrateur.")
    return redirect('admin_dashboard')


# ══════════════════════════════════════════
# HISTORIQUE CONNEXIONS
# ══════════════════════════════════════════
@superadmin_required
def admin_historique_connexions(request):
    historique = LoginHistory.objects.select_related('user').order_by('-date')[:200]
    return render(request, 'admin_bwana/historique_connexions.html', {
        'historique': historique,
    })


# ══════════════════════════════════════════
# MODE MAINTENANCE
# ══════════════════════════════════════════
@superadmin_required
def admin_maintenance(request):
    maintenance = MaintenanceMode.get_instance()

    if request.method == 'POST':
        action  = request.POST.get('action')
        message = request.POST.get('message', maintenance.message)

        if action == 'activer':
            maintenance.actif      = True
            maintenance.message    = message
            maintenance.active_par = request.user
            maintenance.date_debut = timezone.now()
            maintenance.date_fin   = None
            maintenance.save()
            messages.warning(request, "Mode maintenance ACTIVÉ — le site est inaccessible aux utilisateurs.")

        elif action == 'desactiver':
            maintenance.actif    = False
            maintenance.date_fin = timezone.now()
            maintenance.save()
            messages.success(request, "Mode maintenance désactivé — le site est accessible.")

        elif action == 'message':
            maintenance.message = message
            maintenance.save()
            messages.success(request, "Message de maintenance mis à jour.")

        return redirect('admin_maintenance')

    return render(request, 'admin_bwana/maintenance_admin.html', {
        'maintenance': maintenance,
    })


# ══════════════════════════════════════════
# ANNONCES SYSTÈME
# ══════════════════════════════════════════
@superadmin_required
def admin_annonces(request):
    annonces = Annonce.objects.all().order_by('-created_at')
    return render(request, 'admin_bwana/annonces.html', {'annonces': annonces})


@superadmin_required
def admin_ajouter_annonce(request):
    if request.method == 'POST':
        titre        = request.POST.get('titre', '').strip()
        message      = request.POST.get('message', '').strip()
        type_annonce = request.POST.get('type_annonce', 'info')
        date_debut   = request.POST.get('date_debut')
        date_fin     = request.POST.get('date_fin') or None

        if titre and message:
            Annonce.objects.create(
                titre=titre,
                message=message,
                type_annonce=type_annonce,
                date_debut=date_debut,
                date_fin=date_fin,
                creee_par=request.user,
                active=True,
            )
            messages.success(request, f"Annonce « {titre} » créée.")
            return redirect('admin_annonces')
        else:
            messages.error(request, "Titre et message sont obligatoires.")

    return render(request, 'admin_bwana/form_annonce.html', {
        'titre':  'Nouvelle annonce',
        'bouton': 'Publier',
    })


@superadmin_required
@require_POST
def admin_toggle_annonce(request, pk):
    annonce        = get_object_or_404(Annonce, pk=pk)
    annonce.active = not annonce.active
    annonce.save()
    statut = "activée" if annonce.active else "désactivée"
    messages.success(request, f"Annonce {statut}.")
    return redirect('admin_annonces')


@superadmin_required
@require_POST
def admin_supprimer_annonce(request, pk):
    annonce = get_object_or_404(Annonce, pk=pk)
    annonce.delete()
    messages.success(request, "Annonce supprimée.")
    return redirect('admin_annonces')


# ══════════════════════════════════════════
# CONFIGURATION EMAIL (NOUVEAU)
# ══════════════════════════════════════════

@superadmin_required
def admin_config_email(request):
    """Page d'administration des configurations email"""
    configs = ConfigurationEmail.objects.all()
    
    # Créer les configurations par défaut si la table est vide
    if not configs.exists():
        ConfigurationEmail.objects.get_or_create(
            type_email='principal',
            defaults={
                'nom': 'Email principal (notifications)',
                'host': 'smtp.gmail.com',
                'port': 587,
                'use_tls': True,
                'use_ssl': False,
                'username': '',
                'password': '',
                'from_email': '',
                'actif': True,
            }
        )
        ConfigurationEmail.objects.get_or_create(
            type_email='factures',
            defaults={
                'nom': 'Email factures (à configurer)',
                'host': 'smtp.gmail.com',
                'port': 587,
                'use_tls': True,
                'use_ssl': False,
                'username': '',
                'password': '',
                'from_email': '',
                'actif': False,
            }
        )
        configs = ConfigurationEmail.objects.all()
    
    return render(request, 'admin_bwana/config_email.html', {
        'configs': configs,
    })


@superadmin_required
def admin_config_email_modifier(request, pk):
    """Modifier une configuration email"""
    config = get_object_or_404(ConfigurationEmail, pk=pk)
    
    if request.method == 'POST':
        config.nom = request.POST.get('nom', config.nom)
        config.host = request.POST.get('host', config.host)
        config.port = int(request.POST.get('port', config.port))
        config.use_tls = request.POST.get('use_tls') == 'on'
        config.use_ssl = request.POST.get('use_ssl') == 'on'
        config.username = request.POST.get('username', config.username)
        config.from_email = request.POST.get('from_email', config.from_email)
        
        # Mot de passe : ne modifier que si un nouveau est saisi
        nouveau_password = request.POST.get('password')
        if nouveau_password:
            config.password = nouveau_password
        
        config.save()
        messages.success(request, f"Configuration '{config.nom}' mise à jour.")
        return redirect('admin_config_email')
    
    return render(request, 'admin_bwana/config_email_modifier.html', {
        'config': config,
    })


@superadmin_required
def admin_config_email_tester(request, pk):
    """Tester une configuration email en envoyant un email test"""
    config = get_object_or_404(ConfigurationEmail, pk=pk)
    
    if request.method == 'POST':
        email_test = request.POST.get('email_test')
        
        if not email_test:
            messages.error(request, "Veuillez saisir une adresse email pour le test.")
            return redirect('admin_config_email')
        
        try:
            connection = get_connection(
                host=config.host,
                port=config.port,
                username=config.username,
                password=config.password,
                use_tls=config.use_tls,
                use_ssl=config.use_ssl,
            )
            
            email = EmailMessage(
                subject=f"Test email - {config.nom}",
                body=f"Ceci est un email de test depuis la configuration '{config.nom}'.\n\n"
                     f"Date du test : {timezone.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
                     f"Si vous recevez ce message, la configuration fonctionne correctement.",
                from_email=config.from_email,
                to=[email_test],
                connection=connection,
            )
            email.send(fail_silently=False)
            
            config.test_envoye = True
            config.date_dernier_test = timezone.now()
            config.save()
            
            messages.success(request, f"Email test envoyé avec succès à {email_test} depuis {config.nom}.")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'envoi du test : {str(e)}")
        
        return redirect('admin_config_email')
    
    return redirect('admin_config_email')


@superadmin_required
@require_POST
def admin_config_email_activer(request, pk):
    """Activer/désactiver une configuration"""
    config = get_object_or_404(ConfigurationEmail, pk=pk)
    
    # Si on active cette config, on désactive l'autre du même type
    if not config.actif:
        # Désactiver l'autre configuration du même type
        ConfigurationEmail.objects.filter(type_email=config.type_email, actif=True).update(actif=False)
    
    config.actif = not config.actif
    config.save()
    
    status = "activée" if config.actif else "désactivée"
    messages.success(request, f"Configuration '{config.nom}' {status}.")
    return redirect('admin_config_email')