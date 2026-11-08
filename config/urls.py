from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required
from django.views.static import serve
from django.shortcuts import redirect

# Préfixe de l'application, piloté par APP_URL_PREFIX (settings.py / .env)
PREFIXE = settings.APP_URL_PREFIX.strip('/')
RACINE_APP = f'/{PREFIXE}/' if PREFIXE else '/'

app_urls = [
    # Redirection racine → dashboard
    path('', lambda request: redirect(f'{RACINE_APP}devis/tableau-de-bord/')),

    path('users/',      include('users.urls')),
    path('clients/',    include('clients.urls')),
    path('devis/',      include('devis.urls')),
    path('factures/',   include('factures.urls')),
    path('api/',        include('taxes.urls')),
    path('produits/',   include('produits.urls')),

    # Administration personnalisée
    path('masque-zone-ad-rouge/', include('users.urls_admin')),
]

urlpatterns = [
    # Toutes les URLs de l'application sous le préfixe
    path(f'{PREFIXE}/' if PREFIXE else '', include(app_urls)),
]

# Redirection de la racine vers l'application (inutile si l'app est à la racine)
if PREFIXE:
    urlpatterns.append(path('', lambda request: redirect(RACINE_APP)))

urlpatterns += [
    # Media protégés par login
    path('media/<path:path>', login_required(serve), {
        'document_root': settings.MEDIA_ROOT
    }),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
