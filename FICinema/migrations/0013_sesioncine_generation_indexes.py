# Generated manually to speed up session generation queries.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("FICinema", "0012_rename_ficinema_fa_usuario_49eafb_idx_ficinema_fa_usuario_57c662_idx_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="sesioncine",
            index=models.Index(fields=["sala", "inicio", "fin"], name="FICinema_se_sala_i_0f0b7d_idx"),
        ),
        migrations.AddIndex(
            model_name="sesioncine",
            index=models.Index(fields=["movie_id", "fecha", "inicio", "fin"], name="FICinema_se_movie_i_b3e40c_idx"),
        ),
    ]
