from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from FICinema.models import SesionCine
from FICinema.views import (
    MAX_PELICULAS_CARTELERA,
    construir_dias_disponibles_desde_hoy,
    obtener_detalle_tmdb,
    obtener_ids_peliculas_con_sesiones_futuras,
    reforzar_minimo_diario_cartelera,
)


class Command(BaseCommand):
    help = "Comprueba y corrige sesiones futuras de películas en cartelera."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Intenta crear las sesiones diarias que falten.",
        )

    def handle(self, *args, **options):
        dias = construir_dias_disponibles_desde_hoy(7)
        fechas = [
            datetime.strptime(dia["fecha"], "%Y-%m-%d").date()
            for dia in dias
        ]

        ids = obtener_ids_peliculas_con_sesiones_futuras(
            limite=MAX_PELICULAS_CARTELERA
        )

        peliculas = []
        for movie_id in ids:
            try:
                detalle = obtener_detalle_tmdb(movie_id, exigir_datos_cartelera=False)
                peliculas.append(detalle)
            except Exception:
                peliculas.append({"id": movie_id, "title": f"Película {movie_id}"})

        if options["fix"]:
            reforzar_minimo_diario_cartelera(
                peliculas=peliculas,
                dias_disponibles=dias,
            )

        total_fallos = 0

        for pelicula in peliculas:
            movie_id = pelicula.get("id")
            titulo = pelicula.get("title") or f"Película {movie_id}"
            fechas_sin_sesion = []

            for fecha in fechas:
                existe = SesionCine.objects.filter(
                    movie_id=movie_id,
                    fecha=fecha,
                    inicio__isnull=False,
                    inicio__gt=timezone.now(),
                ).exists()

                if not existe:
                    fechas_sin_sesion.append(str(fecha))

            if fechas_sin_sesion:
                total_fallos += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"{titulo} ({movie_id}) sin sesión en: {', '.join(fechas_sin_sesion)}"
                    )
                )

        if total_fallos == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "Programación correcta: todas las películas revisadas tienen sesiones en la ventana visible."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"Películas con días sin sesión: {total_fallos}")
            )
