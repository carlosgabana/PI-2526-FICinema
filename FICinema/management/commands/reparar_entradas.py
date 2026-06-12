from django.core.management.base import BaseCommand
from django.utils import timezone

from FICinema.models import Entrada


class Command(BaseCommand):
    help = "Repara entradas activas/caducadas según la fecha real de la sesión."

    def handle(self, *args, **options):
        ahora = timezone.now()

        reactivadas = Entrada.objects.filter(
            estado=Entrada.ESTADO_CADUCADA,
            sesion__fin__gt=ahora,
        ).update(estado=Entrada.ESTADO_ACTIVA)

        caducadas = Entrada.objects.filter(
            estado=Entrada.ESTADO_ACTIVA,
            sesion__fin__lte=ahora,
        ).update(estado=Entrada.ESTADO_CADUCADA)

        self.stdout.write(
            self.style.SUCCESS(
                f"Entradas reactivadas: {reactivadas}. Entradas caducadas correctamente: {caducadas}."
            )
        )
