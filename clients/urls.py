# clients/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.liste_clients, name='liste_clients'),
    path('ajouter/', views.ajouter_client, name='ajouter_client'),
    path('<int:pk>/', views.detail_client, name='detail_client'),
    path('<int:pk>/modifier/', views.modifier_client, name='modifier_client'),
    path('<int:pk>/supprimer/', views.supprimer_client, name='supprimer_client'),
    path('<int:pk>/nouvel-identifiant/', views.nouvel_identifiant_portail, name='nouvel_identifiant_portail'),
    path('api/<int:pk>/info/', views.api_client_info, name='api_client_info'),
    # ✅ NOUVELLE URL pour les taxes multiples
    path('api/<int:pk>/taxes/', views.api_client_taxes, name='api_client_taxes'),
]