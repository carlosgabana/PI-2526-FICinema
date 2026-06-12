from django.urls import path

from . import views

urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),
    path("", views.index_peliculas, name="home"),
    path("peliculas/", views.index_peliculas, name="index_peliculas"),
    path("peliculas/<int:movie_id>/", views.detalle_pelicula, name="detalle_pelicula"),
    path("peliculas/<int:movie_id>/resenas/guardar/", views.guardar_resena, name="guardar_resena"),
    path("peliculas/<int:movie_id>/resenas/eliminar/", views.eliminar_resena, name="eliminar_resena"),

    path("entradas/", views.mis_entradas, name="mis_entradas"),
    path("entradas/confirmar/", views.confirmar_entrada, name="confirmar_entrada"),
    path("entradas/comprar/", views.comprar_entrada, name="comprar_entrada"),
    path("entradas/<int:entrada_id>/cancelar/", views.cancelar_entrada, name="cancelar_entrada"),
    path("entradas/<int:entrada_id>/qr/", views.qr_entrada, name="qr_entrada"),
    path("entradas/<int:entrada_id>/pdf/", views.descargar_entrada_pdf, name="descargar_entrada_pdf"),
    path("entrada/verificar/<str:codigo_verificacion>/", views.verificar_entrada, name="verificar_entrada"),

    path("favoritos/", views.mis_favoritos, name="mis_favoritos"),
    path("recomendaciones/", views.mis_recomendaciones, name="mis_recomendaciones"),
    path("favoritos/alternar/", views.alternar_favorito, name="alternar_favorito"),

    path(
        "panel-interno/entradas/<int:entrada_id>/cancelar/",
        views.cancelar_entrada_staff,
        name="cancelar_entrada_staff"
    ),

    path("registro/", views.registro, name="registro"),
    path("login/", views.iniciar_sesion, name="login"),
    path("logout/", views.cerrar_sesion, name="logout"),
    path("perfil/", views.perfil, name="perfil"),
    path("editar-perfil/", views.editar_perfil, name="editar_perfil"),

    path("socio/", views.socio, name="socio"),
    path("baja-socio/", views.baja_socio, name="baja_socio"),
    path("bonos/", views.bonos, name="bonos"),
    path("confirmar-bono/<str:tipo>/", views.confirmar_bono, name="confirmar_bono"),
    path("comprar-bono/<str:tipo>/", views.comprar_bono, name="comprar_bono"),

    path("estadisticas/", views.estadisticas, name="estadisticas"),
    path("estadisticas/exportar/csv/", views.exportar_estadisticas_csv, name="exportar_estadisticas_csv"),
    path("estadisticas/exportar/pdf/", views.exportar_estadisticas_pdf, name="exportar_estadisticas_pdf"),

    path("panel-interno/", views.panel_interno, name="panel_interno"),
    path("panel-interno/estado/", views.panel_estado_sistema, name="panel_estado_sistema"),
    path("panel-interno/regenerar-cartelera/", views.regenerar_cartelera_staff, name="regenerar_cartelera_staff"),
    path("panel-interno/sesiones/", views.panel_sesiones, name="panel_sesiones"),
    path("panel-interno/entradas/", views.panel_entradas, name="panel_entradas"),
    path("panel-interno/escanear-qr/", views.escanear_qr_staff, name="escanear_qr_staff"),
    path("panel-interno/bonos/", views.panel_bonos, name="panel_bonos"),
    path("panel-interno/resenas/", views.panel_resenas, name="panel_resenas"),
    path("panel-interno/resenas/<int:resena_id>/visibilidad/", views.cambiar_visibilidad_resena, name="cambiar_visibilidad_resena"),
    path("panel-interno/usuarios/", views.panel_usuarios, name="panel_usuarios"),

    path("validar-registro/", views.validar_registro, name="validar_registro"),
    path("ubicacion-cine/", views.ubicacion_cine, name="ubicacion_cine"),

    path("entradas/pago/", views.pago_entrada, name="pago_entrada"),
    path("entradas/pago/procesar/", views.procesar_pago, name="procesar_pago"),
]