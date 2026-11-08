from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required
from django.views.static import serve
from django.shortcuts import redirect

urlpatterns = [
    # ✅ Préfixe BwanaFacturation — toutes les URLs sous ce préfixe
    path('BwanaFacturation/', include([

        # Redirection racine → dashboard
        path('', lambda request: redirect('/BwanaFacturation/devis/tableau-de-bord/')),

        path('users/',      include('users.urls')),
        path('clients/',    include('clients.urls')),
        path('devis/',      include('devis.urls')),
        path('factures/',   include('factures.urls')),
        path('api/',        include('taxes.urls')),
        path('produits/',   include('produits.urls')),
        path('portail/',    include('clients.urls_portail')),

        # Administration personnalisée
        path('masque-zone-ad-rouge/', include('users.urls_admin')),
    ])),

    # ✅ Redirection de la racine vers BwanaFacturation
    path('', lambda request: redirect('/BwanaFacturation/')),

    # Media protégés par login
    path('media/<path:path>', login_required(serve), {
        'document_root': settings.MEDIA_ROOT
    }),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)