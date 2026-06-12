# Generated manually for FICinema favorites

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("FICinema", "0009_entrada_bono_usado_entrada_estado"),
    ]

    operations = [
        migrations.CreateModel(
            name="Favorito",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("movie_id", models.PositiveBigIntegerField()),
                ("titulo", models.CharField(max_length=255)),
                ("poster_url", models.URLField(blank=True, default="", max_length=500)),
                ("fecha_estreno", models.CharField(blank=True, default="", max_length=30)),
                ("valoracion", models.FloatField(default=0)),
                ("creado_en", models.DateTimeField(default=django.utils.timezone.now)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favoritos", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-creado_en"],
                "indexes": [
                    models.Index(fields=["usuario", "-creado_en"], name="FICinema_fa_usuario_49eafb_idx"),
                    models.Index(fields=["movie_id"], name="FICinema_fa_movie_i_ebc84b_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("usuario", "movie_id"), name="favorito_unico_por_usuario_y_pelicula"),
                ],
            },
        ),
    ]
