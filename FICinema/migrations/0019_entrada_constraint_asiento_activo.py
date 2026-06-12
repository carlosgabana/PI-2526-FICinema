from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("FICinema", "0018_rename_ficinema_va_entrada_41bd41_idx_ficinema_va_entrada_b62181_idx_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="entrada",
            name="entrada_asiento_unico_por_sesion",
        ),
        migrations.AddConstraint(
            model_name="entrada",
            constraint=models.UniqueConstraint(
                fields=("sesion", "asiento"),
                condition=~models.Q(estado="CANCELADA"),
                name="entrada_asiento_unico_por_sesion_activa",
            ),
        ),
    ]
