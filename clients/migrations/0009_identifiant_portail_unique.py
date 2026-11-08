import clients.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0008_identifiants_portail_existants'),
    ]

    operations = [
        migrations.AlterField(
            model_name='client',
            name='identifiant_portail',
            field=models.CharField(default=clients.models.generer_identifiant_portail, editable=False, max_length=12, unique=True, verbose_name='Identifiant du portail'),
        ),
    ]
