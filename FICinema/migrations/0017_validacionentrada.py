# Generated manually for FICinema

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("FICinema", "0016_rename_ficinema_re_movie__0b0f6c_idx_ficinema_re_movie_i_0ff157_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ValidacionEntrada",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo_verificacion", models.CharField(max_length=80)),
                ("resultado", models.CharField(choices=[("VALIDA", "Válida"), ("YA_USADA", "Ya usada"), ("CANCELADA", "Cancelada"), ("CADUCADA", "Caducada"), ("NO_ENCONTRADA", "No encontrada"), ("SIN_PERMISO", "Sin permiso"), ("ERROR", "Error")], max_length=20)),
                ("detalle", models.CharField(blank=True, max_length=255)),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=255)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("entrada", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="validaciones", to="FICinema.entrada")),
                ("usuario_staff", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="validaciones_entrada", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-creado_en", "-id"],
                "indexes": [
                    models.Index(fields=["entrada", "-creado_en"], name="FICinema_va_entrada_41bd41_idx"),
                    models.Index(fields=["resultado", "-creado_en"], name="FICinema_va_resulta_0c6e96_idx"),
                    models.Index(fields=["usuario_staff", "-creado_en"], name="FICinema_va_usuario_508949_idx"),
                ],
            },
        ),
    ]
