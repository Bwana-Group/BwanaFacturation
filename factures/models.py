# factures/models.py
from django.db import models
from django.contrib.auth.models import User
from clients.models import Client
from devis.models import Devis
import secrets
from decimal import Decimal


class Facture(models.Model):
    STATUT_CHOICES = [
        ('en_attente', 'En attente d\'approbation'),
        ('approuvee', 'Approuvée'),
        ('rejetee', 'Rejetée'),
        ('non_payee', 'Non payée'),
        ('payee', 'Payée'),
        ('annulee', 'Annulée'),
    ]

    utilisateur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='factures')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='factures')
    devis = models.OneToOneField(Devis, on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='facture')
    numero = models.CharField(max_length=20, unique=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_echeance = models.DateField()
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    notes = models.TextField(blank=True)
    fichier_pdf = models.FileField(upload_to='factures/pdf/', blank=True, null=True)

    # ── Taxe par pays (ancien système - gardé pour compatibilité) ──
    pays = models.CharField(max_length=100, blank=True, default='',
                            verbose_name="Pays")
    type_taxe = models.CharField(max_length=50, blank=True, default='TVA',
                                  verbose_name="Type de taxe")
    taux_taxe = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                    verbose_name="Taux de taxe (%)")
    
    # Relation ManyToMany pour plusieurs taxes
    taxes = models.ManyToManyField(
        'taxes.Taxe',
        blank=True,
        related_name='factures',
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
        help_text="Devise sélectionnée par l'utilisateur pour cette facture"
    )
    
    # ✅ Date d'envoi par email
    date_envoi_email = models.DateTimeField(null=True, blank=True, verbose_name="Date d'envoi par email")
    
    # ── Champs d'approbation ──
    approuve_par = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='factures_approuvees',
        verbose_name="Approuvé par"
    )
    approuve_le = models.DateTimeField(null=True, blank=True, verbose_name="Date d'approbation")
    commentaire_approbation = models.TextField(blank=True, verbose_name="Commentaire d'approbation")
    
    accepte_par_client = models.BooleanField(null=True, blank=True, verbose_name="Accepté par le client")
    accepte_client_le = models.DateTimeField(null=True, blank=True, verbose_name="Date d'acceptation client")
    
    # Tokens pour liens publics
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

    def generer_tokens(self):
        """Génère des tokens uniques pour les liens d'approbation et client"""
        self.token_approbation = secrets.token_urlsafe(32)
        self.token_client = secrets.token_urlsafe(32)

    def __str__(self):
        return f"Facture {self.numero} - {self.client}"

    def calculer_total_ht(self):
        """Calcule le total HT de la facture - retourne Decimal"""
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
        """Retourne les taxes formatées pour l'affichage"""
        details = self.get_taxes_details()
        formatted = []
        
        for taxe in details:
            formatted.append({
                'nom': f"{taxe['code']} ({taxe['taux']}%)",
                'montant': taxe['montant']
            })
        
        return formatted
    
    def get_devise(self):
        """Retourne la devise de la facture (depuis le client ou choix utilisateur)"""
        if self.devise_choisie:
            return self.devise_choisie
        if self.client and self.client.pays_obj:
            return self.client.pays_obj.devise_symbole
        return 'FCFA'
    
    @property
    def est_approuvee(self):
        return self.statut == 'approuvee'
    
    @property
    def est_rejetee(self):
        return self.statut == 'rejetee'
    
    @property
    def est_payee(self):
        return self.statut == 'payee'
    
    @property
    def est_acceptee_client(self):
        return self.accepte_par_client == True

    class Meta:
        ordering = ['-date_creation']
        verbose_name = 'Facture'
        verbose_name_plural = 'Factures'


class LigneFacture(models.Model):
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='lignes')
    description = models.TextField(verbose_name="Description")
    quantite = models.DecimalField(max_digits=10, decimal_places=2)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    # ✅ TVA à 0 par défaut (taxe globale uniquement)
    tva = models.DecimalField(max_digits=5, decimal_places=2, default=0, blank=True, null=True)

    def total_ht(self):
        """Retourne le total HT de la ligne - retourne Decimal"""
        from decimal import Decimal
        return Decimal(str(self.quantite)) * Decimal(str(self.prix_unitaire))

    def montant_tva(self):
        """Retourne le montant de TVA de la ligne - non utilisé car taxe globale"""
        from decimal import Decimal
        if self.tva and Decimal(str(self.tva)) > Decimal('0'):
            return self.total_ht() * Decimal(str(self.tva)) / Decimal('100')
        return Decimal('0')

    def total_ttc(self):
        """Retourne le total TTC de la ligne - non utilisé car taxe globale"""
        return self.total_ht() + self.montant_tva()

    def __str__(self):
        return f"{self.description} x{self.quantite}"

    class Meta:
        verbose_name = 'Ligne de facture'
        verbose_name_plural = 'Lignes de facture'