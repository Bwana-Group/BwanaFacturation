from django.urls import path
from . import views

urlpatterns = [
    # Liste et création
    path('', views.liste_devis, name='liste_devis'),
    path('ajouter/', views.ajouter_devis, name='ajouter_devis'),
    
    # Détail, modification, suppression
    path('<int:pk>/', views.detail_devis, name='detail_devis'),
    path('<int:pk>/modifier/', views.modifier_devis, name='modifier_devis'),
    path('<int:pk>/supprimer/', views.supprimer_devis, name='supprimer_devis'),
    
    # Transformation et PDF
    path('<int:pk>/transformer/', views.transformer_en_facture, name='transformer_en_facture'),
    path('<int:pk>/pdf/', views.telecharger_pdf_devis, name='pdf_devis'),
    
    # Tableau de bord
    path('tableau-de-bord/', views.tableau_de_bord, name='tableau_de_bord'),
    path('api/etat/', views.api_etat_documents, name='api_etat_documents'),
    
    # ✅ NOUVELLES URLs POUR LE SYSTÈME D'APPROBATION
    # Gestion des liens
    path('<int:pk>/liens/', views.gestion_liens_devis, name='gestion_liens_devis'),
    
    # Pages publiques (sans login)
    path('public/approbation/<str:token>/', views.visualiser_devis_approbation, name='visualiser_devis_approbation'),
    path('public/client/<str:token>/', views.visualiser_devis_client, name='visualiser_devis_client'),
    path('public/pdf/<str:token>/', views.telecharger_pdf_devis_public, name='pdf_devis_public'),
    path('<int:pk>/envoyer/', views.envoyer_devis_email, name='envoyer_devis_email'),
]