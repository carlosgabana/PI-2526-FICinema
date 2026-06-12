# Generated manually to add sinopsis to Favorito

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("FICinema", "0010_favorito"),
    ]

    operations = [
        migrations.AddField(
            model_name="favorito",
            name="sinopsis",
            field=models.TextField(blank=True, default=""),
        ),
    ]
