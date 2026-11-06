from django.db import migrations


def creer_taxes_nationales(apps, schema_editor):
    """
    Les taxes nationales (TVA 18 % au Burkina, 20 % en France...) n'existent
    que dans l'ancien modèle PaysTaxe. Sans ligne Taxe, aucun taux n'est
    proposé dans les devis/factures : on les recrée pour chaque pays qui
    n'a encore aucune taxe. Les pays déjà configurés ne sont pas touchés.
    """
    Pays = apps.get_model('taxes', 'Pays')
    Taxe = apps.get_model('taxes', 'Taxe')
    PaysTaxe = apps.get_model('taxes', 'PaysTaxe')

    for ancien in PaysTaxe.objects.filter(actif=True, taux_defaut__gt=0):
        pays = Pays.objects.filter(code=ancien.code).first()
        if pays is None or Taxe.objects.filter(pays=pays).exists():
            continue
        code = (ancien.type_taxe or 'TVA')[:10]
        Taxe.objects.create(
            pays=pays,
            nom=ancien.type_taxe or 'TVA',
            code=code,
            taux=ancien.taux_defaut,
            actif=True,
            ordre=1,
            par_defaut=True,
            cumulative=False,
            province='',
            description=f"Taxe nationale — {pays.nom}",
        )


class Migration(migrations.Migration):

    dependencies = [
        ('taxes', '0003_alter_taxe_options_alter_taxe_unique_together_and_more'),
    ]

    operations = [
        migrations.RunPython(creer_taxes_nationales, migrations.RunPython.noop),
    ]
