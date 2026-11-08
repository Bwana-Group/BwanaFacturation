from django.db import migrations


def attribuer_identifiants(apps, schema_editor):
    """Donne un identifiant unique à chaque client déjà enregistré."""
    from clients.models import generer_identifiant_portail
    Client = apps.get_model('clients', 'Client')
    utilises = set()
    for pk in Client.objects.filter(identifiant_portail__isnull=True).values_list('pk', flat=True).iterator():
        identifiant = generer_identifiant_portail()
        while identifiant in utilises:
            identifiant = generer_identifiant_portail()
        utilises.add(identifiant)
        Client.objects.filter(pk=pk).update(identifiant_portail=identifiant)


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0007_portail_client'),
    ]

    operations = [
        migrations.RunPython(attribuer_identifiants, migrations.RunPython.noop),
    ]
