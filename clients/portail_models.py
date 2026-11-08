# clients/portail_models.py
from django.db import models


TYPES_ACCES = [
    ('client', 'Client'),
    ('comptable', 'Comptable'),
]


class CodePortail(models.Model):
    """Code à usage unique envoyé par email. Seule son empreinte est conservée."""
    type_acces = models.CharField(max_length=10, choices=TYPES_ACCES)
    cible      = models.CharField(max_length=254)
    code_hash  = models.CharField(max_length=64)
    ip         = models.GenericIPAddressField(null=True, blank=True)
    cree_le    = models.DateTimeField(auto_now_add=True)
    expire_le  = models.DateTimeField()
    utilise    = models.BooleanField(default=False)
    essais     = models.PositiveSmallIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=['type_acces', 'cible'])]


class BlocagePortail(models.Model):
    """Compteur d'échecs, par identifiant ou par adresse IP."""
    cle           = models.CharField(max_length=300, unique=True)
    echecs        = models.PositiveIntegerField(default=0)
    bloque_jusqua = models.DateTimeField(null=True, blank=True)
    maj_le        = models.DateTimeField(auto_now=True)


class JournalPortail(models.Model):
    """Historique des accès au portail client et à l'espace comptable."""
    ACTIONS = [
        ('connexion', 'Connexion'),
        ('echec', 'Code incorrect'),
        ('pdf', 'Document consulté'),
        ('deconnexion', 'Déconnexion'),
        ('nouvel_identifiant', 'Nouvel identifiant'),
    ]

    type_acces = models.CharField(max_length=10, choices=TYPES_ACCES)
    action     = models.CharField(max_length=20, choices=ACTIONS)
    client     = models.ForeignKey('clients.Client', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='acces_portail')
    email      = models.EmailField(blank=True)
    ip         = models.GenericIPAddressField(null=True, blank=True)
    detail     = models.CharField(max_length=100, blank=True)
    date       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
