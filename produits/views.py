import json
import re

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q, Prefetch
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
from .models import Produit, Categorie, Pays, Province, TypeTaxe, TauxTaxe, UniteVente
from .forms import ProduitForm, CategorieForm


# ─── PRODUITS ──────────────────────────
@login_required
def liste_produits(request):
    categorie_id = request.GET.get('categorie')
    recherche    = request.GET.get('q', '')

    produits = Produit.objects.filter(
        user=request.user, actif=True
    ).select_related(
        'categorie', 'pays', 'province', 'type_taxe', 'unite_vente'
    ).prefetch_related('type_taxe__taux')

    if categorie_id:
        produits = produits.filter(categorie_id=categorie_id)
    if recherche:
        produits = produits.filter(
            Q(nom__icontains=recherche) |
            Q(reference__icontains=recherche) |
            Q(description__icontains=recherche)
        )

    total_produits      = produits.count()
    valeur_totale_stock = sum(p.valeur_stock() for p in produits)
    produits_stock_bas  = [p for p in produits if p.stock_bas()]

    categories = Categorie.objects.filter(user=request.user).annotate(
        nb_produits=Count('produits')
    )

    return render(request, 'produits/liste.html', {
        'produits':            produits,
        'categories':          categories,
        'categorie_active':    int(categorie_id) if categorie_id else None,
        'recherche':           recherche,
        'total_produits':      total_produits,
        'valeur_totale_stock': valeur_totale_stock,
        'produits_stock_bas':  produits_stock_bas,
        'titre':               'Catalogue produits',
        'page_title':          'Gestion des produits'
    })


@login_required
def ajouter_produit(request):
    if request.method == 'POST':
        form = ProduitForm(request.POST, user=request.user)
        if form.is_valid():
            produit      = form.save(commit=False)
            produit.user = request.user
            produit.save()
            messages.success(request, f'Produit "{produit.nom}" ajouté avec succès')
            return redirect('liste_produits')
        else:
            messages.error(request, 'Veuillez corriger les erreurs ci-dessous')
    else:
        form = ProduitForm(user=request.user)

    dernier_produit = Produit.objects.filter(user=request.user).order_by('-date_creation').first()
    suggestion_ref  = f"REF-{str(dernier_produit.id + 1).zfill(3)}" if dernier_produit else "REF-001"

    pays_list      = Pays.objects.prefetch_related(
        Prefetch('types_taxe', queryset=TypeTaxe.objects.prefetch_related('taux'))
    ).all().order_by('nom')
    provinces_list = Province.objects.select_related('pays').all().order_by('pays__nom', 'nom')

    return render(request, 'produits/form.html', {
        'form':           form,
        'pays_list':      pays_list,
        'provinces_list': provinces_list,
        'titre':          'Ajouter un produit',
        'bouton':         'Ajouter le produit',
        'suggestion_ref': suggestion_ref
    })


@login_required
def modifier_produit(request, pk):
    produit = get_object_or_404(
        Produit.objects.select_related('pays', 'province', 'type_taxe', 'unite_vente'),
        pk=pk, user=request.user
    )

    if request.method == 'POST':
        form = ProduitForm(request.POST, instance=produit, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Produit "{produit.nom}" modifié avec succès')
            return redirect('liste_produits')
        else:
            messages.error(request, 'Veuillez corriger les erreurs ci-dessous')
    else:
        form = ProduitForm(instance=produit, user=request.user)

    pays_list      = Pays.objects.prefetch_related(
        Prefetch('types_taxe', queryset=TypeTaxe.objects.prefetch_related('taux'))
    ).all().order_by('nom')
    provinces_list = Province.objects.select_related('pays').all().order_by('pays__nom', 'nom')

    return render(request, 'produits/form.html', {
        'form':           form,
        'produit':        produit,
        'pays_list':      pays_list,
        'provinces_list': provinces_list,
        'titre':          f'Modifier {produit.nom}',
        'bouton':         'Mettre à jour'
    })


@login_required
def supprimer_produit(request, pk):
    produit = get_object_or_404(Produit, pk=pk, user=request.user)

    if request.method == 'POST':
        nom_produit = produit.nom
        produit.delete()
        messages.success(request, f'Produit "{nom_produit}" supprimé avec succès')
        return redirect('liste_produits')

    return render(request, 'produits/supprimer.html', {
        'produit': produit,
        'titre':   f'Supprimer {produit.nom}'
    })


@login_required
@require_POST
def dupliquer_produit(request, pk):
    produit_original           = get_object_or_404(Produit, pk=pk, user=request.user)

    # Référence unique par utilisateur : -COPY, -COPY2, -COPY3...
    base      = f"{produit_original.reference}-COPY"[:50]
    reference = base
    n = 2
    while Produit.objects.filter(user=request.user, reference=reference).exists():
        suffixe   = str(n)
        reference = f"{base[:50 - len(suffixe)]}{suffixe}"
        n += 1

    produit_original.pk        = None
    produit_original.reference = reference
    produit_original.nom       = f"{produit_original.nom} (copie)"
    produit_original.slug      = ""
    produit_original.save()
    messages.success(request, 'Produit dupliqué avec succès')
    return redirect('modifier_produit', pk=produit_original.pk)


# ─── CATÉGORIES ──────────────────────────
@login_required
def liste_categories(request):
    categories = Categorie.objects.filter(user=request.user).annotate(
        nb_produits=Count('produits')
    )
    return render(request, 'produits/categories/liste.html', {
        'categories': categories,
        'titre':      'Catégories',
        'page_title': 'Gestion des catégories'
    })


@login_required
def ajouter_categorie(request):
    if request.method == 'POST':

        # ✅ Requête AJAX depuis le modal (corps en JSON)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'erreur': 'Données invalides.'}, status=400)

            nom  = data.get('nom', '').strip()
            desc = data.get('description', '').strip()

            if not nom:
                return JsonResponse({'erreur': 'Le nom est obligatoire.'}, status=400)

            if Categorie.objects.filter(user=request.user, nom__iexact=nom).exists():
                return JsonResponse(
                    {'erreur': f'La catégorie "{nom}" existe déjà.'},
                    status=400
                )

            categorie = Categorie(nom=nom, description=desc, user=request.user)
            categorie.save()
            return JsonResponse({'id': categorie.pk, 'nom': categorie.nom})

        # Requête normale
        form = CategorieForm(request.POST, user=request.user)
        if form.is_valid():
            categorie      = form.save(commit=False)
            categorie.user = request.user
            categorie.save()
            messages.success(request, f'Catégorie "{categorie.nom}" ajoutée')
            return redirect('liste_categories')
    else:
        form = CategorieForm(user=request.user)

    return render(request, 'produits/categories/form.html', {
        'form':   form,
        'titre':  'Nouvelle catégorie',
        'bouton': 'Créer la catégorie'
    })


@login_required
def modifier_categorie(request, pk):
    categorie = get_object_or_404(Categorie, pk=pk, user=request.user)

    if request.method == 'POST':
        form = CategorieForm(request.POST, instance=categorie, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Catégorie "{categorie.nom}" modifiée')
            return redirect('liste_categories')
    else:
        form = CategorieForm(instance=categorie, user=request.user)

    return render(request, 'produits/categories/form.html', {
        'form':      form,
        'categorie': categorie,
        'titre':     f'Modifier {categorie.nom}',
        'bouton':    'Mettre à jour'
    })


@login_required
def supprimer_categorie(request, pk):
    categorie = get_object_or_404(Categorie, pk=pk, user=request.user)

    if categorie.produits.exists():
        messages.error(request, 'Impossible de supprimer une catégorie qui contient des produits')
        return redirect('liste_categories')

    if request.method == 'POST':
        nom = categorie.nom
        categorie.delete()
        messages.success(request, f'Catégorie "{nom}" supprimée')
        return redirect('liste_categories')

    return render(request, 'produits/categories/supprimer.html', {'categorie': categorie})


# ─── UNITÉS DE VENTE ──────────────────────────
@login_required
def ajouter_unite_vente(request):
    """API AJAX pour créer une unité de vente personnalisée."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            data = request.POST

        nom  = data.get('nom', '').strip()
        code = data.get('code', '').strip()

        if not nom:
            return JsonResponse({'erreur': 'Le nom est obligatoire.'}, status=400)

        # Générer un code si vide
        if not code:
            code = re.sub(r'[^a-z0-9]', '_', nom.lower())[:20]

        # Vérifier unicité pour cet utilisateur
        if UniteVente.objects.filter(user=request.user, nom__iexact=nom).exists():
            return JsonResponse({'erreur': f'L\'unité "{nom}" existe déjà.'}, status=400)

        unite = UniteVente.objects.create(
            user  = request.user,
            nom   = nom,
            code  = code,
            ordre = 50,
        )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'id': unite.pk, 'nom': unite.nom, 'code': unite.code})

        messages.success(request, f'Unité "{unite.nom}" créée.')
        return redirect('liste_produits')

    return JsonResponse({'erreur': 'Méthode non autorisée.'}, status=405)


# ─── API TAXES & PRODUITS ──────────────────────────
@login_required
def get_types_taxe_ajax(request):
    pays_id = request.GET.get('pays_id')
    if not pays_id:
        return JsonResponse({'error': 'pays_id requis'}, status=400)
    types_taxe = TypeTaxe.objects.filter(pays_id=pays_id).values('id', 'nom', 'code', 'description')
    return JsonResponse(list(types_taxe), safe=False)


@login_required
def get_taux_taxe_ajax(request):
    type_taxe_id = request.GET.get('type_taxe_id')
    if not type_taxe_id:
        return JsonResponse({'error': 'type_taxe_id requis'}, status=400)
    taux = TauxTaxe.objects.filter(type_taxe_id=type_taxe_id).values(
        'id', 'region', 'code_region', 'taux', 'est_defaut'
    )
    return JsonResponse(list(taux), safe=False)


@login_required
def get_provinces_ajax(request):
    pays_id = request.GET.get('pays_id')
    if not pays_id:
        return JsonResponse({'error': 'pays_id requis'}, status=400)
    provinces = Province.objects.filter(pays_id=pays_id).values(
        'id', 'nom', 'code', 'tps', 'tvq', 'tvh'
    )
    return JsonResponse(list(provinces), safe=False)


@login_required
def get_produit_ajax(request, pk):
    produit = get_object_or_404(Produit, pk=pk, user=request.user, actif=True)
    return JsonResponse({
        'id':          produit.pk,
        'nom':         produit.nom,
        'description': produit.description or produit.nom,
        'prix_ht':     float(produit.prix_ht),
        'tva':         float(produit.taux_tva),
        'devise':      produit.devise_symbole,
        # ✅ unite_label au lieu de get_unite_display()
        'unite':       produit.unite_label,
    })