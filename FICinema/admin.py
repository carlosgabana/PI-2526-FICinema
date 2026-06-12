from django.contrib import admin
from .models import Bono, Entrada, Favorito, Resena, Sala, SesionCine, Usuario

@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ('codigo','username','first_name','last_name',
                    'email','fechaNacimiento','socio')
    list_filter = ('socio',)
    search_fields = ('username','first_name','last_name','email')

@admin.register(Bono)
class BonoAdmin(admin.ModelAdmin):
    list_display = ('codigo','tipo','usuario','fechaCaducidad')
    list_filter = ('tipo','fechaCaducidad')
    search_fields = ('usuario__username',)


@admin.register(Favorito)
class FavoritoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "movie_id", "titulo", "valoracion", "fecha_estreno", "creado_en")
    list_filter = ("creado_en",)
    search_fields = ("usuario__username", "titulo", "movie_id")
    readonly_fields = ("creado_en",)


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "filas", "columnas", "activa")
    list_filter = ("activa",)
    search_fields = ("nombre",)


@admin.register(SesionCine)
class SesionCineAdmin(admin.ModelAdmin):
    list_display = ("titulo_pelicula", "fecha", "hora_inicio_formateada", "sala", "duracion_minutos")
    list_filter = ("fecha", "sala")
    search_fields = ("titulo_pelicula", "movie_id")


@admin.register(Entrada)
class EntradaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "usuario", "titulo_pelicula", "fecha", "hora", "sala", "asiento", "estado")
    list_filter = ("estado", "fecha", "sala")
    search_fields = ("codigo", "usuario__username", "titulo_pelicula")


@admin.register(Resena)
class ResenaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "titulo_pelicula", "movie_id", "puntuacion", "visible", "actualizada_en")
    list_filter = ("visible", "puntuacion", "actualizada_en")
    search_fields = ("usuario__username", "titulo_pelicula", "comentario", "movie_id")
    readonly_fields = ("creada_en", "actualizada_en")
    actions = ("marcar_como_visible", "marcar_como_oculta")

    @admin.action(description="Marcar reseñas como visibles")
    def marcar_como_visible(self, request, queryset):
        queryset.update(visible=True)

    @admin.action(description="Ocultar reseñas seleccionadas")
    def marcar_como_oculta(self, request, queryset):
        queryset.update(visible=False)
