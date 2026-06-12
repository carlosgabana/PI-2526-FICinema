# Generated for FICinema final review feature

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("FICinema", "0014_rename_ficinema_se_sala_i_0f0b7d_idx_ficinema_se_sala_id_30dfe8_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Resena",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("movie_id", models.PositiveBigIntegerField()),
                ("titulo_pelicula", models.CharField(max_length=255)),
                ("puntuacion", models.PositiveSmallIntegerField(choices=[(1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5")])),
                ("comentario", models.TextField(blank=True, default="", max_length=600)),
                ("visible", models.BooleanField(default=True)),
                ("creada_en", models.DateTimeField(default=django.utils.timezone.now)),
                ("actualizada_en", models.DateTimeField(auto_now=True)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resenas", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-actualizada_en"],
                "indexes": [
                    models.Index(fields=["movie_id", "visible", "-actualizada_en"], name="FICinema_re_movie__0b0f6c_idx"),
                    models.Index(fields=["usuario", "-actualizada_en"], name="FICinema_re_usuario_6b80a5_idx"),
                    models.Index(fields=["puntuacion"], name="FICinema_re_puntuac_01e37f_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("usuario", "movie_id"), name="resena_unica_por_usuario_y_pelicula"),
                ],
            },
        ),
    ]
