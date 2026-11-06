# devis/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Devis, LigneDevis
from clients.models import Client
from taxes.models import PaysTaxe, Taxe, Pays
from produits.models import Produit
from datetime import timedelta


class DevisForm(forms.ModelForm):
    pays = forms.ChoiceField(
        choices=[],
        required=False,
        label="Pays / Taxe",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_pays_select'})
    )
    
    # Champ pour les taxes multiples
    taxes = forms.ModelMultipleChoiceField(
        queryset=Taxe.objects.none(),
        required=False,
        label="Taxes applicables",
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'taxes-checkbox'})
    )
    
    # ✅ NOUVEAU : Champ devise
    devise = forms.ChoiceField(
        choices=[],
        required=False,
        label="Devise",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_devise'})
    )

    class Meta:
        model = Devis
        fields = ['client', 'date_validite', 'notes',
                  'pays', 'type_taxe', 'taux_taxe', 'taxes', 'devise']
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'date_validite': forms.DateInput(attrs={
                'class': 'form-control', 
                'type': 'date'
            }, format='%Y-%m-%d'),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'type_taxe': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_type_taxe',
                'readonly': 'readonly'
            }),
            'taux_taxe': forms.NumberInput(attrs={
                'class': 'form-control',
                'id': 'id_taux_taxe',
                'step': '0.01',
                'readonly': 'readonly'
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        if user:
            self.fields['client'].queryset = Client.objects.filter(utilisateur=user)

        # Champs optionnels
        self.fields['taux_taxe'].required = False
        self.fields['type_taxe'].required = False
        self.fields['pays'].required = False
        self.fields['taxes'].required = False
        self.fields['devise'].required = False  # ✅ Devise optionnelle

        # Choix des pays (legacy)
        pays_choices = [('', '-- Sélectionner un pays --')]
        pays_choices += [
            (p.code, f"{p.nom} ({p.type_taxe} {p.taux_defaut}%)")
            for p in PaysTaxe.objects.filter(actif=True)
        ]
        self.fields['pays'].choices = pays_choices
        
        # ✅ Configuration du champ devise
        # Récupérer toutes les devises disponibles
        toutes_devises = Pays.objects.filter(actif=True).values_list('devise_symbole', flat=True).distinct()
        devises_disponibles = list(set(list(toutes_devises) + ['FCFA', '€', '$', 'CAD', 'USD', 'EUR', 'GBP']))
        devises_disponibles.sort()
        
        devise_choices = [('', '-- Sélectionner une devise --')]
        for devise in devises_disponibles:
            devise_choices.append((devise, devise))
        self.fields['devise'].choices = devise_choices
        
        # Charger les taxes si un client est sélectionné
        client_id = self.data.get('client') or (self.instance.client_id if self.instance.pk else None)
        
        if client_id:
            try:
                client = Client.objects.get(id=client_id)
                if client.pays_obj:
                    # Récupérer les taxes du pays du client
                    self.fields['taxes'].queryset = Taxe.objects.filter(
                        pays=client.pays_obj,
                        actif=True
                    ).order_by('ordre')
                    
                    # Pré-sélectionner les taxes par défaut pour la création
                    if not self.instance.pk and not self.data.get('taxes'):
                        taxes_defaut = client.pays_obj.get_taxes_par_defaut()
                        self.fields['taxes'].initial = taxes_defaut
                    
                    # Mettre à jour le champ pays legacy
                    if client.pays_obj.code:
                        self.fields['pays'].initial = client.pays_obj.code
                    
                    # ✅ Pré-sélectionner la devise du client
                    if client.devise:
                        self.fields['devise'].initial = client.devise
                        
            except Client.DoesNotExist:
                pass
        
        # Si en modification, sélectionner les taxes existantes
        if self.instance.pk and self.instance.taxes.exists():
            self.fields['taxes'].initial = self.instance.taxes.all()
        
        # ✅ Si en modification, charger la devise sauvegardée
        if self.instance.pk and hasattr(self.instance, 'devise_choisie') and self.instance.devise_choisie:
            self.fields['devise'].initial = self.instance.devise_choisie
        
        # Définir une date par défaut (J+30)
        if not self.instance.pk and not self.initial.get('date_validite'):
            default_date = timezone.now().date() + timedelta(days=30)
            self.initial['date_validite'] = default_date

    def clean_date_validite(self):
        """Validation : La date doit être strictement supérieure à aujourd'hui"""
        date_validite = self.cleaned_data.get('date_validite')
        
        if not date_validite:
            raise ValidationError("La date de validité est obligatoire.")
        
        aujourdhui = timezone.now().date()
        
        if date_validite <= aujourdhui:
            raise ValidationError(
                f"La date de validité ({date_validite.strftime('%d/%m/%Y')}) "
                f"doit être postérieure à aujourd'hui ({aujourdhui.strftime('%d/%m/%Y')})."
            )
        
        return date_validite

    def clean_client(self):
        """Vérifier que le client existe et est actif"""
        client = self.cleaned_data.get('client')
        
        if client and hasattr(client, 'actif') and not client.actif:
            raise ValidationError(f"Le client '{client.nom}' est inactif.")
        
        return client

    def clean_taux_taxe(self):
        """Retourner 0 si taux_taxe est vide"""
        taux = self.cleaned_data.get('taux_taxe')
        if taux is None or taux == '':
            return 0
        return taux

    def clean_type_taxe(self):
        """Retourner chaîne vide si type_taxe est vide"""
        return self.cleaned_data.get('type_taxe') or ''

    def clean_pays(self):
        """Retourner chaîne vide si pays est vide"""
        return self.cleaned_data.get('pays') or ''

    def save(self, commit=True):
        """Sauvegarde avec gestion des taxes multiples et de la devise"""
        instance = super().save(commit=False)
        
        # ✅ Sauvegarder la devise choisie
        devise_choisie = self.cleaned_data.get('devise')
        if devise_choisie:
            instance.devise_choisie = devise_choisie
        
        if commit:
            instance.save()
            # Sauvegarder la relation ManyToMany des taxes
            self._save_m2m()
        
        return instance


# LigneDevisForm sans tva
class LigneDevisForm(forms.ModelForm):
    produit = forms.ModelChoiceField(
        queryset=Produit.objects.none(),
        required=False,
        label="Produit",
        widget=forms.Select(attrs={
            'class': 'form-select select-produit',
        })
    )

    class Meta:
        model = LigneDevis
        fields = ['description', 'quantite', 'prix_unitaire']
        widgets = {
            'description': forms.TextInput(attrs={
                'class': 'form-control description-input',
                'placeholder': 'Description du produit/service'
            }),
            'quantite': forms.NumberInput(attrs={
                'class': 'form-control quantite-input',
                'step': '0.01',
                'min': '0',
                'value': '1'
            }),
            'prix_unitaire': forms.NumberInput(attrs={
                'class': 'form-control prix-unitaire',
                'step': '0.01',
                'min': '0'
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if user:
            self.fields['produit'].queryset = Produit.objects.filter(
                user=user,
                actif=True
            ).select_related('pays').order_by('nom')
        else:
            self.fields['produit'].queryset = Produit.objects.none()

        self.fields['produit'].empty_label = "--- Sélectionnez un produit ---"

        if self.instance and self.instance.pk and self.instance.produit:
            self.fields['produit'].initial = self.instance.produit

    def clean_quantite(self):
        quantite = self.cleaned_data.get('quantite')
        if quantite is not None and quantite <= 0:
            raise ValidationError("La quantité doit être supérieure à 0.")
        return quantite

    def clean_prix_unitaire(self):
        prix = self.cleaned_data.get('prix_unitaire')
        if prix is not None and prix < 0:
            raise ValidationError("Le prix unitaire ne peut pas être négatif.")
        return prix

    def save(self, commit=True):
        instance = super().save(commit=False)

        produit = self.cleaned_data.get('produit')
        if produit:
            instance.produit = produit
            if not instance.description:
                instance.description = produit.nom
            if not instance.prix_unitaire or instance.prix_unitaire == 0:
                instance.prix_unitaire = produit.prix_ht

        if commit:
            instance.save()
        return instance


class BaseLigneDevisFormSet(forms.BaseFormSet):
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['user'] = self.user
        return super()._construct_form(i, **kwargs)
    
    def clean(self):
        if any(self.errors):
            return
        
        lignes_non_supprimees = 0
        for form in self.forms:
            if form.cleaned_data.get('DELETE', False):
                continue
            if form.cleaned_data.get('produit') or form.cleaned_data.get('description'):
                lignes_non_supprimees += 1
        
        if lignes_non_supprimees == 0:
            raise ValidationError("Veuillez ajouter au moins un produit ou service.")


LigneDevisFormSet = forms.formset_factory(
    LigneDevisForm,
    formset=BaseLigneDevisFormSet,
    extra=1,
    can_delete=True
)


class RechercheProduitForm(forms.Form):
    recherche = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Rechercher un produit...',
            'id': 'search-produit',
            'autocomplete': 'off'
        })
    )