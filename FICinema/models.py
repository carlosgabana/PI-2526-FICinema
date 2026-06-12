from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Usuario(AbstractUser):
    GENERO_CHOICES = [
        ("M", "Masculino"),
        ("F", "Femenino"),
        ("O", "Otro"),
        ("N", "Prefiero no decirlo"),
    ]

    codigo = models.PositiveBigIntegerField(unique=True, editable=False)
    fechaNacimiento = models.DateField(null=True, blank=True)
    socio = models.BooleanField(default=False)
    genero = models.CharField(
        max_length=1,
        choices=GENERO_CHOICES,
        default="N",
        blank=True,
    )

    def save(self, *args, **kwargs):
        if not self.pk:
            ultimo_usuario = Usuario.objects.order_by("codigo").last()

            if ultimo_usuario and ultimo_usuario.codigo is not None:
                self.codigo = ultimo_usuario.codigo + 1
            else:
                self.codigo = 1

        super(Usuario, self).save(*args, **kwargs)

    def __str__(self):
        return (
            f"Código = {self.codigo} | "
            f"Nombre = {self.first_name} {self.last_name} | "
            f"Usuario = {self.username} | "
            f"Socio = {'Sí' if self.socio else 'No'} | "
            f"Género = {self.get_genero_display()}"
        )


class Bono(models.Model):
    codigo = models.PositiveBigIntegerField(unique=True, editable=False)

    TIPOS_BONO = [
        ("5 EN 3", "Ves 5 pagas 3"),
        ("10 EN 5", "Ves 10 pagas 5"),
        ("20 EN 10", "Ves 20 pagas 10"),
    ]

    USOS_POR_TIPO = {
        "5 EN 3": 5,
        "10 EN 5": 10,
        "20 EN 10": 20,
    }

    tipo = models.CharField(max_length=20, choices=TIPOS_BONO)
    fechaCaducidad = models.DateField()
    usos_restantes = models.PositiveIntegerField(default=0)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bonos",
    )

    def asignar_codigo(self):
        ultimo_bono = Bono.objects.order_by("codigo").last()

        if ultimo_bono and ultimo_bono.codigo is not None:
            self.codigo = ultimo_bono.codigo + 1
        else:
            self.codigo = 1

    def asignar_usos_iniciales(self):
        if self.usos_restantes == 0:
            self.usos_restantes = self.USOS_POR_TIPO.get(self.tipo, 0)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.asignar_codigo()
            self.asignar_usos_iniciales()

        super(Bono, self).save(*args, **kwargs)

    def __str__(self):
        return (
            f"Código = {self.codigo} | "
            f"Bono = {self.tipo} | "
            f"Usos restantes = {self.usos_restantes} | "
            f"Usuario = {self.usuario.username} | "
            f"Fecha de Caducidad = {self.fechaCaducidad}"
        )

class Sala(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    filas = models.PositiveIntegerField(default=6)
    columnas = models.PositiveIntegerField(default=8)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.nombre} ({self.filas}x{self.columnas})"

    def obtener_asientos(self):
        """
        Genera los asientos de la sala a partir de sus filas y columnas.

        Ejemplo:
        filas = 3, columnas = 4
        A1 A2 A3 A4
        B1 B2 B3 B4
        C1 C2 C3 C4
        """
        letras = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        asientos = []

        for indice_fila in range(self.filas):
            letra_fila = letras[indice_fila]

            for columna in range(1, self.columnas + 1):
                asientos.append(f"{letra_fila}{columna}")

        return asientos

    def asiento_existe(self, asiento):
        return asiento in self.obtener_asientos()


class SesionCine(models.Model):
    movie_id = models.PositiveBigIntegerField()
    titulo_pelicula = models.CharField(max_length=255)

    fecha = models.DateField()
    hora = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Campo auxiliar para mostrar la hora en formato HH:MM.",
    )

    inicio = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora real de inicio de la sesión.",
    )
    fin = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora real de finalización de la sesión, incluyendo limpieza.",
    )

    duracion_minutos = models.PositiveIntegerField(
        default=120,
        help_text="Duración real de la película en minutos obtenida de TMDB.",
    )
    margen_limpieza_minutos = models.PositiveIntegerField(
        default=20,
        help_text="Margen de limpieza entre sesiones.",
    )

    popularidad = models.FloatField(default=0)
    valoracion = models.FloatField(default=0)
    fecha_estreno = models.DateField(null=True, blank=True)
    demanda_estimada = models.FloatField(default=0)

    sala = models.ForeignKey(
        Sala,
        on_delete=models.CASCADE,
        related_name="sesiones",
    )

    creada_en = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ["fecha", "inicio", "sala__id"]
        indexes = [
            models.Index(fields=["fecha", "sala"]),
            models.Index(fields=["movie_id", "fecha"]),
            models.Index(fields=["inicio", "fin"]),
            models.Index(fields=["sala", "inicio", "fin"]),
            models.Index(fields=["movie_id", "fecha", "inicio", "fin"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sala", "inicio"],
                name="sesion_unica_por_sala_e_inicio",
            )
        ]

    def clean(self):
        if self.inicio and self.fin and self.fin <= self.inicio:
            raise ValidationError(
                "La hora de fin de la sesión debe ser posterior a la hora de inicio."
            )

    def save(self, *args, **kwargs):
        if self.inicio:
            self.fecha = timezone.localtime(self.inicio).date()
            self.hora = timezone.localtime(self.inicio).strftime("%H:%M")

        super(SesionCine, self).save(*args, **kwargs)

    def se_solapa_con_intervalo(self, inicio_nuevo, fin_nuevo):
        """
        Devuelve True si esta sesión se solapa con otro intervalo.

        Hay solapamiento cuando:
        inicio_nuevo < fin_existente
        y
        fin_nuevo > inicio_existente
        """
        if not self.inicio or not self.fin:
            return False

        return inicio_nuevo < self.fin and fin_nuevo > self.inicio

    def hora_inicio_formateada(self):
        if self.inicio:
            return timezone.localtime(self.inicio).strftime("%H:%M")

        return self.hora

    def hora_fin_formateada(self):
        if self.fin:
            return timezone.localtime(self.fin).strftime("%H:%M")

        return "No disponible"

    def __str__(self):
        return (
            f"{self.titulo_pelicula} | "
            f"{self.fecha} {self.hora_inicio_formateada()} | "
            f"{self.sala.nombre}"
        )


class Favorito(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favoritos",
    )
    movie_id = models.PositiveBigIntegerField()
    titulo = models.CharField(max_length=255)
    sinopsis = models.TextField(blank=True, default="")
    poster_url = models.URLField(max_length=500, blank=True, default="")
    fecha_estreno = models.CharField(max_length=30, blank=True, default="")
    valoracion = models.FloatField(default=0)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "movie_id"],
                name="favorito_unico_por_usuario_y_pelicula",
            )
        ]
        indexes = [
            models.Index(fields=["usuario", "-creado_en"]),
            models.Index(fields=["movie_id"]),
        ]

    def __str__(self):
        return f"{self.usuario.username} | {self.titulo} ({self.movie_id})"


class Resena(models.Model):
    PUNTUACION_CHOICES = [(valor, str(valor)) for valor in range(1, 6)]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resenas",
    )
    movie_id = models.PositiveBigIntegerField()
    titulo_pelicula = models.CharField(max_length=255)
    puntuacion = models.PositiveSmallIntegerField(choices=PUNTUACION_CHOICES)
    comentario = models.TextField(max_length=600, blank=True, default="")
    visible = models.BooleanField(default=True)
    creada_en = models.DateTimeField(default=timezone.now)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizada_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "movie_id"],
                name="resena_unica_por_usuario_y_pelicula",
            )
        ]
        indexes = [
            models.Index(fields=["movie_id", "visible", "-actualizada_en"]),
            models.Index(fields=["usuario", "-actualizada_en"]),
            models.Index(fields=["puntuacion"]),
        ]

    def clean(self):
        if self.puntuacion < 1 or self.puntuacion > 5:
            raise ValidationError("La puntuación debe estar entre 1 y 5.")

    def __str__(self):
        return f"{self.usuario.username} | {self.titulo_pelicula} | {self.puntuacion}/5"


class Entrada(models.Model):
    ESTADO_ACTIVA = "ACTIVA"
    ESTADO_USADA = "USADA"
    ESTADO_CADUCADA = "CADUCADA"
    ESTADO_CANCELADA = "CANCELADA"

    ESTADO_CHOICES = [
        (ESTADO_ACTIVA, "Activa"),
        (ESTADO_USADA, "Usada"),
        (ESTADO_CADUCADA, "Caducada"),
        (ESTADO_CANCELADA, "Cancelada"),
    ]

    codigo = models.PositiveBigIntegerField(unique=True, editable=False)

    sesion = models.ForeignKey(
        SesionCine,
        on_delete=models.PROTECT,
        related_name="entradas",
        null=True,
        blank=True,
    )

    movie_id = models.PositiveBigIntegerField()
    titulo_pelicula = models.CharField(max_length=255)
    fecha = models.DateField()
    hora = models.CharField(max_length=10)

    sala = models.ForeignKey(
        Sala,
        on_delete=models.PROTECT,
        related_name="entradas",
        null=True,
        blank=True,
    )

    asiento = models.CharField(max_length=5, default="A1")
    fechaCompra = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_ACTIVA,
    )

    bono_usado = models.ForeignKey(
        Bono,
        on_delete=models.SET_NULL,
        related_name="entradas_usadas",
        null=True,
        blank=True,
    )

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="entradas",
    )

    class Meta:
        ordering = ["-fechaCompra"]
        constraints = [
            models.UniqueConstraint(
                fields=["sesion", "asiento"],
                condition=~models.Q(estado="CANCELADA"),
                name="entrada_asiento_unico_por_sesion_activa",
            )
        ]

    def clean(self):
        if self.sesion and self.asiento:
            if not self.sesion.sala.asiento_existe(self.asiento):
                raise ValidationError(
                    "El asiento seleccionado no existe en la sala de esta sesión."
                )

    def ha_finalizado(self):
        return bool(self.sesion and self.sesion.fin and self.sesion.fin <= timezone.now())

    def puede_cancelarse(self):
        return (
            self.estado == self.ESTADO_ACTIVA
            and self.sesion
            and self.sesion.inicio
            and self.sesion.inicio > timezone.now()
        )

    def marcar_caducada_si_corresponde(self):
        if self.estado == self.ESTADO_ACTIVA and self.ha_finalizado():
            self.estado = self.ESTADO_CADUCADA
            self.save(update_fields=["estado"])

    def cancelar_y_devolver_bono(self):
        if not self.puede_cancelarse():
            raise ValidationError("Esta entrada no se puede cancelar.")

        self.estado = self.ESTADO_CANCELADA
        self.save(update_fields=["estado"])

        if self.bono_usado:
            self.bono_usado.usos_restantes += 1
            self.bono_usado.save(update_fields=["usos_restantes"])

    def save(self, *args, **kwargs):
        if not self.pk:
            ultima_entrada = Entrada.objects.order_by("codigo").last()

            if ultima_entrada and ultima_entrada.codigo is not None:
                self.codigo = ultima_entrada.codigo + 1
            else:
                self.codigo = 1

        if self.sesion:
            self.movie_id = self.sesion.movie_id
            self.titulo_pelicula = self.sesion.titulo_pelicula
            self.fecha = self.sesion.fecha
            self.hora = self.sesion.hora_inicio_formateada()
            self.sala = self.sesion.sala

        super(Entrada, self).save(*args, **kwargs)

    def __str__(self):
        nombre_sala = self.sala.nombre if self.sala else "Sin sala"

        return (
            f"Código = {self.codigo} | "
            f"Película = {self.titulo_pelicula} | "
            f"Fecha = {self.fecha} | "
            f"Hora = {self.hora} | "
            f"Sala = {nombre_sala} | "
            f"Asiento = {self.asiento} | "
            f"Estado = {self.estado} | "
            f"Usuario = {self.usuario.username}"
        )

class ValidacionEntrada(models.Model):
    RESULTADO_VALIDA = "VALIDA"
    RESULTADO_YA_USADA = "YA_USADA"
    RESULTADO_CANCELADA = "CANCELADA"
    RESULTADO_CADUCADA = "CADUCADA"
    RESULTADO_NO_ENCONTRADA = "NO_ENCONTRADA"
    RESULTADO_SIN_PERMISO = "SIN_PERMISO"
    RESULTADO_ERROR = "ERROR"

    RESULTADO_CHOICES = [
        (RESULTADO_VALIDA, "Válida"),
        (RESULTADO_YA_USADA, "Ya usada"),
        (RESULTADO_CANCELADA, "Cancelada"),
        (RESULTADO_CADUCADA, "Caducada"),
        (RESULTADO_NO_ENCONTRADA, "No encontrada"),
        (RESULTADO_SIN_PERMISO, "Sin permiso"),
        (RESULTADO_ERROR, "Error"),
    ]

    entrada = models.ForeignKey(
        Entrada,
        on_delete=models.SET_NULL,
        related_name="validaciones",
        null=True,
        blank=True,
    )
    codigo_verificacion = models.CharField(max_length=80)
    resultado = models.CharField(max_length=20, choices=RESULTADO_CHOICES)
    detalle = models.CharField(max_length=255, blank=True)
    usuario_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="validaciones_entrada",
        null=True,
        blank=True,
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-id"]
        indexes = [
            models.Index(fields=["entrada", "-creado_en"]),
            models.Index(fields=["resultado", "-creado_en"]),
            models.Index(fields=["usuario_staff", "-creado_en"]),
        ]

    def __str__(self):
        staff = self.usuario_staff.username if self.usuario_staff else "sin staff"
        return f"{self.codigo_verificacion} | {self.resultado} | {staff}"

