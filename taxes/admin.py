# taxes/admin.py
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.db.models import Sum
from .models import Pays, Taxe, PaysTaxe


@admin.register(Pays)
class PaysAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'devise', 'devise_symbole', 'nb_taxes', 'actif']
    list_editable = ['actif']
    list_filter = ['actif']
    search_fields = ['nom', 'code']
    ordering = ['nom']
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('nom', 'code', 'actif')
        }),
        ('Devise', {
            'fields': ('devise', 'devise_symbole')
        }),
        ('Taxe par défaut (compatibilité)', {
            'fields': ('type_taxe_defaut', 'taux_defaut'),
            'classes': ('collapse',),
            'description': 'Ces champs sont utilisés pour la compatibilité avec l\'ancien système'
        }),
    )
    
    def nb_taxes(self, obj):
        """Affiche le nombre de taxes actives pour ce pays"""
        count = obj.taxes.filter(actif=True).count()
        if count == 0:
            return format_html('<span style="color: red;">0</span>')
        return format_html('<span style="color: green;">{}</span>', count)
    nb_taxes.short_description = "Taxes actives"


@admin.register(Taxe)
class TaxeAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom', 'pays', 'taux', 'ordre', 'par_defaut', 'cumulative', 'actif']
    list_editable = ['taux', 'ordre', 'par_defaut', 'cumulative', 'actif']
    list_filter = ['pays', 'actif', 'par_defaut', 'cumulative']
    search_fields = ['code', 'nom', 'pays__nom']
    ordering = ['pays', 'ordre']
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('pays', 'code', 'nom', 'actif')
        }),
        ('Taux et calcul', {
            'fields': ('taux', 'cumulative', 'ordre'),
            'help_texts': {
                'cumulative': 'Cochez pour les taxes qui s\'appliquent sur le montant incluant les autres taxes (ex: TVQ au Québec)',
                'ordre': 'Détermine l\'ordre de calcul des taxes cumulatives'
            }
        }),
        ('Options', {
            'fields': ('par_defaut', 'description'),
            'classes': ('collapse',),
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('pays')
    
    def save_model(self, request, obj, form, change):
        """À la sauvegarde, vérifier la cohérence des taxes cumulatives"""
        super().save_model(request, obj, form, change)
        
        # Si cette taxe est cumulative, vérifier l'ordre
        if obj.cumulative:
            # Réorganiser les taxes cumulatives du même pays
            taxes_cumulatives = Taxe.objects.filter(
                pays=obj.pays,
                cumulative=True,
                actif=True
            ).exclude(id=obj.id).order_by('ordre')
            
            current_order = obj.ordre
            for taxe in taxes_cumulatives:
                if taxe.ordre >= current_order:
                    taxe.ordre = taxe.ordre + 1
                    taxe.save()


@admin.register(PaysTaxe)
class PaysTaxeAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'type_taxe', 'taux_defaut', 'statut_migration', 'actif']
    list_editable = ['taux_defaut', 'actif']
    list_filter = ['actif', 'pays_migre']
    search_fields = ['nom', 'code']
    ordering = ['nom']
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('nom', 'code', 'actif')
        }),
        ('Taxe', {
            'fields': ('type_taxe', 'taux_defaut')
        }),
        ('Migration', {
            'fields': ('pays_migre',),
            'classes': ('collapse',),
            'description': 'Ce champ est rempli automatiquement après la migration'
        }),
    )
    
    actions = ['migrer_vers_nouveau_modele']
    
    def statut_migration(self, obj):
        """Affiche le statut de migration"""
        if obj.pays_migre:
            link = reverse('admin:taxes_pays_change', args=[obj.pays_migre.id])
            return format_html(
                '<a href="{}" style="color: green;">Migré vers {}</a>',
                link, obj.pays_migre.nom
            )
        return format_html('<span style="color: orange;">Non migré</span>')
    statut_migration.short_description = "Statut migration"
    
    def migrer_vers_nouveau_modele(self, request, queryset):
        """Action admin pour migrer les données"""
        compteur = 0
        for obj in queryset:
            if not obj.pays_migre:
                try:
                    pays, taxe = obj.migrer_vers_nouveau_modele()
                    compteur += 1
                    self.message_user(
                        request, 
                        f'{obj.nom} migré avec succès vers {pays.nom} (Taxe: {taxe.code} {taxe.taux}%)'
                    )
                except Exception as e:
                    self.message_user(
                        request, 
                        f'Erreur lors de la migration de {obj.nom}: {str(e)}',
                        level='ERROR'
                    )
        if compteur > 0:
            self.message_user(request, f'{compteur} pays/taxe(s) migré(s) avec succès!')
    migrer_vers_nouveau_modele.short_description = "Migrer vers le nouveau modèle"


# ✅ Inlines pour afficher les taxes dans l'admin du pays
class TaxeInline(admin.TabularInline):
    model = Taxe
    extra = 1
    fields = ['code', 'nom', 'taux', 'ordre', 'par_defaut', 'cumulative', 'actif']
    show_change_link = True


# ✅ Ré-enregistrer Pays avec l'inline
class PaysAdminWithInline(PaysAdmin):
    inlines = [TaxeInline]


# Désenregistrer et réenregistrer avec l'inline
admin.site.unregister(Pays)
admin.site.register(Pays, PaysAdminWithInline)