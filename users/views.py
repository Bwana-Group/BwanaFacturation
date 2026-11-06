from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode, url_has_allowed_host_and_scheme
from django.urls import reverse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from .tokens import token_activation
from .forms import InscriptionForm


# ══════════════════════════════════════════
# INSCRIPTION
# ══════════════════════════════════════════
def inscription(request):
    if request.user.is_authenticated:
        return redirect('tableau_de_bord')

    if request.method == 'POST':
        if not request.POST.get('terms'):
            form = InscriptionForm(request.POST)
            messages.error(request,
                "Vous devez accepter les conditions d'utilisation "
                "et la politique de confidentialité.")
            return render(request, 'users/inscription.html', {'form': form})

        form = InscriptionForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            uid   = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_activation.make_token(user)
            activation_url = request.build_absolute_uri(reverse('activer_compte', args=[uid, token]))

            try:
                html_message = render_to_string(
                    'users/emails/activation_email.html',
                    {'user': user, 'activation_url': activation_url}
                )
                send_mail(
                    subject='Bwana Facturation — Activez votre compte',
                    message=f'Activation : {activation_url}',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
            except Exception:
                user.is_active = True
                user.save()
                login(request, user)
                messages.success(request, "Compte créé avec succès !")
                return redirect('tableau_de_bord')

            return render(request, 'users/activation_envoyee.html', {'email': user.email})
    else:
        form = InscriptionForm()

    return render(request, 'users/inscription.html', {'form': form})


# ══════════════════════════════════════════
# ACTIVATION COMPTE
# ══════════════════════════════════════════
def activer_compte(request, uidb64, token):
    try:
        uid  = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and token_activation.check_token(user, token):
        user.is_active = True
        user.save()
        return render(request, 'users/activation_succes.html')
    else:
        return render(request, 'users/activation_invalide.html')


# ══════════════════════════════════════════
# CONNEXION / DÉCONNEXION
# ══════════════════════════════════════════
def connexion(request):
    if request.user.is_authenticated:
        return redirect('tableau_de_bord')

    if request.method == 'POST':
        email    = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        ip = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
              or request.META.get('REMOTE_ADDR', ''))
        ua = request.META.get('HTTP_USER_AGENT', '')

        # Connexion par email (ou nom d'utilisateur). Plusieurs comptes peuvent
        # partager un email hérité : on essaie chacun avec le mot de passe saisi.
        candidats = list(User.objects.filter(email__iexact=email)) if email else []
        if not candidats:
            candidats = list(User.objects.filter(username=email)) if email else []

        username = None
        user = None
        if not candidats:
            messages.error(request, "Aucun compte trouvé avec cet email.")
        else:
            username = candidats[0].username
            for candidat in candidats:
                user = authenticate(request, username=candidat.username, password=password)
                if user is not None:
                    username = candidat.username
                    break
            # authenticate() renvoie None pour un compte inactif :
            # le signaler plutôt que d'annoncer un mauvais mot de passe.
            if user is None:
                inactif = next((c for c in candidats if not c.is_active and c.check_password(password)), None)
                if inactif:
                    user = inactif

        if username:
            if user is not None:
                if user.is_active:
                    login(request, user)
                    try:
                        from .admin_models import LoginHistory
                        LoginHistory.objects.create(
                            user=user, ip_address=ip or None,
                            user_agent=ua, succes=True
                        )
                    except Exception:
                        pass
                    next_url = request.GET.get('next', '')
                    if not url_has_allowed_host_and_scheme(
                        next_url, allowed_hosts={request.get_host()},
                        require_https=request.is_secure(),
                    ):
                        next_url = 'tableau_de_bord'
                    messages.success(request, f"Bienvenue {user.first_name or user.username} !")
                    return redirect(next_url)
                else:
                    messages.error(request,
                        "Votre compte n'est pas encore activé. "
                        "Vérifiez votre email de confirmation.")
            else:
                try:
                    from .admin_models import LoginHistory
                    failed_user = User.objects.filter(username=username).first()
                    if failed_user:
                        LoginHistory.objects.create(
                            user=failed_user, ip_address=ip or None,
                            user_agent=ua, succes=False
                        )
                except Exception:
                    pass
                messages.error(request, "Mot de passe incorrect.")

    return render(request, 'users/connexion.html')


def deconnexion(request):
    logout(request)
    return redirect('connexion')


# ══════════════════════════════════════════
# PROFIL — avec logo et infos entreprise
# ══════════════════════════════════════════
@login_required
def profil(request):
    from .models import ProfilUtilisateur
    profil_obj, _ = ProfilUtilisateur.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        # ── Infos utilisateur — l'email sert d'identifiant de connexion
        email = request.POST.get('email', '').strip()
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Adresse email invalide.")
            return redirect('profil')
        if User.objects.filter(email__iexact=email).exclude(pk=request.user.pk).exists():
            messages.error(request, "Cet email est déjà utilisé par un autre compte.")
            return redirect('profil')

        superieur_email = request.POST.get('superieur_email', '').strip()
        if superieur_email:
            try:
                validate_email(superieur_email)
            except ValidationError:
                messages.error(request, "Adresse email du supérieur invalide.")
                return redirect('profil')

        request.user.first_name = request.POST.get('first_name', '').strip()
        request.user.last_name  = request.POST.get('last_name', '').strip()
        request.user.email      = email
        request.user.save()

        # ── Infos entreprise
        profil_obj.superieur_nom        = request.POST.get('superieur_nom', '').strip()[:150]
        profil_obj.superieur_email      = superieur_email
        profil_obj.nom_entreprise       = request.POST.get('nom_entreprise', '').strip()
        profil_obj.telephone            = request.POST.get('telephone', '').strip()
        profil_obj.email_entreprise     = request.POST.get('email_entreprise', '').strip()
        profil_obj.site_web             = request.POST.get('site_web', '').strip()
        profil_obj.adresse              = request.POST.get('adresse', '').strip()
        profil_obj.ville                = request.POST.get('ville', '').strip()
        profil_obj.code_postal          = request.POST.get('code_postal', '').strip()
        profil_obj.pays                 = request.POST.get('pays', '').strip()
        profil_obj.mention_legale       = request.POST.get('mention_legale', '').strip()
        profil_obj.conditions_paiement  = request.POST.get('conditions_paiement', '').strip()

        # ── Logo
        if 'logo' in request.FILES:
            # Supprimer l'ancien logo
            if profil_obj.logo:
                import os
                if os.path.isfile(profil_obj.logo.path):
                    os.remove(profil_obj.logo.path)
            profil_obj.logo = request.FILES['logo']

        # ── Supprimer le logo
        if request.POST.get('supprimer_logo') == '1' and profil_obj.logo:
            import os
            if os.path.isfile(profil_obj.logo.path):
                os.remove(profil_obj.logo.path)
            profil_obj.logo = None

        profil_obj.save()
        messages.success(request, "Profil mis à jour avec succès !")
        return redirect('profil')

    return render(request, 'users/profil.html', {
        'user':   request.user,
        'profil': profil_obj,
    })


# ══════════════════════════════════════════
# MOT DE PASSE OUBLIÉ
# ══════════════════════════════════════════
def password_reset_request(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        try:
            user  = User.objects.get(email=email, is_active=True)
            uid   = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = request.build_absolute_uri(reverse('password_reset_confirm', args=[uid, token]))
            html_message = render_to_string(
                'users/emails/reset_password_email.html',
                {'user': user, 'reset_url': reset_url}
            )
            send_mail(
                subject='Bwana Facturation — Réinitialisation mot de passe',
                message=f'Reset : {reset_url}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
        except User.DoesNotExist:
            pass
        return render(request, 'users/password_reset_envoye.html')
    return render(request, 'users/password_reset.html')


def password_reset_confirm(request, uidb64, token):
    try:
        uid  = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    validlink = user and default_token_generator.check_token(user, token)

    if request.method == 'POST' and validlink:
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            return redirect('password_reset_succes')
    else:
        form = SetPasswordForm(user) if validlink else None

    if form:
        form.fields['new_password1'].widget.attrs.update({
            'class': 'form-control form-control-lg', 'placeholder': '••••••••'
        })
        form.fields['new_password2'].widget.attrs.update({
            'class': 'form-control form-control-lg', 'placeholder': '••••••••'
        })

    return render(request, 'users/password_reset_confirm.html', {
        'form': form, 'validlink': validlink,
    })


def password_reset_succes(request):
    return render(request, 'users/password_reset_succes.html')


# ══════════════════════════════════════════
# PAGES LÉGALES
# ══════════════════════════════════════════
def politique_confidentialite(request):
    return render(request, 'users/politique_confidentialite.html')