# clients/models.py
from django.db import models
from django.contrib.auth.models import User
from taxes.models import Pays
import logging
import unicodedata

logger = logging.getLogger(__name__)


def normaliser_texte(texte):
    """Minuscules, sans accents ni espaces superflus — pour comparer des saisies libres."""
    texte = unicodedata.normalize('NFKD', (texte or '').strip().lower())
    return ''.join(c for c in texte if not unicodedata.combining(c))


class Client(models.Model):
    utilisateur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='clients')

    # Identité
    nom    = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, blank=True)

    # Contact
    email = models.EmailField(blank=True)

    INDICATIF_CHOICES = [
        ('+226', '🇧🇫 Burkina Faso (+226)'),
        ('+225', '🇨🇮 Côte d\'Ivoire (+225)'),
        ('+221', '🇸🇳 Sénégal (+221)'),
        ('+223', '🇲🇱 Mali (+223)'),
        ('+227', '🇳🇪 Niger (+227)'),
        ('+228', '🇹🇬 Togo (+228)'),
        ('+229', '🇧🇯 Bénin (+229)'),
        ('+237', '🇨🇲 Cameroun (+237)'),
        ('+241', '🇬🇦 Gabon (+241)'),
        ('+242', '🇨🇬 Congo (+242)'),
        ('+243', '🇨🇩 RDC (+243)'),
        ('+212', '🇲🇦 Maroc (+212)'),
        ('+213', '🇩🇿 Algérie (+213)'),
        ('+216', '🇹🇳 Tunisie (+216)'),
        ('+20',  '🇪🇬 Égypte (+20)'),
        ('+27',  '🇿🇦 Afrique du Sud (+27)'),
        ('+234', '🇳🇬 Nigeria (+234)'),
        ('+233', '🇬🇭 Ghana (+233)'),
        ('+254', '🇰🇪 Kenya (+254)'),
        ('+255', '🇹🇿 Tanzanie (+255)'),
        ('+256', '🇺🇬 Ouganda (+256)'),
        ('+250', '🇷🇼 Rwanda (+250)'),
        ('+251', '🇪🇹 Éthiopie (+251)'),
        ('+1',   '🇨🇦 Canada / 🇺🇸 États-Unis (+1)'),
        ('+52',  '🇲🇽 Mexique (+52)'),
        ('+55',  '🇧🇷 Brésil (+55)'),
        ('+54',  '🇦🇷 Argentine (+54)'),
        ('+57',  '🇨🇴 Colombie (+57)'),
        ('+56',  '🇨🇱 Chili (+56)'),
        ('+51',  '🇵🇪 Pérou (+51)'),
        ('+58',  '🇻🇪 Venezuela (+58)'),
        ('+44',  '🇬🇧 Royaume-Uni (+44)'),
        ('+33',  '🇫🇷 France (+33)'),
        ('+49',  '🇩🇪 Allemagne (+49)'),
        ('+39',  '🇮🇹 Italie (+39)'),
        ('+34',  '🇪🇸 Espagne (+34)'),
        ('+351', '🇵🇹 Portugal (+351)'),
        ('+32',  '🇧🇪 Belgique (+32)'),
        ('+41',  '🇨🇭 Suisse (+41)'),
        ('+31',  '🇳🇱 Pays-Bas (+31)'),
        ('+46',  '🇸🇪 Suède (+46)'),
        ('+47',  '🇳🇴 Norvège (+47)'),
        ('+45',  '🇩🇰 Danemark (+45)'),
        ('+358', '🇫🇮 Finlande (+358)'),
        ('+48',  '🇵🇱 Pologne (+48)'),
        ('+420', '🇨🇿 République Tchèque (+420)'),
        ('+36',  '🇭🇺 Hongrie (+36)'),
        ('+7',   '🇷🇺 Russie (+7)'),
        ('+90',  '🇹🇷 Turquie (+90)'),
        ('+86',  '🇨🇳 Chine (+86)'),
        ('+81',  '🇯🇵 Japon (+81)'),
        ('+82',  '🇰🇷 Corée du Sud (+82)'),
        ('+91',  '🇮🇳 Inde (+91)'),
        ('+62',  '🇮🇩 Indonésie (+62)'),
        ('+60',  '🇲🇾 Malaisie (+60)'),
        ('+65',  '🇸🇬 Singapour (+65)'),
        ('+66',  '🇹🇭 Thaïlande (+66)'),
        ('+84',  '🇻🇳 Vietnam (+84)'),
        ('+63',  '🇵🇭 Philippines (+63)'),
        ('+92',  '🇵🇰 Pakistan (+92)'),
        ('+880', '🇧🇩 Bangladesh (+880)'),
        ('+94',  '🇱🇰 Sri Lanka (+94)'),
        ('+977', '🇳🇵 Népal (+977)'),
        ('+61',  '🇦🇺 Australie (+61)'),
        ('+64',  '🇳🇿 Nouvelle-Zélande (+64)'),
    ]

    indicatif = models.CharField(
        max_length=5,
        choices=INDICATIF_CHOICES,
        default='+226',
        verbose_name="Indicatif"
    )
    telephone = models.CharField(max_length=20, blank=True, verbose_name="Numéro de téléphone")

    # ✅ Pays lié à la table Pays (devise + taxes automatiques)
    pays_obj = models.ForeignKey(
        Pays,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='clients',
        verbose_name="Pays"
    )

    # Adresse
    adresse     = models.TextField(blank=True)
    ville       = models.CharField(max_length=100, blank=True)
    code_postal = models.CharField(max_length=20, blank=True)
    province    = models.CharField(max_length=100, blank=True, verbose_name="Province / État / Région")

    # Entreprise
    entreprise = models.CharField(max_length=150, blank=True)

    # Logo client
    logo = models.ImageField(
        upload_to='clients/logos/',
        blank=True,
        null=True,
        verbose_name="Logo"
    )

    # Métadonnées
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.entreprise:
            return f"{self.nom} {self.prenom} - {self.entreprise}"
        return f"{self.nom} {self.prenom}"

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}".strip()

    @property
    def telephone_complet(self):
        if self.telephone:
            return f"{self.indicatif} {self.telephone}"
        return ""

    @property
    def devise(self):
        """Devise du client selon son pays"""
        if self.pays_obj:
            return self.pays_obj.devise_symbole
        return 'FCFA'

    @property
    def taux_tva(self):
        """
        CORRECTION : Calcule le taux total uniquement pour la province du client
        """
        if self.pays_obj:
            taxes = self.taxes_disponibles
            if taxes.exists():
                total = sum(taxe.taux for taxe in taxes)
                logger.debug(f"taux_tva pour {self.nom}: {total}% ({taxes.count()} taxes)")
                return total
        return 0

    @property
    def type_taxe_nom(self):
        """
        CORRECTION : Retourne uniquement les taxes de la province du client
        """
        if self.pays_obj:
            taxes = self.taxes_disponibles
            if taxes.exists():
                if taxes.count() == 1:
                    return taxes.first().code
                else:
                    result = " + ".join(taxe.code for taxe in taxes)
                    if len(result) > 50:
                        return f"{taxes.count()} taxes"
                    return result
        return 'TVA'

    @property
    def pays_nom(self):
        if self.pays_obj:
            return self.pays_obj.nom
        return ''
    
    @property
    def taxes_disponibles(self):
        """
        CORRECTION : Retourne les taxes disponibles selon la province du client
        """
        from taxes.models import Taxe

        if not self.pays_obj:
            return Taxe.objects.none()

        # Taxes nationales (sans province) + taxes de la province du client.
        # La province est saisie librement : comparaison sans accents ni casse
        # (« Quebec » = « Québec »).
        province_client = normaliser_texte(self.province)
        ids = [
            taxe.id
            for taxe in self.pays_obj.taxes.filter(actif=True)
            if not (taxe.province or '').strip()
            or normaliser_texte(taxe.province) == province_client
        ]
        return Taxe.objects.filter(id__in=ids).order_by('ordre')

    class Meta:
        ordering = ['-date_creation']
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'