# clients/urls_portail.py
from django.urls import path
from . import views_portail

urlpatterns = [
    path('', views_portail.connexion_client, name='portail_connexion'),
    path('comptable/', views_portail.connexion_comptable, name='portail_comptable_connexion'),
    path('code/', views_portail.saisie_code, name='portail_code'),
    path('code/renvoyer/', views_portail.renvoyer_code, name='portail_renvoyer_code'),
    path('espace/', views_portail.espace_client, name='portail_client'),
    path('comptable/espace/', views_portail.espace_comptable, name='portail_comptable'),
    path('document/<str:type_doc>/<int:pk>/', views_portail.pdf_document, name='portail_pdf'),
    path('deconnexion/', views_portail.deconnexion, name='portail_deconnexion'),
]
