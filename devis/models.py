# devis/models.py
from django.db import models
from django.contrib.auth.models import User
from clients.models import Client
from produits.models import Produit
import secrets
from decimal import Decimal


class Devis(models.Model):
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('approuve_superieur', 'En attente du client'),
        ('rejete_superieur', 'Rejeté par supérieur'),
        ('accepte', 'Accepté'),
        ('refuse', 'Refusé'),
        ('expire', 'Expiré'),
    ]

    # ── Champs existants ──
    utilisateur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devis')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='devis')
    numero = models.CharField(max_length=20, unique=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validite = models.DateField()
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    notes = models.TextField(blank=True)
    fichier_pdf = models.FileField(upload_to='devis/pdf/', blank=True, null=True)
    transforme_en_facture = models.BooleanField(default=False)
    
    # ── Champs d'approbation ──
    approuve_par = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='devis_approuves',
        verbose_name="Approuvé par"
    )
    approuve_le = models.DateTimeField(null=True, blank=True, verbose_name="Date d'approbation")
    commentaire_approbation = models.TextField(blank=True, verbose_name="Commentaire d'approbation")
    
    accepte_par_client = models.BooleanField(null=True, blank=True, verbose_name="Accepté par le client")
    accepte_client_le = models.DateTimeField(null=True, blank=True, verbose_name="Date d'acceptation client")
    
    token_approbation = models.CharField(
        max_length=100, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Token approbation"
    )
    token_client = models.CharField(
        max_length=100, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Token client"
    )

    # ── Champs taxes (ancien système - gardé pour compatibilité) ──
    pays = models.CharField(max_length=100, blank=True, default='',
                            verbose_name="Pays")
    type_taxe = models.CharField(max_length=50, blank=True, default='TVA',
                                  verbose_name="Type de taxe")
    taux_taxe = models.DecimalField(max_digits=5, decimal_places=2,
                                    default=0, verbose_name="Taux de taxe (%)")

    # Relation ManyToMany pour plusieurs taxes
    taxes = models.ManyToManyField(
        'taxes.Taxe',
        blank=True,
        related_name='devis',
        verbose_name="Taxes applicables"
    )

    # ✅ Taxes personnalisées (stockées en JSON)
    taxes_personnalisees = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        verbose_name="Taxes personnalisées"
    )

    # ✅ Devise choisie par l'utilisateur
    devise_choisie = models.CharField(
        max_length=10,
        blank=True,
        default='',
        verbose_name="Devise",
        help_text="Devise sélectionnée par l'utilisateur pour ce devis"
    )

    def generer_tokens(self):
        """Génère des tokens uniques pour les liens d'approbation et client"""
        self.token_approbation = secrets.token_urlsafe(32)
        self.token_client = secrets.token_urlsafe(32)

    def __str__(self):
        return f"Devis {self.numero} - {self.client}"

    def calculer_total_ht(self):
        """Calcule le total HT du devis - retourne Decimal"""
        total = Decimal('0')
        for ligne in self.lignes.all():
            total += ligne.total_ht()
        return total

    def calculer_tva(self):
        """
        Calcule le montant total des taxes
        Priorité aux taxes personnalisées (JSON)
        """
        from decimal import Decimal
        total_ht = self.calculer_total_ht()
        total_taxes = Decimal('0')
        
        # ✅ CAS 1: Taxes personnalisées (envoyées par le frontend)
        if self.taxes_personnalisees and isinstance(self.taxes_personnalisees, dict):
            from taxes.models import Taxe
            
            taxe_ids = self.taxes_personnalisees.get('ids', [])
            taxes_perso = self.taxes_personnalisees.get('personnalisees', [])
            
            # Taxes depuis la base de données
            if taxe_ids:
                taxes = Taxe.objects.filter(id__in=taxe_ids, actif=True)
                for taxe in taxes:
                    taux = Decimal(str(taxe.taux))
                    if taux > 0:
                        montant = total_ht * (taux / Decimal('100'))
                        total_taxes += montant
            
            # Taxes personnalisées (ajoutées manuellement)
            for taxe in taxes_perso:
                taux = Decimal(str(taxe.get('taux', 0)))
                if taux > 0:
                    montant = total_ht * (taux / Decimal('100'))
                    total_taxes += montant
            
            if total_taxes > 0:
                return total_taxes
        
        # ✅ CAS 2: Relation ManyToMany
        if self.taxes.exists():
            taxes_triees = self.taxes.filter(actif=True).order_by('ordre')
            total_tva = Decimal('0')
            base_calcul = total_ht
            
            for taxe in taxes_triees:
                taux = Decimal(str(taxe.taux))
                if taux > 0:
                    if taxe.cumulative:
                        montant_taxe = base_calcul * (taux / Decimal('100'))
                        base_calcul += montant_taxe
                    else:
                        montant_taxe = total_ht * (taux / Decimal('100'))
                    total_tva += montant_taxe
            
            if total_tva > 0:
                return total_tva
        
        # ✅ CAS 3: Ancien système (fallback)
        if self.taux_taxe and Decimal(str(self.taux_taxe)) > 0:
            taux = Decimal(str(self.taux_taxe))
            return total_ht * (taux / Decimal('100'))
        
        return Decimal('0')

    def calculer_total_ttc(self):
        """Calcule le total TTC (HT + toutes les taxes)"""
        return self.calculer_total_ht() + self.calculer_tva()
    
    def get_taxes_details(self):
        """
        Retourne les détails des taxes pour le PDF
        """
        from decimal import Decimal
        total_ht = self.calculer_total_ht()
        details = []
        
        # ✅ CAS 1: Taxes personnalisées
        if self.taxes_personnalisees and isinstance(self.taxes_personnalisees, dict):
            from taxes.models import Taxe
            
            taxe_ids = self.taxes_personnalisees.get('ids', [])
            taxes_perso = self.taxes_personnalisees.get('personnalisees', [])
            
            # Taxes depuis la base de données
            if taxe_ids:
                taxes = Taxe.objects.filter(id__in=taxe_ids, actif=True)
                for taxe in taxes:
                    taux = Decimal(str(taxe.taux))
                    if taux > 0:
                        montant = total_ht * (taux / Decimal('100'))
                        details.append({
                            'id': taxe.id,
                            'nom': taxe.nom,
                            'code': taxe.code,
                            'taux': float(taxe.taux),
                            'montant': float(montant),
                            'cumulative': taxe.cumulative
                        })
            
            # Taxes personnalisées
            for taxe in taxes_perso:
                taux = Decimal(str(taxe.get('taux', 0)))
                if taux > 0:
                    montant = total_ht * (taux / Decimal('100'))
                    details.append({
                        'id': None,
                        'nom': taxe.get('nom', 'Taxe'),
                        'code': taxe.get('code', 'TAXE'),
                        'taux': float(taxe.get('taux', 0)),
                        'montant': float(montant),
                        'cumulative': taxe.get('cumulative', False)
                    })
            
            if details:
                return details
        
        # ✅ CAS 2: Relation ManyToMany
        if self.taxes.exists():
            taxes_triees = self.taxes.filter(actif=True).order_by('ordre')
            base_calcul = total_ht
            total_taxes_cumul = Decimal('0')
            
            for taxe in taxes_triees:
                taux = Decimal(str(taxe.taux))
                if taux > 0:
                    if taxe.cumulative:
                        base_avec_taxes = total_ht + total_taxes_cumul
                        montant = base_avec_taxes * (taux / Decimal('100'))
                        total_taxes_cumul += montant
                    else:
                        montant = total_ht * (taux / Decimal('100'))
                    
                    details.append({
                        'id': taxe.id,
                        'nom': taxe.nom,
                        'code': taxe.code,
                        'taux': float(taxe.taux),
                        'montant': float(montant),
                        'cumulative': taxe.cumulative
                    })
            
            if details:
                return details
        
        # ✅ CAS 3: Ancien système (fallback)
        if self.taux_taxe and Decimal(str(self.taux_taxe)) > 0:
            taux = Decimal(str(self.taux_taxe))
            montant = total_ht * (taux / Decimal('100'))
            details.append({
                'id': None,
                'nom': self.type_taxe or 'TVA',
                'code': self.type_taxe or 'TVA',
                'taux': float(self.taux_taxe),
                'montant': float(montant),
                'cumulative': False
            })
        
        return details
    
    def get_taxes_total(self):
        """Retourne le montant total des taxes"""
        total = Decimal('0')
        for t in self.get_taxes_details():
            total += Decimal(str(t['montant']))
        return total
    
    def get_taxes_formatted(self):
        """
        Retourne les taxes formatées pour l'affichage
        """
        details = self.get_taxes_details()
        formatted = []
        
        for taxe in details:
            formatted.append({
                'nom': f"{taxe['code']} ({taxe['taux']}%)",
                'montant': taxe['montant']
            })
        
        return formatted
    
    def get_devise(self):
        """Retourne la devise choisie par l'utilisateur ou celle du client"""
        if self.devise_choisie:
            return self.devise_choisie
        if self.client and self.client.pays_obj:
            return self.client.pays_obj.devise_symbole
        return 'FCFA'
    
    @property
    def est_approuve(self):
        """Vérifie si le devis a été approuvé par le supérieur"""
        return self.statut == 'approuve_superieur'

    @property
    def envoi_direct(self):
        """Le devis est parti chez le client sans passer par un supérieur."""
        return self.approuve_par_id is not None and self.approuve_par_id == self.utilisateur_id
    
    @property
    def est_rejete(self):
        """Vérifie si le devis a été rejeté par le supérieur"""
        return self.statut == 'rejete_superieur'
    
    @property
    def est_accepte_client(self):
        """Vérifie si le client a accepté le devis"""
        return self.statut == 'accepte'
    
    @property
    def est_refuse_client(self):
        """Vérifie si le client a refusé le devis"""
        return self.statut == 'refuse'

    class Meta:
        ordering = ['-date_creation']
        verbose_name = 'Devis'
        verbose_name_plural = 'Devis'


class LigneDevis(models.Model):
    devis = models.ForeignKey(Devis, on_delete=models.CASCADE, related_name='lignes')
    
    # Lien vers le catalogue produits
    produit = models.ForeignKey(
        'produits.Produit', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='lignes_devis',
        verbose_name="Produit du catalogue"
    )
    
    description = models.CharField(max_length=255, verbose_name="Description")
    quantite = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantité")
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix unitaire HT")
    tva = models.DecimalField(max_digits=5, decimal_places=2, default=0, blank=True, null=True, verbose_name="TVA (%)")

    def total_ht(self):
        """Retourne le total HT de la ligne - retourne Decimal"""
        from decimal import Decimal
        return Decimal(str(self.quantite)) * Decimal(str(self.prix_unitaire))

    def montant_tva(self):
        """Retourne le montant de TVA de la ligne"""
        from decimal import Decimal
        if self.tva and Decimal(str(self.tva)) > 0:
            return self.total_ht() * Decimal(str(self.tva)) / Decimal('100')
        return Decimal('0')

    def total_ttc(self):
        """Retourne le total TTC de la ligne"""
        return self.total_ht() + self.montant_tva()

    def __str__(self):
        if self.produit:
            return f"{self.produit.nom} x{self.quantite}"
        return f"{self.description} x{self.quantite}"

    class Meta:
        verbose_name = 'Ligne de devis'
        verbose_name_plural = 'Lignes de devis'