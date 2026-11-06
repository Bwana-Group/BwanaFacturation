"""
Corrige les factures issues d'un devis dont les taxes ne correspondent pas au devis.

Avant correction, la transformation devis → facture remplaçait un taux à 0 par
le taux par défaut du pays du client (ex. TVA 18 % au Burkina) : des factures
contiennent donc une taxe absente du devis accepté.

    python manage.py corriger_taxes_factures                    # aperçu, ne modifie rien
    python manage.py corriger_taxes_factures --appliquer        # corrige les factures non payées
    python manage.py corriger_taxes_factures --appliquer --inclure-payees
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from factures.models import Facture


class Command(BaseCommand):
    help = "Aligne les taxes des factures issues d'un devis sur celles du devis."

    def add_arguments(self, parser):
        parser.add_argument('--appliquer', action='store_true',
                            help="Enregistre les corrections (sinon simple aperçu).")
        parser.add_argument('--inclure-payees', action='store_true',
                            help="Corrige aussi les factures payées ou annulées "
                                 "(déjà réglées : à faire en connaissance de cause).")

    def handle(self, *args, appliquer=False, inclure_payees=False, **options):
        a_corriger, ignorees_payees, ignorees_modifiees = [], [], []

        factures = (Facture.objects.filter(devis__isnull=False)
                    .select_related('devis', 'client', 'utilisateur')
                    .order_by('date_creation'))
        for facture in factures:
            devis = facture.devis
            taxe_facture = facture.calculer_tva()
            taxe_devis = devis.calculer_tva()
            if abs(taxe_facture - taxe_devis) < Decimal('0.01'):
                continue

            # Lignes modifiées après la transformation : la différence ne vient
            # pas forcément du bug, on ne touche pas.
            if abs(facture.calculer_total_ht() - devis.calculer_total_ht()) >= Decimal('0.01'):
                ignorees_modifiees.append((facture, taxe_devis, taxe_facture))
                continue
            if facture.statut in ('payee', 'annulee') and not inclure_payees:
                ignorees_payees.append((facture, taxe_devis, taxe_facture))
                continue
            a_corriger.append((facture, taxe_devis, taxe_facture))

        def afficher(titre, lignes, style):
            if not lignes:
                return
            self.stdout.write(style(f"\n{titre} ({len(lignes)})"))
            for facture, taxe_devis, taxe_facture in lignes:
                devise = facture.get_devise()
                self.stdout.write(
                    f"  {facture.numero} (devis {facture.devis.numero}, {facture.utilisateur.username}, "
                    f"{facture.get_statut_display()}) : taxe {taxe_facture:.2f} → {taxe_devis:.2f} {devise}"
                )

        afficher("Factures à corriger", a_corriger, self.style.WARNING)
        afficher("Ignorées — payées ou annulées (ajoutez --inclure-payees)", ignorees_payees, self.style.NOTICE)
        afficher("Ignorées — lignes modifiées depuis le devis, à vérifier à la main", ignorees_modifiees, self.style.NOTICE)

        if not a_corriger:
            self.stdout.write(self.style.SUCCESS("\nAucune facture à corriger."))
            return
        if not appliquer:
            self.stdout.write("\nAperçu uniquement : relancez avec --appliquer pour enregistrer.")
            return

        with transaction.atomic():
            for facture, _, _ in a_corriger:
                devis = facture.devis
                facture.pays = devis.pays
                facture.taux_taxe = devis.taux_taxe or 0
                facture.type_taxe = devis.type_taxe if devis.taux_taxe else ''
                facture.taxes_personnalisees = devis.taxes_personnalisees or {}
                facture.fichier_pdf = None  # le PDF enregistré contient l'ancien montant
                facture.save()
                facture.taxes.set(devis.taxes.all())

        self.stdout.write(self.style.SUCCESS(f"\n{len(a_corriger)} facture(s) corrigée(s)."))
