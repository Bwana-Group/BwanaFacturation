from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class ProfilUtilisateur(models.Model):
    """Profil étendu de l'utilisateur — logo, entreprise, adresse."""
    user            = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profil')

    # ── Entreprise
    nom_entreprise  = models.CharField(max_length=200, blank=True, verbose_name="Nom de l'entreprise")
    telephone       = models.CharField(max_length=30,  blank=True, verbose_name="Téléphone")
    email_entreprise = models.EmailField(blank=True,   verbose_name="Email entreprise")
    site_web        = models.URLField(blank=True,       verbose_name="Site web")

    # ── Adresse
    adresse         = models.TextField(blank=True,     verbose_name="Adresse")
    ville           = models.CharField(max_length=100, blank=True, verbose_name="Ville")
    code_postal     = models.CharField(max_length=20,  blank=True, verbose_name="Code postal")
    pays            = models.CharField(max_length=100, blank=True, verbose_name="Pays")

    # ── Logo
    logo            = models.ImageField(
        upload_to='profils/logos/',
        blank=True, null=True,
        verbose_name="Logo de l'entreprise"
    )

    # ── Pied de page PDF
    mention_legale  = models.TextField(
        blank=True,
        verbose_name="Mentions légales",
        help_text="Apparaît en bas des PDF (SIRET, RCE, etc.)"
    )
    conditions_paiement = models.TextField(
        blank=True,
        default="Paiement à 30 jours.",
        verbose_name="Conditions de paiement"
    )

    # ── Approbation des devis : à qui envoyer la demande
    superieur_nom   = models.CharField(max_length=150, blank=True, verbose_name="Nom du supérieur")
    superieur_email = models.EmailField(blank=True, verbose_name="Email du supérieur")

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profil utilisateur"

    def __str__(self):
        return f"Profil de {self.user.get_full_name() or self.user.username}"

    @property
    def nom_affichage(self):
        """Nom entreprise ou nom utilisateur."""
        return self.nom_entreprise or self.user.get_full_name() or self.user.username


# ── Créer automatiquement un profil à l'inscription
@receiver(post_save, sender=User)
def creer_profil(sender, instance, created, **kwargs):
    if created:
        ProfilUtilisateur.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def sauvegarder_profil(sender, instance, **kwargs):
    try:
        instance.profil.save()
    except ProfilUtilisateur.DoesNotExist:
        ProfilUtilisateur.objects.create(user=instance)