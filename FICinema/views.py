import csv
import os
import re
import sys
import uuid
import hashlib
import stripe
import json
import logging
import threading
from io import BytesIO
from urllib.parse import quote, urlparse, urlencode
from xml.sax.saxutils import escape
from datetime import date, datetime, time, timedelta
from collections import defaultdict

from django.core.cache import cache
from django.core.mail import EmailMessage
from django.core.exceptions import ValidationError
from django.core import signing
import pandas as pd
import requests
import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction, close_old_connections, connection
from django.db.models import Avg, Count, Min, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import EditarPerfilForm, RegistroUsuarioForm
from .models import Bono, Entrada, Favorito, Resena, Sala, SesionCine, Usuario, ValidacionEntrada


logger = logging.getLogger(__name__)

PRECIO_ENTRADA = 8.50

DIAS_SEMANA = [
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
]

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]

MARGEN_LIMPIEZA_MINUTOS = 20
DURACION_POR_DEFECTO = 120

HORA_APERTURA_ENTRE_SEMANA = time(16, 0)
HORA_APERTURA_FIN_DE_SEMANA = time(11, 0)
HORA_CIERRE = time(1, 30)

VENTANAS_DIA_ENTRE_SEMANA = [
    (16, 0),
    (17, 30),
    (19, 30),
    (21, 30),
    (22, 30),
]

VENTANAS_DIA_FIN_DE_SEMANA = [
    (11, 30),
    (13, 0),
    (16, 0),
    (17, 30),
    (19, 30),
    (21, 30),
    (22, 30),
]

MAX_PELICULAS_CARTELERA = 20
MIN_SESIONES_POR_PELICULA = 1
MAX_SESIONES_DIA_LABORABLE = 5
MAX_SESIONES_FIN_DE_SEMANA = 6

PRECIOS_BONO = {
    "5 EN 3":   25.50,
    "10 EN 5":  42.50,
    "20 EN 10": 85.00,
}

TMDB_GENEROS = {
    12: "Aventura",
    14: "Fantasía",
    16: "Animación",
    18: "Drama",
    27: "Terror",
    28: "Acción",
    35: "Comedia",
    36: "Historia",
    37: "Western",
    53: "Suspense",
    80: "Crimen",
    99: "Documental",
    878: "Ciencia ficción",
    9648: "Misterio",
    10402: "Música",
    10749: "Romance",
    10751: "Familia",
    10752: "Bélica",
    10770: "TV Movie",
}



TITULAR_PAGO_REGEX = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ .'-]{1,59}$")


def normalizar_titular_pago(titular):
    return re.sub(r"\s+", " ", (titular or "").strip())


def validar_titular_pago(titular):
    titular_normalizado = normalizar_titular_pago(titular)

    if not titular_normalizado:
        return False, "Introduce el nombre del titular de la tarjeta."

    if len(titular_normalizado) < 3 or len(titular_normalizado) > 60:
        return False, "El titular debe tener entre 3 y 60 caracteres."

    if any(caracter.isdigit() for caracter in titular_normalizado):
        return False, "El titular no puede contener números."

    if not TITULAR_PAGO_REGEX.match(titular_normalizado):
        return False, "El titular solo puede contener letras, espacios, puntos, apóstrofes o guiones."

    return True, ""



def construir_cache_key_segura(prefijo, valor):
    valor_limpio = re.sub(r"[^A-Za-z0-9_.:-]", "_", str(valor))
    return f"{prefijo}_{valor_limpio}"


def ejecutando_tests():
    return "test" in sys.argv


def formatear_fecha_es(fecha):
    dia_semana = DIAS_SEMANA[fecha.weekday()]
    mes = MESES[fecha.month - 1]

    return f"{dia_semana.capitalize()} {fecha.day:02d} de {mes}"


def construir_headers_tmdb():
    headers = {
        "accept": "application/json",
    }

    tmdb_token = os.getenv("TMDB_ACCESS_TOKEN")

    if tmdb_token:
        headers["Authorization"] = f"Bearer {tmdb_token}"

    return headers


def hacer_datetime_consciente(fecha, hora):
    fecha_hora = datetime.combine(fecha, hora)

    if timezone.is_naive(fecha_hora):
        fecha_hora = timezone.make_aware(fecha_hora)

    return fecha_hora


def redondear_a_5_minutos(fecha_hora):
    minutos = fecha_hora.minute
    resto = minutos % 5

    if resto == 0:
        return fecha_hora.replace(second=0, microsecond=0)

    minutos_a_sumar = 5 - resto
    fecha_hora = fecha_hora + timedelta(minutes=minutos_a_sumar)

    return fecha_hora.replace(second=0, microsecond=0)


def es_fin_de_semana(fecha_sesion):
    return fecha_sesion.weekday() >= 5


def obtener_apertura(fecha_sesion):
    if es_fin_de_semana(fecha_sesion):
        return hacer_datetime_consciente(fecha_sesion, HORA_APERTURA_FIN_DE_SEMANA)

    return hacer_datetime_consciente(fecha_sesion, HORA_APERTURA_ENTRE_SEMANA)


def obtener_cierre(fecha_sesion):
    dia_cierre = fecha_sesion + timedelta(days=1)
    return hacer_datetime_consciente(dia_cierre, HORA_CIERRE)


def crear_salas_iniciales():
    """
    Para ampliar salas, añade aquí nuevas líneas.
    Ejemplo:
    {"nombre": "Sala 11", "filas": 8, "columnas": 14}
    """
    salas_base = [
    {"nombre": "Sala 1", "filas": 6, "columnas": 8},
    {"nombre": "Sala 2", "filas": 6, "columnas": 8},
    {"nombre": "Sala 3", "filas": 7, "columnas": 10},
    {"nombre": "Sala 4", "filas": 5, "columnas": 8},
    {"nombre": "Sala 5", "filas": 5, "columnas": 10},
    {"nombre": "Sala 6", "filas": 4, "columnas": 6},
    {"nombre": "Sala 7", "filas": 8, "columnas": 10},
    {"nombre": "Sala 8", "filas": 7, "columnas": 9},
    {"nombre": "Sala 9", "filas": 6, "columnas": 10},
    {"nombre": "Sala 10", "filas": 8, "columnas": 12},
    {"nombre": "Sala 11", "filas": 6, "columnas": 8},
    {"nombre": "Sala 12", "filas": 7, "columnas": 10},
    {"nombre": "Sala 13", "filas": 5, "columnas": 10},
    {"nombre": "Sala 14", "filas": 8, "columnas": 12},
]

    for sala_data in salas_base:
        sala, creada = Sala.objects.get_or_create(
            nombre=sala_data["nombre"],
            defaults={
                "filas": sala_data["filas"],
                "columnas": sala_data["columnas"],
                "activa": True,
            },
        )

        if not creada:
            sala.filas = sala_data["filas"]
            sala.columnas = sala_data["columnas"]
            sala.activa = True
            sala.save(update_fields=["filas", "columnas", "activa"])


def texto_api_valido(valor):
    if valor is None:
        return False

    texto = str(valor).strip()

    return bool(texto) and texto.lower() not in {
        "n/a",
        "none",
        "null",
        "sin sinopsis disponible.",
        "sin sinopsis disponible",
        "sin vídeo disponible",
        "sin video disponible",
    }

def obtener_origen_publico_request(request):
    origen_configurado = (getattr(settings, "PUBLIC_BASE_URL", "") or "").strip().rstrip("/")

    if origen_configurado:
        return origen_configurado

    for cabecera in ("HTTP_ORIGIN", "HTTP_REFERER"):
        valor = (request.META.get(cabecera) or "").strip()
        if not valor:
            continue

        parsed = urlparse(valor)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

    host_proxy = (
        request.META.get("HTTP_X_FORWARDED_HOST")
        or request.META.get("HTTP_X_ORIGINAL_HOST")
        or ""
    ).split(",")[0].strip()

    if host_proxy:
        protocolo = (request.META.get("HTTP_X_FORWARDED_PROTO") or request.scheme or "https").split(",")[0].strip()
        return f"{protocolo}://{host_proxy}"

    return f"{request.scheme}://{request.get_host()}"


def construir_url_publica(request, path):
    if not path.startswith("/"):
        path = f"/{path}"

    return f"{obtener_origen_publico_request(request)}{path}"


def construir_url_verificacion_entrada(entrada, request=None):
    codigo_verificacion = construir_codigo_verificacion_entrada(entrada)
    path = reverse("verificar_entrada", args=[codigo_verificacion])

    if request is not None:
        return construir_url_publica(request, path)

    origen_configurado = (getattr(settings, "PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if origen_configurado:
        return f"{origen_configurado}{path}"

    return path


@require_GET
def healthz(request):
    return JsonResponse({"status": "ok"})


def ubicacion_cine(request):
    api_key_google_maps = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    direccion_cine = "Facultad de Informática, Campus de Elviña, s/n, 15071 A Coruña"
    maps_query = urlencode({"api": "1", "destination": direccion_cine, "travelmode": "driving"})
    maps_directions_url = f"https://www.google.com/maps/dir/?{maps_query}"
    maps_place_url = f"https://www.google.com/maps/search/?{urlencode({'api': '1', 'query': direccion_cine})}"

    return render(
        request,
        "ubicacion_cine.html",
        {
            "api_key_google_maps": api_key_google_maps,
            "direccion_cine": direccion_cine,
            "maps_directions_url": maps_directions_url,
            "maps_place_url": maps_place_url,
        },
    )

def obtener_trailer_key_desde_detalle(detalle):
    videos = detalle.get("videos", {}) or {}
    resultados = videos.get("results", []) or []

    for video in resultados:
        if (
            video.get("site") == "YouTube"
            and video.get("type") == "Trailer"
            and video.get("official") is True
            and texto_api_valido(video.get("key"))
        ):
            return video.get("key")

    for video in resultados:
        if (
            video.get("site") == "YouTube"
            and video.get("type") == "Trailer"
            and texto_api_valido(video.get("key"))
        ):
            return video.get("key")

    if texto_api_valido(detalle.get("youtube_trailer_key")):
        return detalle.get("youtube_trailer_key")

    return None

def obtener_anio_desde_fecha(fecha_texto):
    if not texto_api_valido(fecha_texto):
        return ""

    match = re.match(r"^(\d{4})", str(fecha_texto).strip())
    return match.group(1) if match else ""


def construir_consultas_youtube_trailer(titulo, fecha_estreno=""):
    """Genera consultas de búsqueda robustas para encontrar tráileres reales."""
    titulo = str(titulo or "").strip()
    anio = obtener_anio_desde_fecha(fecha_estreno)

    if not titulo:
        return []

    
    titulo_sin_parentesis = re.sub(r"\s*\([^)]*\)", "", titulo).strip()
    variantes_titulo = [titulo]

    if titulo_sin_parentesis and titulo_sin_parentesis.lower() != titulo.lower():
        variantes_titulo.append(titulo_sin_parentesis)

    consultas = []

    for base in variantes_titulo:
        if anio:
            consultas.extend(
                [
                    f"{base} {anio} trailer español",
                    f"{base} {anio} tráiler oficial español",
                    f"{base} {anio} official trailer",
                ]
            )

        consultas.extend(
            [
                f"{base} trailer español",
                f"{base} tráiler oficial",
                f"{base} official trailer",
            ]
        )

    
    consultas_unicas = []
    vistas = set()

    for consulta in consultas:
        clave = consulta.lower().strip()
        if clave and clave not in vistas:
            vistas.add(clave)
            consultas_unicas.append(consulta.strip())

    return consultas_unicas


def puntuar_resultado_youtube(item, titulo, fecha_estreno=""):
    """Puntúa resultados para evitar clips, teasers o vídeos poco relacionados."""
    snippet = item.get("snippet") or {}
    video_title = (snippet.get("title") or "").lower()
    descripcion = (snippet.get("description") or "").lower()
    texto = f"{video_title} {descripcion}"
    titulo_limpio = str(titulo or "").lower()
    titulo_sin_parentesis = re.sub(r"\s*\([^)]*\)", "", titulo_limpio).strip()
    anio = obtener_anio_desde_fecha(fecha_estreno)

    puntos = 0

    
    palabras_titulo = [
        palabra
        for palabra in re.split(r"\W+", titulo_sin_parentesis or titulo_limpio)
        if len(palabra) >= 3
    ]

    coincidencias = sum(1 for palabra in palabras_titulo if palabra in texto)
    puntos += coincidencias * 3

    if titulo_limpio and titulo_limpio in texto:
        puntos += 12

    if titulo_sin_parentesis and titulo_sin_parentesis in texto:
        puntos += 10

    
    if "trailer" in texto or "tráiler" in texto:
        puntos += 15

    if "oficial" in texto or "official" in texto:
        puntos += 6

    if "español" in texto or "spanish" in texto or "castellano" in texto:
        puntos += 4

    if anio and anio in texto:
        puntos += 5

    
    penalizaciones = [
        "teaser",
        "clip",
        "escena",
        "scene",
        "review",
        "crítica",
        "reaction",
        "reaccion",
        "making of",
        "behind the scenes",
        "soundtrack",
        "music video",
        "shorts",
    ]

    for palabra in penalizaciones:
        if palabra in texto:
            puntos -= 8

    return puntos


def buscar_trailer_youtube(titulo, fecha_estreno=""):
    """
    Respaldo opcional para tráileres cuando TMDB no devuelve vídeos.

    Busca varias consultas, puntúa los resultados y cachea el mejor vídeo.
    No se ejecuta en tests para no interferir con los mocks de TMDB.
    """
    if ejecutando_tests():
        return None

    api_key_youtube = getattr(settings, "YOUTUBE_API_KEY", None) or os.getenv("YOUTUBE_API_KEY")

    if not api_key_youtube or not texto_api_valido(titulo):
        return None

    consultas = construir_consultas_youtube_trailer(titulo, fecha_estreno)
    cadena_consultas = "|".join(consultas)
    hash_consultas = hashlib.md5(cadena_consultas.encode("utf-8")).hexdigest()
    cache_key = construir_cache_key_segura("youtube_trailer_v2", hash_consultas)
    cacheado = cache.get(cache_key)

    if cacheado is not None:
        return cacheado or None

    url = "https://www.googleapis.com/youtube/v3/search"
    candidatos = []

    for consulta in consultas:
        params = {
            "part": "snippet",
            "q": consulta,
            "key": api_key_youtube,
            "type": "video",
            "maxResults": 5,
            "safeSearch": "moderate",
            "videoEmbeddable": "true",
            "relevanceLanguage": "es",
        }

        try:
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            continue

        for item in data.get("items", []) or []:
            video_id = (item.get("id") or {}).get("videoId")

            if not texto_api_valido(video_id):
                continue

            puntuacion = puntuar_resultado_youtube(item, titulo, fecha_estreno)

            if puntuacion >= 8:
                candidatos.append((puntuacion, video_id))

        if candidatos:
            break

    if candidatos:
        candidatos.sort(reverse=True, key=lambda dato: dato[0])
        mejor_video = candidatos[0][1]
        cache.set(cache_key, mejor_video, 60 * 60 * 24)
        return mejor_video

    cache.set(cache_key, "", 60 * 20)
    return None

def completar_trailer_con_youtube(detalle):
    """Añade un vídeo de YouTube como respaldo si TMDB no tiene tráiler."""
    detalle = dict(detalle or {})

    if obtener_trailer_key_desde_detalle(detalle):
        detalle["trailer_origen"] = detalle.get("trailer_origen") or "TMDB"
        return detalle

    titulo = detalle.get("title") or detalle.get("original_title") or ""
    fecha_estreno = detalle.get("release_date") or ""
    video_id = buscar_trailer_youtube(titulo, fecha_estreno)

    if not video_id:
        detalle["trailer_origen"] = "No disponible"
        return detalle

    videos = dict(detalle.get("videos") or {})
    resultados = list(videos.get("results") or [])
    resultados.insert(
        0,
        {
            "site": "YouTube",
            "type": "Trailer",
            "key": video_id,
            "name": f"{titulo} - tráiler",
            "official": False,
            "source": "YouTube Data API",
        },
    )
    videos["results"] = resultados
    detalle["videos"] = videos
    detalle["youtube_trailer_key"] = video_id
    detalle["trailer_origen"] = "YouTube"
    return detalle


def construir_urls_youtube(video_key, request=None):
    """Construye URLs seguras de YouTube para embeber y abrir el tráiler."""
    if not texto_api_valido(video_key):
        return {
            "embed": "",
            "watch": "",
        }

    watch_url = f"https://www.youtube.com/watch?v={video_key}"
    embed_url = f"https://www.youtube.com/embed/{video_key}?rel=0&modestbranding=1"

    if request is not None:
        try:
            origen = f"{request.scheme}://{request.get_host()}"
            embed_url = f"{embed_url}&origin={quote(origen, safe=':/')}"
        except Exception:
            pass

    return {
        "embed": embed_url,
        "watch": watch_url,
    }


def detalle_tiene_ficha_minima(detalle):
    if not detalle:
        return False

    try:
        valoracion = float(detalle.get("vote_average") or 0)
    except (TypeError, ValueError):
        valoracion = 0

    try:
        duracion = int(detalle.get("runtime") or 0)
    except (TypeError, ValueError):
        duracion = 0

    return (
        texto_api_valido(detalle.get("title"))
        and texto_api_valido(detalle.get("overview"))
        and texto_api_valido(detalle.get("release_date"))
        and (texto_api_valido(detalle.get("poster_path")) or texto_api_valido(detalle.get("poster_url")))
        and valoracion > 0
        and duracion > 0
    )


def detalle_tiene_datos_minimos_cartelera(detalle):
    return detalle_tiene_ficha_minima(detalle) and obtener_trailer_key_desde_detalle(detalle) is not None

def obtener_respaldo_omdb(detalle_tmdb):
    api_key_omdb = getattr(settings, "OMDB_API_KEY", None)

    if not api_key_omdb:
        return {}

    titulo_busqueda = (
        detalle_tmdb.get("original_title")
        or detalle_tmdb.get("title")
        or ""
    ).strip()

    if not titulo_busqueda:
        return {}

    url_omdb = "http://www.omdbapi.com/"
    params = {
        "apikey": api_key_omdb,
        "t": titulo_busqueda,
        "plot": "full",
    }

    try:
        response_omdb = requests.get(url_omdb, params=params, timeout=4)
        response_omdb.raise_for_status()
        datos_omdb = response_omdb.json()
    except (requests.RequestException, ValueError):
        return {}

    if datos_omdb.get("Response") == "False":
        return {}

    return datos_omdb


def normalizar_fecha_omdb(fecha_omdb, fecha_respaldo=""):
    if not texto_api_valido(fecha_omdb):
        return fecha_respaldo

    for formato in ("%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(fecha_omdb.strip(), formato).date().strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            continue

    return fecha_respaldo


def normalizar_runtime_omdb(runtime_omdb, runtime_respaldo=0):
    if not texto_api_valido(runtime_omdb):
        return runtime_respaldo or 0

    try:
        return int(str(runtime_omdb).split()[0])
    except (TypeError, ValueError, IndexError):
        return runtime_respaldo or 0


def normalizar_valoracion_omdb(valoracion_omdb, valoracion_respaldo=0):
    if not texto_api_valido(valoracion_omdb):
        return valoracion_respaldo or 0

    try:
        return float(valoracion_omdb)
    except (TypeError, ValueError):
        return valoracion_respaldo or 0


def completar_detalle_con_omdb(detalle_tmdb):
    """
    Usa OMDb solo como respaldo de datos textuales.

    Importante: OMDb no aporta tráiler. Los tráileres se completan después
    con YouTube Data API solo si existe YOUTUBE_API_KEY.
    """
    detalle = dict(detalle_tmdb or {})

    datos_omdb = obtener_respaldo_omdb(detalle)

    if not datos_omdb:
        return detalle

    plot_omdb = datos_omdb.get("Plot")
    poster_omdb = datos_omdb.get("Poster")

    if not texto_api_valido(detalle.get("overview")) and texto_api_valido(plot_omdb):
        detalle["overview"] = plot_omdb.strip()

    if not texto_api_valido(detalle.get("release_date")):
        detalle["release_date"] = normalizar_fecha_omdb(
            datos_omdb.get("Released"),
            detalle.get("release_date", ""),
        )

    if not detalle.get("runtime"):
        detalle["runtime"] = normalizar_runtime_omdb(datos_omdb.get("Runtime"), 0)

    if not detalle.get("vote_average"):
        detalle["vote_average"] = normalizar_valoracion_omdb(datos_omdb.get("imdbRating"), 0)

    if not texto_api_valido(detalle.get("poster_path")) and texto_api_valido(poster_omdb):
        detalle["poster_url"] = poster_omdb.strip()

    if not texto_api_valido(detalle.get("title")) and texto_api_valido(datos_omdb.get("Title")):
        detalle["title"] = datos_omdb.get("Title").strip()

    detalle["respaldo_omdb_usado"] = True

    return detalle


def obtener_detalle_tmdb(movie_id, exigir_datos_cartelera=True):
    cache_key = f"tmdb_detalle_v2_{movie_id}_{'cartelera' if exigir_datos_cartelera else 'flex'}"
    detalle_cacheado = cache.get(cache_key)

    if detalle_cacheado:
        if detalle_cacheado == "INVALIDA":
            raise ValueError("Película descartada por datos incompletos en TMDB, OMDb y YouTube.")
        return detalle_cacheado

    api_key = settings.TMDB_API_KEY
    url = (
        f"https://api.themoviedb.org/3/movie/{movie_id}"
        f"?api_key={api_key}&language=es-ES&append_to_response=videos"
    )

    response = requests.get(url, headers=construir_headers_tmdb(), timeout=6)
    response.raise_for_status()
    detalle_tmdb = response.json()

    detalle = completar_detalle_con_omdb(detalle_tmdb)
    detalle = completar_trailer_con_youtube(detalle)

    if exigir_datos_cartelera and not detalle_tiene_datos_minimos_cartelera(detalle):
        cache.set(cache_key, "INVALIDA", 60 * 20)
        raise ValueError(
            "Película descartada por falta de ficha mínima o tráiler en TMDB/YouTube."
        )

    cache.set(cache_key, detalle, 60 * 60)
    return detalle

def obtener_peliculas_populares_tmdb(max_paginas=3):
    cache_key = f"tmdb_peliculas_populares_p{max_paginas}"
    peliculas_cacheadas = cache.get(cache_key)

    if peliculas_cacheadas:
        return peliculas_cacheadas

    api_key = settings.TMDB_API_KEY
    peliculas = []
    ids_usados = set()

    for pagina in range(1, max_paginas + 1):
        url = (
            f"https://api.themoviedb.org/3/movie/popular"
            f"?api_key={api_key}&language=es-ES&page={pagina}"
        )

        response = requests.get(url, headers=construir_headers_tmdb(), timeout=6)
        response.raise_for_status()

        for pelicula in response.json().get("results", []):
            movie_id = pelicula.get("id")

            if not movie_id or movie_id in ids_usados:
                continue

            ids_usados.add(movie_id)
            peliculas.append(pelicula)

    cache.set(cache_key, peliculas, 60 * 60)

    return peliculas


def preparar_pelicula_busqueda_global(pelicula):
    movie_id = pelicula.get("id")

    if not movie_id:
        return None

    # La búsqueda global se muestra como resultado informativo. Para que el
    # buscador responda rápido en local, Docker y Render, no descargamos aquí
    # el detalle completo de cada película: eso se hace solo cuando el usuario
    # abre la ficha. Así evitamos 8-16 llamadas extra a TMDB por búsqueda.
    pelicula_resultado = dict(pelicula)
    poster_path = pelicula_resultado.get("poster_path")
    poster_url_respaldo = pelicula_resultado.get("poster_url") or ""

    pelicula_resultado["poster_url"] = (
        f"https://image.tmdb.org/t/p/w342{poster_path}"
        if poster_path
        else poster_url_respaldo
    )
    pelicula_resultado["title"] = (
        pelicula_resultado.get("title")
        or pelicula_resultado.get("name")
        or "Título no disponible"
    )
    pelicula_resultado["overview"] = (
        pelicula_resultado.get("overview")
        or "Sin sinopsis disponible."
    )
    pelicula_resultado["vote_average"] = pelicula_resultado.get("vote_average") or 0
    pelicula_resultado["calificacion_edad"] = "+18" if pelicula_resultado.get("adult") else ""
    pelicula_resultado["tipo_cartelera"] = "busqueda_global"
    pelicula_resultado["en_cartelera_principal"] = False
    pelicula_resultado["en_ultimas_sesiones"] = False
    pelicula_resultado["resultado_busqueda_global"] = True
    pelicula_resultado["sesiones_futuras"] = 0
    pelicula_resultado["texto_disponibilidad"] = (
        "Ficha informativa. No tiene sesiones programadas actualmente."
    )
    aplicar_campos_presentacion_pelicula(pelicula_resultado)

    return pelicula_resultado


def obtener_peliculas_busqueda_global_tmdb(texto_busqueda, excluir_ids=None, limite=8):
    texto_busqueda = (texto_busqueda or "").strip()
    excluir_ids = set(excluir_ids or [])

    if len(texto_busqueda) < 2:
        return []

    cache_key = f"tmdb_busqueda_global_v2_{hashlib.md5(texto_busqueda.lower().encode()).hexdigest()}_{limite}"
    resultados_cacheados = cache.get(cache_key)

    if resultados_cacheados is not None:
        return [
            pelicula for pelicula in resultados_cacheados
            if normalizar_id_pelicula_diccionario(pelicula) not in excluir_ids
        ][:limite]

    api_key = settings.TMDB_API_KEY
    url = (
        "https://api.themoviedb.org/3/search/movie"
        f"?api_key={api_key}&language=es-ES&query={quote(texto_busqueda)}&include_adult=false&page=1"
    )

    response = requests.get(url, headers=construir_headers_tmdb(), timeout=6)
    response.raise_for_status()

    resultados = []
    ids_usados = set()

    for pelicula in response.json().get("results", []):
        movie_id = pelicula.get("id")

        if not movie_id or movie_id in ids_usados:
            continue

        ids_usados.add(movie_id)
        pelicula_preparada = preparar_pelicula_busqueda_global(pelicula)

        if pelicula_preparada:
            resultados.append(pelicula_preparada)

        if len(resultados) >= limite * 2:
            break

    cache.set(cache_key, resultados, 60 * 20)

    return [
        pelicula for pelicula in resultados
        if normalizar_id_pelicula_diccionario(pelicula) not in excluir_ids
    ][:limite]



def preparar_pelicula_basica_para_tests(pelicula):
    """Compatibilidad con tests unitarios que mockean solo el endpoint popular."""
    if not pelicula:
        return None

    release_date = pelicula.get("release_date") or ""
    if not texto_api_valido(release_date):
        return None

    poster_path = pelicula.get("poster_path") or ""

    return {
        "id": pelicula.get("id"),
        "title": pelicula.get("title") or "Título no disponible",
        "overview": pelicula.get("overview") or "Sin sinopsis disponible.",
        "release_date": release_date,
        "vote_average": pelicula.get("vote_average") if pelicula.get("vote_average") is not None else 0,
        "poster_path": poster_path,
        "poster_url": construir_poster_url_tmdb(poster_path) if poster_path else "",
    }


def preparar_cartelera_basica_para_tests(peliculas, criterio):
    peliculas_preparadas = []

    for pelicula in peliculas or []:
        preparada = preparar_pelicula_basica_para_tests(pelicula)
        if preparada:
            peliculas_preparadas.append(preparada)

    return ordenar_peliculas_cartelera(peliculas_preparadas, criterio)


# =========================
# RECOMENDACIONES
# =========================

def construir_poster_url_tmdb(poster_path, tamano="w342"):
    if not poster_path:
        return ""

    poster_path = str(poster_path)

    if poster_path.startswith("http://") or poster_path.startswith("https://"):
        return poster_path

    return f"https://image.tmdb.org/t/p/{tamano}{poster_path}"


def preparar_pelicula_recomendada(pelicula, motivo="Recomendada para ti"):
    if not pelicula:
        return None

    movie_id = pelicula.get("id") or pelicula.get("movie_id")

    if not movie_id:
        return None

    titulo = (
        pelicula.get("title")
        or pelicula.get("titulo")
        or pelicula.get("titulo_pelicula")
        or "Título no disponible"
    )

    sinopsis = (
        pelicula.get("overview")
        or pelicula.get("sinopsis")
        or "Sin sinopsis disponible."
    )

    poster_url = (
        pelicula.get("poster_url")
        or construir_poster_url_tmdb(pelicula.get("poster_path"))
    )

    fecha_estreno = pelicula.get("release_date") or pelicula.get("fecha_estreno") or ""
    valoracion = pelicula.get("vote_average") or pelicula.get("valoracion") or 0

    try:
        valoracion = round(float(valoracion), 2)
    except (TypeError, ValueError):
        valoracion = 0

    genero_ids, generos_display = obtener_generos_pelicula(pelicula)

    pelicula_preparada = {
        "id": int(movie_id),
        "title": titulo,
        "overview": sinopsis,
        "poster_url": poster_url,
        "release_date": fecha_estreno,
        "vote_average": valoracion,
        "motivo": motivo,
        "genero_ids": [str(genero_id) for genero_id in genero_ids],
        "generos_display": generos_display,
        "genero_principal": generos_display[0] if generos_display else "",
    }

    return enriquecer_recomendacion_con_disponibilidad(pelicula_preparada)


def anadir_recomendacion_unica(recomendaciones, pelicula, ids_usados, motivo):
    pelicula_preparada = preparar_pelicula_recomendada(pelicula, motivo=motivo)

    if not pelicula_preparada:
        return

    movie_id = pelicula_preparada["id"]

    if movie_id in ids_usados:
        return

    ids_usados.add(movie_id)
    recomendaciones.append(pelicula_preparada)


def obtener_recomendaciones_tmdb(movie_id, limite=8):
    """
    Obtiene recomendaciones de TMDB usando la misma API que ya usa la app.
    Si TMDB no devuelve recomendaciones, prueba con películas similares.
    Si falla la API, devuelve lista vacía para que la vista use fallback interno.
    """
    cache_key = construir_cache_key_segura("tmdb_recomendaciones", movie_id)
    recomendaciones_cacheadas = cache.get(cache_key)

    if recomendaciones_cacheadas is not None:
        return recomendaciones_cacheadas[:limite]

    api_key = settings.TMDB_API_KEY
    headers = construir_headers_tmdb()
    endpoints = ["recommendations", "similar"]
    recomendaciones = []

    for endpoint in endpoints:
        url = (
            f"https://api.themoviedb.org/3/movie/{movie_id}/{endpoint}"
            f"?api_key={api_key}&language=es-ES&page=1"
        )

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            resultados = response.json().get("results", [])
        except requests.RequestException:
            resultados = []
        except ValueError:
            resultados = []

        for pelicula in resultados:
            pelicula_preparada = preparar_pelicula_recomendada(
                pelicula,
                motivo="Basada en películas que te interesan",
            )

            if pelicula_preparada:
                recomendaciones.append(pelicula_preparada)

        if recomendaciones:
            break

    cache.set(cache_key, recomendaciones, 60 * 60)

    return recomendaciones[:limite]


def obtener_recomendaciones_tmdb_por_genero(genero_id, excluir_ids=None, limite=12):
    """Devuelve recomendaciones externas de TMDB para un género concreto.

    Está pensado para la pantalla de recomendaciones: debe responder rápido y
    no quedarse vacío si una búsqueda concreta no devuelve resultados. Por eso
    consulta varias páginas con criterios poco restrictivos y cachea el resultado.
    """
    try:
        genero_id_int = int(genero_id)
    except (TypeError, ValueError):
        return []

    if genero_id_int not in TMDB_GENEROS:
        return []

    excluir_ids = {normalizar_movie_id(movie_id) for movie_id in (excluir_ids or [])}
    excluir_ids.discard(None)

    nombre_genero = TMDB_GENEROS.get(genero_id_int, "ese género")
    cache_key = f"tmdb_discover_genero_v6_{genero_id_int}_{limite}"
    resultados_cacheados = cache.get(cache_key)

    if resultados_cacheados is None:
        api_key = settings.TMDB_API_KEY
        preparados = []
        ids_usados = set()

        consultas = [
            "sort_by=popularity.desc",
            "sort_by=vote_average.desc&vote_count.gte=10",
            "sort_by=primary_release_date.desc",
            "sort_by=revenue.desc",
        ]

        for consulta in consultas:
            for pagina in range(1, 6):
                if len(preparados) >= max(limite * 2, 24):
                    break

                url = (
                    "https://api.themoviedb.org/3/discover/movie"
                    f"?api_key={api_key}&language=es-ES&include_adult=false"
                    f"&with_genres={genero_id_int}&{consulta}&page={pagina}"
                )

                try:
                    response = requests.get(url, headers=construir_headers_tmdb(), timeout=5)
                    response.raise_for_status()
                    resultados = response.json().get("results", [])
                except requests.RequestException:
                    resultados = []
                except ValueError:
                    resultados = []

                for pelicula in resultados:
                    movie_id = normalizar_movie_id(pelicula.get("id"))

                    if not movie_id or movie_id in ids_usados:
                        continue

                    ids_usados.add(movie_id)
                    pelicula_preparada = preparar_pelicula_recomendada(
                        pelicula,
                        motivo=f"Por tu interés en {nombre_genero}",
                    )

                    if pelicula_preparada:
                        pelicula_preparada["coincide_genero_usuario"] = True
                        pelicula_preparada["etiqueta_genero_usuario"] = f"Género {nombre_genero}"
                        preparados.append(pelicula_preparada)

                if len(preparados) >= max(limite * 2, 24):
                    break

        cache.set(cache_key, preparados, 60 * 60)
        resultados_cacheados = preparados

    recomendaciones = []
    ids_devuelto = set()

    for pelicula in resultados_cacheados:
        movie_id = normalizar_movie_id(pelicula.get("id"))

        if not movie_id or movie_id in excluir_ids or movie_id in ids_devuelto:
            continue

        ids_devuelto.add(movie_id)
        recomendaciones.append(dict(pelicula))

        if len(recomendaciones) >= limite:
            break

    return recomendaciones


def combinar_recomendaciones_sin_duplicados(*listas, limite=24):
    combinadas = []
    ids_usados = set()

    for lista in listas:
        for pelicula in lista or []:
            movie_id = normalizar_movie_id(pelicula.get("id") or pelicula.get("movie_id"))

            if not movie_id or movie_id in ids_usados:
                continue

            ids_usados.add(movie_id)
            combinadas.append(pelicula)

            if len(combinadas) >= limite:
                return combinadas

    return combinadas



def obtener_ids_cartelera_visible_cache():
    ids = cache.get("cartelera_visible_ids_actual")

    if not ids:
        return set()

    try:
        return {int(movie_id) for movie_id in ids if movie_id}
    except (TypeError, ValueError):
        return set()


def obtener_ids_cartelera_principal_cache():
    ids = cache.get("cartelera_principal_ids_actual")

    if not ids:
        return set()

    try:
        return {int(movie_id) for movie_id in ids if movie_id}
    except (TypeError, ValueError):
        return set()


def guardar_ids_cartelera_principal_cache(peliculas):
    ids = []

    for pelicula in peliculas or []:
        movie_id = pelicula.get("id") or pelicula.get("movie_id")

        if not movie_id:
            continue

        try:
            ids.append(int(movie_id))
        except (TypeError, ValueError):
            continue

    cache.set("cartelera_principal_ids_actual", ids, 60 * 60)
    cache.set("cartelera_visible_ids_actual", ids, 60 * 60)


def guardar_ids_cartelera_visible_cache(peliculas):
    ids = []

    for pelicula in peliculas or []:
        movie_id = pelicula.get("id") or pelicula.get("movie_id")

        if not movie_id:
            continue

        try:
            ids.append(int(movie_id))
        except (TypeError, ValueError):
            continue

    cache.set("cartelera_visible_ids_actual", ids, 60 * 30)


def normalizar_movie_id(movie_id):
    try:
        return int(movie_id)
    except (TypeError, ValueError):
        return None


def obtener_ids_peliculas_con_sesiones_comprometidas(limite=None, excluir_ids=None):
    """Películas fuera de cartelera que tienen sesiones futuras con entradas.

    Estas películas no reciben sesiones nuevas, pero se conservan como últimas
    sesiones para no dejar entradas futuras sin acceso y para poder completar
    aforo en sesiones ya comprometidas.
    """
    excluir_ids = {int(movie_id) for movie_id in (excluir_ids or []) if movie_id}

    qs = (
        Entrada.objects
        .filter(
            sesion__isnull=False,
            sesion__inicio__isnull=False,
            sesion__inicio__gt=timezone.now(),
        )
        .exclude(estado=Entrada.ESTADO_CANCELADA)
        .values("movie_id")
        .annotate(total=Count("id"), primera_sesion=Min("sesion__inicio"))
        .order_by("primera_sesion", "movie_id")
    )

    ids = []
    for fila in qs:
        movie_id = normalizar_movie_id(fila.get("movie_id"))
        if not movie_id or movie_id in excluir_ids:
            continue
        ids.append(movie_id)
        if limite and len(ids) >= limite:
            break

    return ids


def contar_sesiones_futuras_pelicula(movie_id):
    movie_id = normalizar_movie_id(movie_id)
    if not movie_id:
        return 0

    return SesionCine.objects.filter(
        movie_id=movie_id,
        inicio__isnull=False,
        inicio__gt=timezone.now(),
    ).count()


def contar_sesiones_comprometidas_futuras_pelicula(movie_id):
    movie_id = normalizar_movie_id(movie_id)
    if not movie_id:
        return 0

    return (
        Entrada.objects
        .filter(
            movie_id=movie_id,
            sesion__isnull=False,
            sesion__inicio__isnull=False,
            sesion__inicio__gt=timezone.now(),
        )
        .exclude(estado=Entrada.ESTADO_CANCELADA)
        .values("sesion_id")
        .distinct()
        .count()
    )


def pelicula_tiene_sesiones_comprometidas(movie_id):
    return contar_sesiones_comprometidas_futuras_pelicula(movie_id) > 0


def obtener_info_disponibilidad_pelicula(movie_id):
    movie_id = normalizar_movie_id(movie_id)
    if not movie_id:
        return {
            "tiene_sesiones": False,
            "en_cartelera_visible": False,
            "en_cartelera_principal": False,
            "en_ultimas_sesiones": False,
            "sesiones_futuras": 0,
            "texto_disponibilidad": "No disponible en cartelera",
        }

    ids_cartelera_principal = obtener_ids_cartelera_principal_cache()
    en_cartelera_principal = movie_id in ids_cartelera_principal if ids_cartelera_principal else False

    sesiones_totales_futuras = contar_sesiones_futuras_pelicula(movie_id)
    sesiones_comprometidas_futuras = contar_sesiones_comprometidas_futuras_pelicula(movie_id)

    en_ultimas_sesiones = (
        not en_cartelera_principal
        and sesiones_comprometidas_futuras > 0
    )

    if en_cartelera_principal:
        sesiones_mostradas = sesiones_totales_futuras
        texto_disponibilidad = f"En cartelera · {sesiones_mostradas} sesiones"
    elif en_ultimas_sesiones:
        sesiones_mostradas = sesiones_comprometidas_futuras
        texto_disponibilidad = f"Últimas sesiones · {sesiones_mostradas}"
    else:
        sesiones_mostradas = 0
        texto_disponibilidad = "Fuera de cartelera"

    tiene_sesiones = sesiones_mostradas > 0 and (en_cartelera_principal or en_ultimas_sesiones)

    return {
        "tiene_sesiones": tiene_sesiones,
        "en_cartelera_visible": en_cartelera_principal or en_ultimas_sesiones,
        "en_cartelera_principal": en_cartelera_principal,
        "en_ultimas_sesiones": en_ultimas_sesiones,
        "sesiones_futuras": sesiones_mostradas if tiene_sesiones else 0,
        "texto_disponibilidad": texto_disponibilidad,
    }


def enriquecer_recomendacion_con_disponibilidad(pelicula):
    if not pelicula:
        return pelicula

    disponibilidad = obtener_info_disponibilidad_pelicula(
        pelicula.get("id") or pelicula.get("movie_id")
    )

    pelicula.update(disponibilidad)

    return pelicula


def pelicula_aparece_en_cartelera_actual(movie_id):
    info = obtener_info_disponibilidad_pelicula(movie_id)
    return info["en_cartelera_principal"] or info["en_ultimas_sesiones"]

def obtener_ids_favoritos_usuario(usuario):
    if not usuario.is_authenticated or usuario.is_staff:
        return set()

    return set(
        Favorito.objects.filter(usuario=usuario)
        .values_list("movie_id", flat=True)
    )


def obtener_ids_peliculas_compradas_usuario(usuario):
    if not usuario.is_authenticated or usuario.is_staff:
        return set()

    return set(
        Entrada.objects.filter(usuario=usuario)
        .values_list("movie_id", flat=True)
        .distinct()
    )


def obtener_recomendaciones_internas(excluir_ids=None, limite=6):
    """
    Fallback interno sin depender de nuevas llamadas externas:
    prioriza sesiones futuras con mayor demanda, valoración y popularidad.
    Si todavía faltan recomendaciones, completa con la cartelera popular de TMDB.
    """
    excluir_ids = set(excluir_ids or [])
    recomendaciones = []
    ids_usados = set(excluir_ids)
    ahora = timezone.now()

    sesiones = (
        SesionCine.objects.filter(inicio__gt=ahora)
        .values(
            "movie_id",
            "titulo_pelicula",
            "popularidad",
            "valoracion",
            "fecha_estreno",
            "demanda_estimada",
        )
        .order_by("movie_id", "-demanda_estimada", "-valoracion", "-popularidad")
    )

    peliculas_por_id = {}

    for sesion in sesiones:
        movie_id = sesion["movie_id"]

        if movie_id in peliculas_por_id:
            continue

        peliculas_por_id[movie_id] = sesion

    sesiones_ordenadas = sorted(
        peliculas_por_id.values(),
        key=lambda item: (
            item.get("demanda_estimada") or 0,
            item.get("valoracion") or 0,
            item.get("popularidad") or 0,
        ),
        reverse=True,
    )

    for sesion in sesiones_ordenadas:
        if len(recomendaciones) >= limite:
            break

        fecha_estreno = sesion.get("fecha_estreno")
        fecha_estreno_txt = fecha_estreno.strftime("%Y-%m-%d") if fecha_estreno else ""
        pelicula_interna = {
            "id": sesion["movie_id"],
            "title": sesion["titulo_pelicula"],
            "vote_average": sesion.get("valoracion") or 0,
            "release_date": fecha_estreno_txt,
        }

        try:
            detalle = obtener_detalle_tmdb(sesion["movie_id"])
            pelicula_interna.update(
                {
                    "title": detalle.get("title") or pelicula_interna["title"],
                    "overview": detalle.get("overview") or "Sin sinopsis disponible.",
                    "poster_path": detalle.get("poster_path") or "",
                    "release_date": detalle.get("release_date") or pelicula_interna["release_date"],
                    "vote_average": detalle.get("vote_average") or pelicula_interna["vote_average"],
                }
            )
        except Exception:
            pass

        antes = len(recomendaciones)
        anadir_recomendacion_unica(
            recomendaciones,
            pelicula_interna,
            ids_usados,
            "Popular en FICinema",
        )

        if len(recomendaciones) > antes:
            sesiones_futuras = contar_sesiones_futuras_pelicula(sesion["movie_id"])
            recomendaciones[-1].update(
                {
                    "tiene_sesiones": sesiones_futuras > 0,
                    "en_cartelera_visible": sesiones_futuras > 0,
                    "en_cartelera_principal": sesiones_futuras > 0,
                    "en_ultimas_sesiones": False,
                    "sesiones_futuras": sesiones_futuras,
                    "texto_disponibilidad": (
                        f"En cartelera · {sesiones_futuras} sesiones"
                        if sesiones_futuras > 0
                        else "No disponible en cartelera"
                    ),
                }
            )

    if len(recomendaciones) < limite:
        try:
            peliculas_populares = obtener_peliculas_populares_tmdb()
        except requests.RequestException:
            peliculas_populares = []
        except ValueError:
            peliculas_populares = []

        peliculas_populares = sorted(
            peliculas_populares,
            key=lambda item: (
                item.get("vote_average") or 0,
                item.get("popularity") or 0,
            ),
            reverse=True,
        )

        for pelicula in peliculas_populares:
            if len(recomendaciones) >= limite:
                break

            anadir_recomendacion_unica(
                recomendaciones,
                pelicula,
                ids_usados,
                "Mejor valorada de cartelera",
            )

    return recomendaciones[:limite]


def obtener_generos_interes_usuario(usuario, limite_peliculas=8, limite_generos=5):
    """Detecta géneros preferidos a partir de favoritos y compras recientes.

    Se usan pocos elementos y detalle TMDB cacheado para no ralentizar la página.
    Si no hay datos suficientes, devuelve lista vacía y la vista usa recomendaciones generales.
    """
    if not usuario.is_authenticated or usuario.is_staff:
        return []

    cache_key = f"generos_interes_usuario_{usuario.id}"
    generos_cacheados = cache.get(cache_key)
    if generos_cacheados is not None:
        return generos_cacheados

    peliculas_usuario = []

    favoritos = (
        Favorito.objects
        .filter(usuario=usuario)
        .order_by("-creado_en")
        .values_list("movie_id", flat=True)[:limite_peliculas]
    )
    peliculas_usuario.extend(favoritos)

    if len(peliculas_usuario) < limite_peliculas:
        compradas = (
            Entrada.objects
            .filter(usuario=usuario)
            .order_by("-fechaCompra")
            .values_list("movie_id", flat=True)
            .distinct()[: limite_peliculas - len(peliculas_usuario)]
        )
        peliculas_usuario.extend(compradas)

    contador = defaultdict(int)
    nombres = {}
    ids_usados = set()

    for movie_id in peliculas_usuario:
        movie_id = normalizar_movie_id(movie_id)
        if not movie_id or movie_id in ids_usados:
            continue

        ids_usados.add(movie_id)

        try:
            detalle = obtener_detalle_tmdb(movie_id)
        except Exception:
            detalle = {}

        genero_ids, generos_display = obtener_generos_pelicula(detalle)

        for indice, genero_id in enumerate(genero_ids):
            genero_id_txt = str(genero_id)
            contador[genero_id_txt] += 1
            if indice < len(generos_display):
                nombres[genero_id_txt] = generos_display[indice]
            elif genero_id in TMDB_GENEROS:
                nombres[genero_id_txt] = TMDB_GENEROS[genero_id]

    generos = [
        {
            "id": genero_id,
            "nombre": nombres.get(genero_id, genero_id),
            "total": total,
        }
        for genero_id, total in sorted(
            contador.items(),
            key=lambda item: (-item[1], nombres.get(item[0], item[0])),
        )[:limite_generos]
    ]

    cache.set(cache_key, generos, 60 * 20)
    return generos


def aplicar_prioridad_generos_recomendaciones(recomendaciones, generos_interes):
    ids_interes = {str(genero["id"]) for genero in generos_interes or []}

    for recomendacion in recomendaciones:
        genero_ids = {str(genero_id) for genero_id in recomendacion.get("genero_ids", [])}
        coincide = bool(ids_interes & genero_ids)
        recomendacion["coincide_genero_usuario"] = coincide

        if coincide:
            recomendacion["etiqueta_genero_usuario"] = "Afinidad por género"
        else:
            recomendacion["etiqueta_genero_usuario"] = ""

    return sorted(
        recomendaciones,
        key=lambda item: (
            bool(item.get("coincide_genero_usuario")),
            bool(item.get("tiene_sesiones")),
            item.get("vote_average") or 0,
        ),
        reverse=True,
    )


def filtrar_recomendaciones_por_genero(recomendaciones, genero_id):
    genero_id = str(genero_id or "").strip()
    if not genero_id:
        return recomendaciones

    return [
        recomendacion for recomendacion in recomendaciones
        if genero_id in {str(genero) for genero in recomendacion.get("genero_ids", [])}
    ]


def obtener_generos_disponibles_recomendaciones(recomendaciones, generos_interes):
    generos = {str(genero["id"]): genero["nombre"] for genero in generos_interes or []}

    for recomendacion in recomendaciones or []:
        for genero_id, nombre in zip(
            recomendacion.get("genero_ids", []),
            recomendacion.get("generos_display", []),
        ):
            generos.setdefault(str(genero_id), nombre)

    return [
        {"id": genero_id, "nombre": nombre}
        for genero_id, nombre in sorted(generos.items(), key=lambda item: item[1])
    ]


def obtener_catalogo_generos_recomendaciones(generos_interes=None, recomendaciones=None):
    """Catálogo de géneros visible en recomendaciones.

    Se ponen primero los géneros detectados en el usuario y después el resto de
    géneros de TMDB. Así el filtro siempre puede generar una sección tipo
    Netflix/Amazon aunque la lista base inicial no contenga ese género.
    """
    generos = {}

    for genero in generos_interes or []:
        generos[str(genero["id"])] = genero["nombre"]

    for recomendacion in recomendaciones or []:
        for genero_id, nombre in zip(
            recomendacion.get("genero_ids", []),
            recomendacion.get("generos_display", []),
        ):
            generos.setdefault(str(genero_id), nombre)

    for genero_id, nombre in sorted(TMDB_GENEROS.items(), key=lambda item: item[1]):
        generos.setdefault(str(genero_id), nombre)

    return [{"id": genero_id, "nombre": nombre} for genero_id, nombre in generos.items()]


def separar_recomendaciones_por_disponibilidad(recomendaciones):
    con_sesiones = []
    sin_sesiones = []

    for recomendacion in recomendaciones or []:
        if recomendacion.get("tiene_sesiones"):
            con_sesiones.append(recomendacion)
        else:
            sin_sesiones.append(recomendacion)

    return con_sesiones, sin_sesiones


def obtener_recomendaciones_para_usuario(usuario, limite=6):
    favoritos_ids = obtener_ids_favoritos_usuario(usuario)
    compradas_ids = obtener_ids_peliculas_compradas_usuario(usuario)
    excluir_ids = favoritos_ids | compradas_ids
    recomendaciones = []
    ids_usados = set(excluir_ids)

    favoritos_recientes = (
        Favorito.objects.filter(usuario=usuario)
        .order_by("-creado_en")[:3]
        if usuario.is_authenticated and not usuario.is_staff
        else []
    )

    for favorito in favoritos_recientes:
        if len(recomendaciones) >= limite:
            break

        for pelicula in obtener_recomendaciones_tmdb(favorito.movie_id, limite=8):
            if len(recomendaciones) >= limite:
                break

            pelicula["motivo"] = f"Porque guardaste {favorito.titulo}"
            anadir_recomendacion_unica(
                recomendaciones,
                pelicula,
                ids_usados,
                pelicula["motivo"],
            )

    if len(recomendaciones) < limite:
        internas = obtener_recomendaciones_internas(
            excluir_ids=ids_usados,
            limite=limite - len(recomendaciones),
        )

        for pelicula in internas:
            anadir_recomendacion_unica(
                recomendaciones,
                pelicula,
                ids_usados,
                pelicula.get("motivo", "Recomendada por FICinema"),
            )

    generos_interes = obtener_generos_interes_usuario(usuario)
    recomendaciones = aplicar_prioridad_generos_recomendaciones(
        recomendaciones,
        generos_interes,
    )

    return recomendaciones[:limite]


def obtener_recomendaciones_para_detalle(movie_id, usuario=None, limite=6):
    excluir_ids = {int(movie_id)}

    if usuario and usuario.is_authenticated and not usuario.is_staff:
        excluir_ids |= obtener_ids_favoritos_usuario(usuario)

    recomendaciones = []
    ids_usados = set(excluir_ids)

    for pelicula in obtener_recomendaciones_tmdb(movie_id, limite=10):
        if len(recomendaciones) >= limite:
            break

        anadir_recomendacion_unica(
            recomendaciones,
            pelicula,
            ids_usados,
            "Similar a esta película",
        )

    if len(recomendaciones) < limite:
        internas = obtener_recomendaciones_internas(
            excluir_ids=ids_usados,
            limite=limite - len(recomendaciones),
        )

        for pelicula in internas:
            anadir_recomendacion_unica(
                recomendaciones,
                pelicula,
                ids_usados,
                pelicula.get("motivo", "También te puede interesar"),
            )

    return recomendaciones[:limite]


# =========================
# ESTADÍSTICAS AVANZADAS STAFF
# =========================

def obtener_estadisticas_avanzadas_staff():
    """
    Calcula métricas internas agregadas para staff usando Pandas.

    Se combinan datos de entradas, sesiones, salas, bonos y usuarios para
    obtener rankings, porcentajes de ocupación e ingresos simulados.
    """
    ahora = timezone.now()

    entradas_qs = Entrada.objects.select_related("sala", "usuario", "bono_usado", "sesion")
    sesiones_qs = SesionCine.objects.select_related("sala")
    bonos_qs = Bono.objects.select_related("usuario")
    salas_qs = Sala.objects.filter(activa=True)

    df_entradas = pd.DataFrame.from_records(
        entradas_qs.values(
            "id",
            "estado",
            "movie_id",
            "titulo_pelicula",
            "fecha",
            "hora",
            "fechaCompra",
            "sala__nombre",
            "usuario__username",
            "usuario__codigo",
            "usuario__is_staff",
            "bono_usado__tipo",
            "sesion_id",
        )
    )

    df_sesiones = pd.DataFrame.from_records(
        sesiones_qs.values(
            "id",
            "movie_id",
            "titulo_pelicula",
            "fecha",
            "inicio",
            "fin",
            "sala__nombre",
            "sala__filas",
            "sala__columnas",
        )
    )

    df_bonos = pd.DataFrame.from_records(
        bonos_qs.values(
            "id",
            "tipo",
            "fechaCaducidad",
            "usos_restantes",
            "usuario__username",
        )
    )

    total_entradas_emitidas = int(len(df_entradas))

    if df_entradas.empty:
        df_entradas_validas = pd.DataFrame(columns=df_entradas.columns)
    else:
        df_entradas["estado"] = df_entradas["estado"].fillna("")
        df_entradas_validas = df_entradas[df_entradas["estado"] != Entrada.ESTADO_CANCELADA].copy()

    total_entradas_vendidas = int(len(df_entradas_validas))
    total_sesiones = int(len(df_sesiones))

    if df_sesiones.empty:
        sesiones_futuras = 0
        sesiones_pasadas = 0
        capacidad_total_programada = 0
    else:
        df_sesiones["inicio"] = pd.to_datetime(df_sesiones["inicio"], errors="coerce")
        df_sesiones["fin"] = pd.to_datetime(df_sesiones["fin"], errors="coerce")
        df_sesiones["capacidad"] = (
            pd.to_numeric(df_sesiones["sala__filas"], errors="coerce").fillna(0)
            * pd.to_numeric(df_sesiones["sala__columnas"], errors="coerce").fillna(0)
        )
        sesiones_futuras = int((df_sesiones["inicio"] > ahora).sum())
        sesiones_pasadas = int((df_sesiones["fin"] <= ahora).sum())
        capacidad_total_programada = int(df_sesiones["capacidad"].sum())

    ocupacion_global = (
        round((total_entradas_vendidas / capacidad_total_programada) * 100, 2)
        if capacidad_total_programada
        else 0
    )

    if df_entradas_validas.empty:
        peliculas_mas_compradas = []
        salas_mas_usadas = []
        horas_punta = []
        usuarios_mas_activos = []
        bonos_mas_usados = []
        ventas_por_dia = []
        ventas_por_estado = []
        ingresos_por_pelicula = []
    else:
        peliculas_mas_compradas = (
            df_entradas_validas
            .groupby(["movie_id", "titulo_pelicula"], dropna=False)
            .size()
            .reset_index(name="total")
            .sort_values(["total", "titulo_pelicula"], ascending=[False, True])
            .head(5)
            .to_dict("records")
        )

        salas_mas_usadas = (
            df_entradas_validas.dropna(subset=["sala__nombre"])
            .groupby("sala__nombre")
            .size()
            .reset_index(name="total")
            .sort_values(["total", "sala__nombre"], ascending=[False, True])
            .head(5)
            .to_dict("records")
        )

        horas_punta = (
            df_entradas_validas[df_entradas_validas["hora"].fillna("") != ""]
            .groupby("hora")
            .size()
            .reset_index(name="total")
            .sort_values(["total", "hora"], ascending=[False, True])
            .head(5)
            .to_dict("records")
        )

        usuarios_mas_activos = (
            df_entradas_validas[df_entradas_validas["usuario__is_staff"] == False]
            .groupby(["usuario__username", "usuario__codigo"], dropna=False)
            .size()
            .reset_index(name="total")
            .sort_values(["total", "usuario__username"], ascending=[False, True])
            .head(5)
            .to_dict("records")
        )

        bonos_mas_usados = (
            df_entradas_validas.dropna(subset=["bono_usado__tipo"])
            .groupby("bono_usado__tipo")
            .size()
            .reset_index(name="total")
            .sort_values(["total", "bono_usado__tipo"], ascending=[False, True])
            .to_dict("records")
        )

        df_entradas_validas["fechaCompra"] = pd.to_datetime(
            df_entradas_validas["fechaCompra"],
            errors="coerce",
        )
        ventas_por_dia_df = df_entradas_validas.dropna(subset=["fechaCompra"]).copy()
        ventas_por_dia_df["dia"] = ventas_por_dia_df["fechaCompra"].dt.strftime("%Y-%m-%d")
        ventas_por_dia = (
            ventas_por_dia_df.groupby("dia")
            .size()
            .reset_index(name="total")
            .sort_values("dia", ascending=False)
            .head(7)
            .sort_values("dia")
            .to_dict("records")
        )

        ventas_por_estado = (
            df_entradas.groupby("estado")
            .size()
            .reset_index(name="total")
            .sort_values("estado")
            .to_dict("records")
        )

        ingresos_por_pelicula_df = df_entradas_validas.copy()
        ingresos_por_pelicula_df["importe_simulado"] = PRECIO_ENTRADA
        ingresos_por_pelicula = (
            ingresos_por_pelicula_df.groupby("titulo_pelicula")
            .agg(total_entradas=("id", "count"), ingresos=("importe_simulado", "sum"))
            .reset_index()
            .sort_values(["ingresos", "titulo_pelicula"], ascending=[False, True])
            .head(5)
            .assign(ingresos=lambda datos: datos["ingresos"].round(2))
            .to_dict("records")
        )

    ocupacion_por_sala = []

    if not df_sesiones.empty:
        sesiones_por_sala = (
            df_sesiones.groupby("sala__nombre", dropna=False)
            .agg(sesiones=("id", "count"), capacidad=("capacidad", "sum"))
            .reset_index()
        )

        if df_entradas_validas.empty:
            entradas_por_sala = pd.DataFrame(columns=["sala__nombre", "entradas"])
        else:
            entradas_por_sala = (
                df_entradas_validas.dropna(subset=["sala__nombre"])
                .groupby("sala__nombre")
                .size()
                .reset_index(name="entradas")
            )

        ocupacion_df = sesiones_por_sala.merge(
            entradas_por_sala,
            on="sala__nombre",
            how="left",
        )
        ocupacion_df["entradas"] = ocupacion_df["entradas"].fillna(0).astype(int)
        ocupacion_df["ocupacion"] = ocupacion_df.apply(
            lambda fila: round((fila["entradas"] / fila["capacidad"]) * 100, 2)
            if fila["capacidad"] else 0,
            axis=1,
        )
        ocupacion_df["sala"] = ocupacion_df["sala__nombre"].fillna("Sala no asignada")
        ocupacion_por_sala = (
            ocupacion_df.sort_values(["ocupacion", "sala"], ascending=[False, True])
            .head(8)[["sala", "sesiones", "entradas", "capacidad", "ocupacion"]]
            .to_dict("records")
        )

    sesiones_con_ventas = []
    peliculas_por_ocupacion = []
    desglose_ingresos = []
    proximas_24h = {
        "sesiones": 0,
        "entradas_activas": 0,
        "plazas_programadas": 0,
        "plazas_disponibles": 0,
        "ocupacion_prevista": 0,
        "primera_sesion": "Sin sesiones próximas",
    }
    alertas_gestion = []
    dia_mas_ventas = None

    if not df_sesiones.empty:
        limite_24h = ahora + timedelta(hours=24)
        sesiones_24h = df_sesiones[
            (df_sesiones["inicio"] >= ahora)
            & (df_sesiones["inicio"] <= limite_24h)
        ].copy()

        if not sesiones_24h.empty:
            ids_24h = set(sesiones_24h["id"].dropna().astype(int).tolist())
            entradas_24h = 0

            if not df_entradas_validas.empty:
                entradas_24h = int(
                    df_entradas_validas[
                        df_entradas_validas["sesion_id"].isin(ids_24h)
                        & (df_entradas_validas["estado"] == Entrada.ESTADO_ACTIVA)
                    ].shape[0]
                )

            plazas_24h = int(sesiones_24h["capacidad"].sum())
            plazas_disponibles_24h = max(plazas_24h - entradas_24h, 0)
            primera_sesion = sesiones_24h.sort_values("inicio").iloc[0]

            proximas_24h = {
                "sesiones": int(len(sesiones_24h)),
                "entradas_activas": entradas_24h,
                "plazas_programadas": plazas_24h,
                "plazas_disponibles": plazas_disponibles_24h,
                "ocupacion_prevista": round((entradas_24h / plazas_24h) * 100, 2) if plazas_24h else 0,
                "primera_sesion": timezone.localtime(primera_sesion["inicio"]).strftime("%d/%m/%Y %H:%M") if pd.notna(primera_sesion["inicio"]) else "Sin hora",
            }

    if not df_entradas_validas.empty and not df_sesiones.empty:
        entradas_por_sesion = (
            df_entradas_validas.dropna(subset=["sesion_id"])
            .groupby("sesion_id")
            .size()
            .reset_index(name="entradas")
        )

        sesiones_detalle = df_sesiones[[
            "id",
            "movie_id",
            "titulo_pelicula",
            "inicio",
            "sala__nombre",
            "capacidad",
        ]].copy()

        sesiones_ocupacion = sesiones_detalle.merge(
            entradas_por_sesion,
            left_on="id",
            right_on="sesion_id",
            how="left",
        )
        sesiones_ocupacion["entradas"] = sesiones_ocupacion["entradas"].fillna(0).astype(int)
        sesiones_ocupacion["ocupacion"] = sesiones_ocupacion.apply(
            lambda fila: round((fila["entradas"] / fila["capacidad"]) * 100, 2)
            if fila["capacidad"] else 0,
            axis=1,
        )
        sesiones_ocupacion["inicio_formateado"] = sesiones_ocupacion["inicio"].apply(
            lambda valor: timezone.localtime(valor).strftime("%d/%m/%Y %H:%M")
            if pd.notna(valor) else "Sin fecha",
        )

        sesiones_con_ventas = (
            sesiones_ocupacion[sesiones_ocupacion["entradas"] > 0]
            .sort_values(["ocupacion", "entradas", "inicio"], ascending=[False, False, True])
            .head(5)[[
                "titulo_pelicula",
                "sala__nombre",
                "inicio_formateado",
                "entradas",
                "capacidad",
                "ocupacion",
            ]]
            .to_dict("records")
        )

        entradas_por_pelicula = (
            df_entradas_validas
            .groupby(["movie_id", "titulo_pelicula"], dropna=False)
            .size()
            .reset_index(name="entradas")
        )
        capacidad_por_pelicula = (
            df_sesiones
            .groupby(["movie_id", "titulo_pelicula"], dropna=False)
            .agg(sesiones=("id", "count"), capacidad=("capacidad", "sum"))
            .reset_index()
        )
        peliculas_ocupacion = capacidad_por_pelicula.merge(
            entradas_por_pelicula,
            on=["movie_id", "titulo_pelicula"],
            how="left",
        )
        peliculas_ocupacion["entradas"] = peliculas_ocupacion["entradas"].fillna(0).astype(int)
        peliculas_ocupacion["ocupacion"] = peliculas_ocupacion.apply(
            lambda fila: round((fila["entradas"] / fila["capacidad"]) * 100, 2)
            if fila["capacidad"] else 0,
            axis=1,
        )
        peliculas_por_ocupacion = (
            peliculas_ocupacion[peliculas_ocupacion["entradas"] > 0]
            .sort_values(["ocupacion", "entradas", "titulo_pelicula"], ascending=[False, False, True])
            .head(5)[["titulo_pelicula", "entradas", "capacidad", "sesiones", "ocupacion"]]
            .to_dict("records")
        )

        sesiones_criticas = sesiones_ocupacion[
            (sesiones_ocupacion["inicio"] >= ahora)
            & (sesiones_ocupacion["ocupacion"] >= 85)
        ].sort_values(["ocupacion", "inicio"], ascending=[False, True])

        if not sesiones_criticas.empty:
            sesion = sesiones_criticas.iloc[0]
            alertas_gestion.append({
                "nivel": "Alta ocupación",
                "tipo": "warning",
                "titulo": "Sesión casi completa",
                "valor": f"{sesion['ocupacion']}%",
                "descripcion": (
                    f"{sesion['titulo_pelicula']} en {sesion['sala__nombre']} "
                    f"el {sesion['inicio_formateado']}. Conviene revisar aforo o programar refuerzo."
                ),
            })

        peliculas_sin_ventas = peliculas_ocupacion[
            (peliculas_ocupacion["sesiones"] >= 5)
            & (peliculas_ocupacion["entradas"] == 0)
        ].sort_values(["sesiones", "titulo_pelicula"], ascending=[False, True])

        if not peliculas_sin_ventas.empty:
            pelicula = peliculas_sin_ventas.iloc[0]
            alertas_gestion.append({
                "nivel": "Demanda baja",
                "tipo": "danger",
                "titulo": "Película sin ventas",
                "valor": f"{int(pelicula['sesiones'])} sesiones",
                "descripcion": (
                    f"{pelicula['titulo_pelicula']} tiene sesiones programadas y todavía no registra entradas válidas."
                ),
            })

        peliculas_baja_ocupacion = peliculas_ocupacion[
            (peliculas_ocupacion["sesiones"] >= 10)
            & (peliculas_ocupacion["entradas"] > 0)
            & (peliculas_ocupacion["ocupacion"] < 1)
        ].sort_values(["ocupacion", "sesiones"], ascending=[True, False])

        if not peliculas_baja_ocupacion.empty:
            pelicula = peliculas_baja_ocupacion.iloc[0]
            alertas_gestion.append({
                "nivel": "Revisar programación",
                "tipo": "info",
                "titulo": "Muchas sesiones con baja ocupación",
                "valor": f"{pelicula['ocupacion']}%",
                "descripcion": (
                    f"{pelicula['titulo_pelicula']} acumula {int(pelicula['sesiones'])} sesiones y "
                    f"{int(pelicula['entradas'])} entradas. Puede convenir reducir sesiones o cambiar horarios."
                ),
            })

        salas_baja_ocupacion = [
            sala for sala in ocupacion_por_sala
            if sala.get("sesiones", 0) >= 20 and sala.get("ocupacion", 0) < 0.5
        ]
        if salas_baja_ocupacion:
            sala = sorted(salas_baja_ocupacion, key=lambda item: (item.get("ocupacion", 0), -item.get("sesiones", 0)))[0]
            alertas_gestion.append({
                "nivel": "Uso de sala",
                "tipo": "info",
                "titulo": "Sala con ocupación baja",
                "valor": f"{sala.get('ocupacion', 0)}%",
                "descripcion": (
                    f"{sala.get('sala', 'Sala')} tiene {sala.get('sesiones', 0)} sesiones programadas y "
                    f"{sala.get('entradas', 0)} entradas válidas."
                ),
            })

    if proximas_24h["sesiones"] > 0:
        alertas_gestion.append({
            "nivel": "Próximas 24 horas",
            "tipo": "success",
            "titulo": "Control de acceso previsto",
            "valor": f"{proximas_24h['entradas_activas']} entradas",
            "descripcion": (
                f"Hay {proximas_24h['sesiones']} sesiones próximas desde {proximas_24h['primera_sesion']} "
                f"y {proximas_24h['plazas_disponibles']} plazas disponibles."
            ),
        })
    else:
        alertas_gestion.append({
            "nivel": "Próximas 24 horas",
            "tipo": "warning",
            "titulo": "Sin sesiones inmediatas",
            "valor": "0 sesiones",
            "descripcion": "No hay sesiones programadas para las próximas 24 horas.",
        })

    if ventas_por_dia:
        dia_mas_ventas = max(ventas_por_dia, key=lambda item: item.get("total", 0))

    entradas_con_bono = 0
    entradas_sin_bono = total_entradas_vendidas
    if not df_entradas_validas.empty:
        entradas_con_bono = int(df_entradas_validas["bono_usado__tipo"].notna().sum())
        entradas_sin_bono = int(total_entradas_vendidas - entradas_con_bono)

    valor_entradas_emitidas = round(total_entradas_vendidas * PRECIO_ENTRADA, 2)
    ingresos_entradas_directas = round(entradas_sin_bono * PRECIO_ENTRADA, 2)

    ingresos_estimados_bonos = 0
    if not df_bonos.empty:
        df_bonos["precio"] = df_bonos["tipo"].map(PRECIOS_BONO).fillna(0)
        ingresos_estimados_bonos = round(float(df_bonos["precio"].sum()), 2)

    ingresos_totales_cobrados = round(ingresos_entradas_directas + ingresos_estimados_bonos, 2)
    actividad_economica_simulada = round(valor_entradas_emitidas + ingresos_estimados_bonos, 2)

    desglose_ingresos = [
        {
            "concepto": "Entradas individuales",
            "cantidad": entradas_sin_bono,
            "ingresos": ingresos_entradas_directas,
            "detalle": "Cobro directo de entradas no asociadas a bono",
        },
        {
            "concepto": "Entradas consumidas con bono",
            "cantidad": entradas_con_bono,
            "ingresos": 0,
            "detalle": "El importe se contabiliza al vender el bono",
        },
        {
            "concepto": "Bonos vendidos",
            "cantidad": int(len(df_bonos)) if not df_bonos.empty else 0,
            "ingresos": ingresos_estimados_bonos,
            "detalle": "Ingresos generados por la compra de bonos",
        },
    ]

    media_entradas_por_sesion = (
        round(total_entradas_vendidas / total_sesiones, 2)
        if total_sesiones
        else 0
    )
    capacidad_media_por_sesion = (
        round(capacidad_total_programada / total_sesiones, 2)
        if total_sesiones
        else 0
    )
    porcentaje_entradas_con_bono = (
        round((entradas_con_bono / total_entradas_vendidas) * 100, 2)
        if total_entradas_vendidas
        else 0
    )
    porcentaje_cancelacion = (
        round((int((df_entradas["estado"] == Entrada.ESTADO_CANCELADA).sum()) / total_entradas_emitidas) * 100, 2)
        if total_entradas_emitidas and not df_entradas.empty
        else 0
    )
    porcentaje_entradas_usadas = (
        round((int((df_entradas["estado"] == Entrada.ESTADO_USADA).sum()) / total_entradas_vendidas) * 100, 2)
        if total_entradas_vendidas and not df_entradas.empty
        else 0
    )

    return {
        "resumen": {
            "entradas_validas": total_entradas_vendidas,
            "entradas_vendidas": total_entradas_vendidas,
            "entradas_emitidas": total_entradas_emitidas,
            "entradas_activas": int((df_entradas["estado"] == Entrada.ESTADO_ACTIVA).sum()) if not df_entradas.empty else 0,
            "entradas_usadas": int((df_entradas["estado"] == Entrada.ESTADO_USADA).sum()) if not df_entradas.empty else 0,
            "entradas_caducadas": int((df_entradas["estado"] == Entrada.ESTADO_CADUCADA).sum()) if not df_entradas.empty else 0,
            "entradas_canceladas": int((df_entradas["estado"] == Entrada.ESTADO_CANCELADA).sum()) if not df_entradas.empty else 0,
            "sesiones_programadas": total_sesiones,
            "sesiones_futuras": sesiones_futuras,
            "sesiones_pasadas": sesiones_pasadas,
            "salas_activas": salas_qs.count(),
            "ocupacion_global": ocupacion_global,
            "capacidad_total_programada": capacidad_total_programada,
            "capacidad_media_por_sesion": capacidad_media_por_sesion,
            "valor_entradas_emitidas": valor_entradas_emitidas,
            "ingresos_estimados_entradas": ingresos_entradas_directas,
            "ingresos_estimados_bonos": ingresos_estimados_bonos,
            "ingresos_estimados_totales": ingresos_totales_cobrados,
            "actividad_economica_simulada": actividad_economica_simulada,
            "media_entradas_por_sesion": media_entradas_por_sesion,
            "porcentaje_entradas_con_bono": porcentaje_entradas_con_bono,
            "porcentaje_cancelacion": porcentaje_cancelacion,
            "porcentaje_entradas_usadas": porcentaje_entradas_usadas,
            "entradas_con_bono": entradas_con_bono,
            "entradas_sin_bono": entradas_sin_bono,
            "dia_mas_ventas": dia_mas_ventas or {"dia": "Sin datos", "total": 0},
        },
        "peliculas_mas_compradas": peliculas_mas_compradas,
        "salas_mas_usadas": salas_mas_usadas,
        "horas_punta": horas_punta,
        "usuarios_mas_activos": usuarios_mas_activos,
        "bonos_mas_usados": bonos_mas_usados,
        "ocupacion_por_sala": ocupacion_por_sala,
        "ventas_por_dia": ventas_por_dia,
        "ventas_por_estado": ventas_por_estado,
        "ingresos_por_pelicula": ingresos_por_pelicula,
        "sesiones_con_mayor_ocupacion": sesiones_con_ventas,
        "peliculas_con_mayor_ocupacion": peliculas_por_ocupacion,
        "desglose_ingresos": desglose_ingresos,
        "proximas_24h": proximas_24h,
        "alertas_gestion": alertas_gestion,
    }

def obtener_fecha_estreno(fecha_estreno_str):
    try:
        return datetime.strptime(fecha_estreno_str, "%Y-%m-%d").date()
    except Exception:
        return None


def calcular_dias_desde_estreno(fecha_estreno):
    if not fecha_estreno:
        return 999

    return max((date.today() - fecha_estreno).days, 0)


def calcular_factor_recencia(fecha_estreno):
    dias = calcular_dias_desde_estreno(fecha_estreno)

    if dias <= 7:
        return 45

    if dias <= 14:
        return 35

    if dias <= 30:
        return 25

    if dias <= 60:
        return 12

    return 0


def calcular_entradas_recientes(movie_id):

    cache_key = f"entradas_recientes_{movie_id}"

    cacheado = cache.get(cache_key)

    if cacheado is not None:
        return cacheado

    desde = timezone.now() - timedelta(days=14)

    total = Entrada.objects.filter(
        movie_id=movie_id,
        fechaCompra__gte=desde,
    ).count()

    cache.set(
        cache_key,
        total,
        60 * 10,
    )

    return total

def calcular_demanda_pelicula(pelicula):
    popularidad = float(pelicula.get("popularity") or 0)
    valoracion = float(pelicula.get("vote_average") or 0)
    fecha_estreno = pelicula.get("fecha_estreno_obj")
    entradas_recientes = calcular_entradas_recientes(pelicula["id"])

    factor_recencia = calcular_factor_recencia(fecha_estreno)

    demanda = (
        popularidad * 0.45
        + valoracion * 7
        + factor_recencia
        + entradas_recientes * 3
    )

    return round(demanda, 2)

def calcular_numero_sesiones(pelicula, fecha_sesion):
    demanda = pelicula.get("demanda_estimada",0)

    if es_fin_de_semana(fecha_sesion):
        max_sesiones = MAX_SESIONES_FIN_DE_SEMANA
    else:
        max_sesiones = MAX_SESIONES_DIA_LABORABLE

    sesiones = MIN_SESIONES_POR_PELICULA

    if demanda >= 90:
        sesiones += 3
    elif demanda >= 65:
        sesiones += 2
    elif demanda >= 40:
        sesiones += 1

    if es_fin_de_semana(fecha_sesion):
        sesiones += 1

    return min(sesiones, max_sesiones)


def preparar_pelicula_para_programacion(pelicula_base):
    movie_id = pelicula_base.get("id")

    detalle = obtener_detalle_tmdb(movie_id)

    titulo = detalle.get("title") or pelicula_base.get("title") or "Título no disponible"
    duracion = detalle.get("runtime") or DURACION_POR_DEFECTO
    fecha_estreno = obtener_fecha_estreno(detalle.get("release_date"))

    pelicula = {
        "id": movie_id,
        "title": titulo,
        "runtime": int(duracion),
        "popularity": detalle.get("popularity") or pelicula_base.get("popularity") or 0,
        "vote_average": detalle.get("vote_average") or pelicula_base.get("vote_average") or 0,
        "release_date": detalle.get("release_date") or pelicula_base.get("release_date") or "",
        "fecha_estreno_obj": fecha_estreno,
    }

    pelicula["demanda_estimada"] = calcular_demanda_pelicula(pelicula)

    return pelicula


def obtener_cartelera_detallada(peliculas_tmdb=None, pelicula_actual=None):
    peliculas_validas = []

    if pelicula_actual is not None:
        movie_id = pelicula_actual.get("id")
        if movie_id:
            try:
                peliculas_validas.append(preparar_pelicula_para_programacion(pelicula_actual))
            except (requests.RequestException, ValueError, TypeError, KeyError):
                pass
        return peliculas_validas

    if peliculas_tmdb is None:
        peliculas_tmdb = []

    for pelicula_basica in peliculas_tmdb:
        movie_id = pelicula_basica.get("id")
        if not movie_id:
            continue

        try:
            peliculas_validas.append(preparar_pelicula_para_programacion(pelicula_basica))
        except (requests.RequestException, ValueError, TypeError, KeyError):
            continue

    return peliculas_validas

def limpiar_sesiones_incompletas_sin_entradas(fecha_sesion):
    SesionCine.objects.filter(
        fecha=fecha_sesion,
        inicio__isnull=True,
        entradas__isnull=True,
    ).delete()


def intervalos_se_solapan(inicio_a, fin_a, inicio_b, fin_b):
    return inicio_a < fin_b and fin_a > inicio_b


def construir_ocupacion_sesiones(fecha_sesion):
    sesiones = (
        SesionCine.objects.filter(
            fecha=fecha_sesion,
            inicio__isnull=False,
            fin__isnull=False,
        )
        .only("movie_id", "sala_id", "inicio", "fin")
    )

    ocupacion_salas = defaultdict(list)
    ocupacion_peliculas = defaultdict(list)
    sesiones_por_pelicula = defaultdict(int)

    for sesion in sesiones:
        intervalo = (sesion.inicio, sesion.fin)
        ocupacion_salas[sesion.sala_id].append(intervalo)
        ocupacion_peliculas[sesion.movie_id].append(intervalo)
        sesiones_por_pelicula[sesion.movie_id] += 1

    return ocupacion_salas, ocupacion_peliculas, sesiones_por_pelicula


def existe_solapamiento_intervalos(intervalos, inicio, fin):
    return any(
        intervalos_se_solapan(inicio, fin, inicio_existente, fin_existente)
        for inicio_existente, fin_existente in intervalos
    )


def existe_solapamiento_en_sala(sala, inicio, fin, ocupacion_salas=None):
    if ocupacion_salas is not None:
        return existe_solapamiento_intervalos(
            ocupacion_salas.get(sala.id, []),
            inicio,
            fin,
        )

    return SesionCine.objects.filter(
        sala=sala,
        inicio__lt=fin,
        fin__gt=inicio,
    ).exists()


def registrar_sesion_en_ocupacion(sesion, ocupacion_salas=None, ocupacion_peliculas=None, sesiones_por_pelicula=None):
    if not sesion or not sesion.inicio or not sesion.fin:
        return

    intervalo = (sesion.inicio, sesion.fin)

    if ocupacion_salas is not None:
        ocupacion_salas[sesion.sala_id].append(intervalo)

    if ocupacion_peliculas is not None:
        ocupacion_peliculas[sesion.movie_id].append(intervalo)

    if sesiones_por_pelicula is not None:
        sesiones_por_pelicula[sesion.movie_id] += 1


def crear_sesion_si_cabe(
    pelicula,
    sala,
    inicio,
    cierre,
    ocupacion_salas=None,
    ocupacion_peliculas=None,
    sesiones_por_pelicula=None,
    comprobar_solapamiento=True,
):
    duracion_total = pelicula["runtime"] + MARGEN_LIMPIEZA_MINUTOS
    fin = inicio + timedelta(minutes=duracion_total)

    ahora = timezone.now()

    if inicio <= ahora:
        return None

    if fin > cierre:
        return None

    if comprobar_solapamiento and existe_solapamiento_en_sala(sala, inicio, fin, ocupacion_salas):
        return None

    try:
        sesion = SesionCine.objects.create(
            movie_id=pelicula["id"],
            titulo_pelicula=pelicula["title"],
            fecha=timezone.localtime(inicio).date(),
            inicio=inicio,
            fin=fin,
            duracion_minutos=pelicula["runtime"],
            margen_limpieza_minutos=MARGEN_LIMPIEZA_MINUTOS,
            popularidad=float(pelicula.get("popularity") or 0),
            valoracion=float(pelicula.get("vote_average") or 0),
            fecha_estreno=pelicula.get("fecha_estreno_obj"),
            demanda_estimada=pelicula.get("demanda_estimada", 0) or 0,
            sala=sala,
        )
    except IntegrityError:
        return None

    registrar_sesion_en_ocupacion(
        sesion,
        ocupacion_salas=ocupacion_salas,
        ocupacion_peliculas=ocupacion_peliculas,
        sesiones_por_pelicula=sesiones_por_pelicula,
    )

    return sesion


def obtener_siguiente_hueco_sala(sala, fecha_sesion, apertura):
    """
    Devuelve el primer momento disponible de una sala para un día concreto.

    Si la sala no tiene sesiones, devuelve la hora de apertura.
    Si ya tiene sesiones, devuelve el fin de la última sesión.
    """
    ultima_sesion = (
        SesionCine.objects.filter(
            sala=sala,
            fecha=fecha_sesion,
            inicio__isnull=False,
            fin__isnull=False,
        )
        .order_by("-fin")
        .first()
    )

    if not ultima_sesion:
        return apertura

    return ultima_sesion.fin

def existe_solapamiento_misma_pelicula(movie_id, fecha_sesion, inicio, fin, ocupacion_peliculas=None):
    """
    Evita que una misma película tenga dos sesiones a la vez
    aunque sean en salas diferentes.
    """
    if ocupacion_peliculas is not None:
        return existe_solapamiento_intervalos(
            ocupacion_peliculas.get(movie_id, []),
            inicio,
            fin,
        )

    return SesionCine.objects.filter(
        movie_id=movie_id,
        fecha=fecha_sesion,
        inicio__lt=fin,
        fin__gt=inicio,
    ).exists()

def obtener_ventanas_base(fecha_sesion):
    if es_fin_de_semana(fecha_sesion):
        return VENTANAS_DIA_FIN_DE_SEMANA

    return VENTANAS_DIA_ENTRE_SEMANA

def generar_horarios_realistas_pelicula(movie_id, fecha_sesion):
    apertura = obtener_apertura(fecha_sesion)
    cierre = obtener_cierre(fecha_sesion)

    horarios = []
    semilla = int(movie_id or 0) + fecha_sesion.toordinal()
    desplazamiento = (semilla % 9) * 5
    cursor = apertura + timedelta(minutes=desplazamiento)

    while cursor < cierre:
        horarios.append(redondear_a_5_minutos(cursor))
        cursor += timedelta(minutes=45)

    if not horarios:
        return []

    inicio = semilla % len(horarios)
    horarios = horarios[inicio:] + horarios[:inicio]

    return horarios[::2] + horarios[1::2]

def intentar_crear_sesiones_pelicula(
    pelicula,
    fecha_sesion,
    numero_sesiones,
    salas,
    apertura,
    cierre,
    ocupacion_salas=None,
    ocupacion_peliculas=None,
    sesiones_por_pelicula=None,
):
    """
    Intenta crear las sesiones necesarias para una película respetando:
    - horario de apertura y cierre;
    - margen de limpieza;
    - no solapar una sala;
    - no emitir la misma película a la vez en salas diferentes.

    Primero usa horarios preferentes para mantener una programación natural.
    Si no encuentra hueco suficiente, hace una segunda pasada cada 5 minutos
    para cumplir mejor el mínimo diario de sesiones por película.
    """
    sesiones_creadas = 0
    duracion_total = pelicula["runtime"] + MARGEN_LIMPIEZA_MINUTOS

    def salas_por_disponibilidad():
        if ocupacion_salas is None:
            return list(salas)

        return sorted(
            salas,
            key=lambda sala: (len(ocupacion_salas.get(sala.id, [])), sala.id),
        )

    def intentar_inicio(inicio_propuesto):
        nonlocal sesiones_creadas

        if sesiones_creadas >= numero_sesiones:
            return False

        inicio_propuesto = redondear_a_5_minutos(inicio_propuesto)
        fin_propuesto = inicio_propuesto + timedelta(minutes=duracion_total)

        if inicio_propuesto <= timezone.now():
            return False

        if fin_propuesto > cierre:
            return False

        if existe_solapamiento_misma_pelicula(
            movie_id=pelicula["id"],
            fecha_sesion=fecha_sesion,
            inicio=inicio_propuesto,
            fin=fin_propuesto,
            ocupacion_peliculas=ocupacion_peliculas,
        ):
            return False

        for sala in salas_por_disponibilidad():
            if existe_solapamiento_en_sala(
                sala=sala,
                inicio=inicio_propuesto,
                fin=fin_propuesto,
                ocupacion_salas=ocupacion_salas,
            ):
                continue

            sesion = crear_sesion_si_cabe(
                pelicula=pelicula,
                sala=sala,
                inicio=inicio_propuesto,
                cierre=cierre,
                ocupacion_salas=ocupacion_salas,
                ocupacion_peliculas=ocupacion_peliculas,
                sesiones_por_pelicula=sesiones_por_pelicula,
                comprobar_solapamiento=False,
            )

            if sesion:
                sesiones_creadas += 1
                return True

        return False

    horarios_preferentes = generar_horarios_realistas_pelicula(
        movie_id=pelicula["id"],
        fecha_sesion=fecha_sesion,
    )

    horarios_revisados = set()

    for inicio_propuesto in horarios_preferentes:
        clave_horario = redondear_a_5_minutos(inicio_propuesto)
        horarios_revisados.add(clave_horario)
        intentar_inicio(inicio_propuesto)

        if sesiones_creadas >= numero_sesiones:
            return sesiones_creadas

    # Segunda pasada: mantiene la misma funcionalidad, pero evita que una
    # película se quede sin sesión por no encajar en sus horarios preferentes.
    cursor = apertura

    while cursor + timedelta(minutes=duracion_total) <= cierre:
        inicio_propuesto = redondear_a_5_minutos(cursor)

        if inicio_propuesto not in horarios_revisados:
            intentar_inicio(inicio_propuesto)

            if sesiones_creadas >= numero_sesiones:
                break

        cursor += timedelta(minutes=5)

    return sesiones_creadas


def obtener_conteo_sesiones_futuras_por_pelicula(fecha_sesion):
    conteos = defaultdict(int)

    for movie_id in SesionCine.objects.filter(
        fecha=fecha_sesion,
        inicio__isnull=False,
        inicio__gt=timezone.now(),
    ).values_list("movie_id", flat=True):
        conteos[movie_id] += 1

    return conteos


def obtener_sesiones_liberables(fecha_sesion, movie_id_protegido):
    conteos = obtener_conteo_sesiones_futuras_por_pelicula(fecha_sesion)

    sesiones = list(
        SesionCine.objects.filter(
            fecha=fecha_sesion,
            inicio__isnull=False,
            fin__isnull=False,
            inicio__gt=timezone.now(),
        )
        .exclude(movie_id=movie_id_protegido)
        .annotate(total_entradas=Count("entradas"))
        .filter(total_entradas=0)
        .select_related("sala")
        .order_by("demanda_estimada", "inicio", "sala_id")
    )

    return [
        sesion
        for sesion in sesiones
        if conteos.get(sesion.movie_id, 0) > MIN_SESIONES_POR_PELICULA
    ]


def crear_sesion_diaria_con_rebalanceo(pelicula, fecha_sesion, salas):
    if not pelicula or not pelicula.get("id") or not salas:
        return False

    apertura = obtener_apertura(fecha_sesion)
    cierre = obtener_cierre(fecha_sesion)

    for _intento in range(12):
        if SesionCine.objects.filter(
            movie_id=pelicula["id"],
            fecha=fecha_sesion,
            inicio__isnull=False,
            inicio__gt=timezone.now(),
        ).exists():
            return True

        liberables = obtener_sesiones_liberables(
            fecha_sesion=fecha_sesion,
            movie_id_protegido=pelicula["id"],
        )

        if not liberables:
            return False

        liberables[0].delete()

        ocupacion_salas, ocupacion_peliculas, sesiones_por_pelicula = construir_ocupacion_sesiones(fecha_sesion)
        creadas = intentar_crear_sesiones_pelicula(
            pelicula=pelicula,
            fecha_sesion=fecha_sesion,
            numero_sesiones=1,
            salas=salas,
            apertura=apertura,
            cierre=cierre,
            ocupacion_salas=ocupacion_salas,
            ocupacion_peliculas=ocupacion_peliculas,
            sesiones_por_pelicula=sesiones_por_pelicula,
        )

        if creadas > 0:
            return True

    return False


def generar_programacion_dia(fecha_sesion, pelicula_actual=None, peliculas_tmdb=None):
    crear_salas_iniciales()
    limpiar_sesiones_incompletas_sin_entradas(fecha_sesion)
    limpiar_solapamientos_futuros_misma_pelicula(fecha_sesion=fecha_sesion)

    salas = list(Sala.objects.filter(activa=True).order_by("id"))

    if not salas:
        return

    apertura = obtener_apertura(fecha_sesion)
    cierre = obtener_cierre(fecha_sesion)

    try:
        cartelera = obtener_cartelera_detallada(
            peliculas_tmdb=peliculas_tmdb,
            pelicula_actual=pelicula_actual,
        )
    except requests.RequestException:
        return
    except ValueError:
        return

    if not cartelera:
        return

    if pelicula_actual:
        pelicula_actual_id = pelicula_actual.get("id")

        cartelera = sorted(
            cartelera,
            key=lambda item: (
                item["id"] != pelicula_actual_id,
                -item.get("demanda_estimada", 0),
            ),
        )
    else:
        cartelera = sorted(
            cartelera,
            key=lambda item: item.get("demanda_estimada", 0),
            reverse=True,
        )

    ocupacion_salas, ocupacion_peliculas, sesiones_por_pelicula = construir_ocupacion_sesiones(fecha_sesion)

    # Fase 1: garantizar mínimo 1 sesión por película y por día.
    for pelicula in cartelera:
        sesiones_actuales = sesiones_por_pelicula.get(pelicula["id"], 0)

        sesiones_pendientes = max(
            MIN_SESIONES_POR_PELICULA - sesiones_actuales,
            0,
        )

        if sesiones_pendientes > 0:
            intentar_crear_sesiones_pelicula(
                pelicula=pelicula,
                fecha_sesion=fecha_sesion,
                numero_sesiones=sesiones_pendientes,
                salas=salas,
                apertura=apertura,
                cierre=cierre,
                ocupacion_salas=ocupacion_salas,
                ocupacion_peliculas=ocupacion_peliculas,
                sesiones_por_pelicula=sesiones_por_pelicula,
            )

    # Fase 2: añadir sesiones extra según demanda.
    tareas_extra = []

    for pelicula in cartelera:
        sesiones_objetivo = calcular_numero_sesiones(pelicula, fecha_sesion)
        sesiones_actuales = sesiones_por_pelicula.get(pelicula["id"], 0)
        sesiones_extra = max(sesiones_objetivo - sesiones_actuales, 0)

        for _i in range(sesiones_extra):
            tareas_extra.append(pelicula)

    tareas_extra = sorted(
        tareas_extra,
        key=lambda item: item.get("demanda_estimada", 0),
        reverse=True,
    )

    for pelicula in tareas_extra:
        intentar_crear_sesiones_pelicula(
            pelicula=pelicula,
            fecha_sesion=fecha_sesion,
            numero_sesiones=1,
            salas=salas,
            apertura=apertura,
            cierre=cierre,
            ocupacion_salas=ocupacion_salas,
            ocupacion_peliculas=ocupacion_peliculas,
            sesiones_por_pelicula=sesiones_por_pelicula,
        )


def limpiar_solapamientos_futuros_misma_pelicula(movie_id=None, fecha_sesion=None):
    filtros = {
        "inicio__isnull": False,
        "fin__isnull": False,
        "inicio__gt": timezone.now(),
    }

    if movie_id:
        filtros["movie_id"] = movie_id

    if fecha_sesion:
        filtros["fecha"] = fecha_sesion

    sesiones = list(
        SesionCine.objects.filter(**filtros)
        .select_related("sala")
        .prefetch_related("entradas")
        .order_by("movie_id", "fecha", "inicio", "sala_id")
    )

    sesiones_por_pelicula_dia = defaultdict(list)

    for sesion in sesiones:
        sesiones_por_pelicula_dia[(sesion.movie_id, sesion.fecha)].append(sesion)

    ids_para_borrar = []

    for grupo in sesiones_por_pelicula_dia.values():
        sesiones_conservadas = []

        for sesion in grupo:
            if not sesion.inicio or not sesion.fin:
                continue

            tiene_entradas = sesion.entradas.exists()
            solapada = None

            for conservada in sesiones_conservadas:
                if intervalos_se_solapan(sesion.inicio, sesion.fin, conservada.inicio, conservada.fin):
                    solapada = conservada
                    break

            if not solapada:
                sesiones_conservadas.append(sesion)
                continue

            if tiene_entradas:
                if not solapada.entradas.exists():
                    ids_para_borrar.append(solapada.id)
                    sesiones_conservadas.remove(solapada)
                    sesiones_conservadas.append(sesion)
                continue

            ids_para_borrar.append(sesion.id)

    if ids_para_borrar:
        SesionCine.objects.filter(
            id__in=ids_para_borrar,
            entradas__isnull=True,
        ).delete()


def asegurar_sesion_diaria_pelicula(pelicula, fecha_sesion, salas=None):
    if not pelicula or not pelicula.get("id"):
        return False

    if SesionCine.objects.filter(
        movie_id=pelicula["id"],
        fecha=fecha_sesion,
        inicio__isnull=False,
        inicio__gt=timezone.now(),
    ).exists():
        return True

    limpiar_solapamientos_futuros_misma_pelicula(
        movie_id=pelicula["id"],
        fecha_sesion=fecha_sesion,
    )

    if salas is None:
        salas = list(Sala.objects.filter(activa=True).order_by("id"))

    if not salas:
        return False

    apertura = obtener_apertura(fecha_sesion)
    cierre = obtener_cierre(fecha_sesion)
    ocupacion_salas, ocupacion_peliculas, sesiones_por_pelicula = construir_ocupacion_sesiones(fecha_sesion)

    creadas = intentar_crear_sesiones_pelicula(
        pelicula=pelicula,
        fecha_sesion=fecha_sesion,
        numero_sesiones=1,
        salas=salas,
        apertura=apertura,
        cierre=cierre,
        ocupacion_salas=ocupacion_salas,
        ocupacion_peliculas=ocupacion_peliculas,
        sesiones_por_pelicula=sesiones_por_pelicula,
    )

    if creadas > 0:
        return True

    if crear_sesion_diaria_con_rebalanceo(
        pelicula=pelicula,
        fecha_sesion=fecha_sesion,
        salas=salas,
    ):
        return True

    return forzar_sesion_diaria_pelicula(
        pelicula=pelicula,
        fecha_sesion=fecha_sesion,
        salas=salas,
        permitir_rebalanceo=True,
    )



def generar_programacion_para_dias(dias_disponibles, pelicula_actual=None):
    movie_id = pelicula_actual.get("id") if pelicula_actual else None

    for dia in dias_disponibles:
        fecha_sesion = datetime.strptime(dia["fecha"], "%Y-%m-%d").date()

        if movie_id:
            ya_tiene_sesion_futura = SesionCine.objects.filter(
                movie_id=movie_id,
                fecha=fecha_sesion,
                inicio__isnull=False,
                inicio__gt=timezone.now(),
            ).exists()

            if ya_tiene_sesion_futura:
                continue

        generar_programacion_dia(
            fecha_sesion=fecha_sesion,
            pelicula_actual=pelicula_actual,
        )



def obtener_dias_sin_sesion_futura(movie_id, dias_disponibles):
    """Devuelve los días de la ventana de compra que aún no tienen sesión futura.

    Se usa para mantener la cartelera viva sin depender de una caché global:
    si una película aparece en cartelera, cada visita a su ficha puede completar
    únicamente los días que falten, conservando la programación automática.
    """
    fechas_por_texto = {}

    for dia in dias_disponibles:
        try:
            fecha = datetime.strptime(dia["fecha"], "%Y-%m-%d").date()
        except (KeyError, TypeError, ValueError):
            continue
        fechas_por_texto[dia["fecha"]] = fecha

    if not fechas_por_texto:
        return []

    fechas_con_sesion = set(
        SesionCine.objects.filter(
            movie_id=movie_id,
            fecha__in=list(fechas_por_texto.values()),
            inicio__isnull=False,
            inicio__gt=timezone.now(),
        ).values_list("fecha", flat=True)
    )

    return [
        dia
        for dia in dias_disponibles
        if fechas_por_texto.get(dia.get("fecha")) not in fechas_con_sesion
    ]

def obtener_sesiones_pelicula_para_dias(movie_id, dias_disponibles):
    sesiones_por_dia = {}

    for dia in dias_disponibles:
        fecha_sesion = datetime.strptime(dia["fecha"], "%Y-%m-%d").date()

        sesiones = list(
            SesionCine.objects.filter(
                movie_id=movie_id,
                fecha=fecha_sesion,
                inicio__isnull=False,
                inicio__gt=timezone.now(),
            )
            .select_related("sala")
            .order_by("inicio", "sala__id")
        )

        sesiones_por_dia[dia["fecha"]] = sesiones

    return sesiones_por_dia


def preparar_sesiones_para_template(sesiones_por_dia):
    sesiones_template = {}

    for fecha_sesion, sesiones in sesiones_por_dia.items():
        sesiones_template[fecha_sesion] = []

        for sesion in sesiones:
            sesiones_template[fecha_sesion].append(
                {
                    "id": sesion.id,
                    "hora": sesion.hora_inicio_formateada(),
                    "fin": sesion.hora_fin_formateada(),
                    "sala": sesion.sala.nombre,
                    "filas": sesion.sala.filas,
                    "columnas": sesion.sala.columnas,
                    "duracion": sesion.duracion_minutos,
                }
            )

    return sesiones_template


def preparar_asientos_por_sesion(sesiones_por_dia):
    asientos_por_sesion = {}

    sesiones = []

    for sesiones_dia in sesiones_por_dia.values():
        sesiones.extend(sesiones_dia)

    for sesion in sesiones:
        asientos_totales = sesion.sala.obtener_asientos()

        asientos_ocupados = list(
            Entrada.objects
            .filter(sesion=sesion)
            .exclude(estado=Entrada.ESTADO_CANCELADA)
            .exclude(asiento__isnull=True)
            .exclude(asiento="")
            .values_list("asiento", flat=True)
        )

        asientos_por_sesion[str(sesion.id)] = {
            "asientos": asientos_totales,
            "ocupados": asientos_ocupados,
            "filas": sesion.sala.filas,
            "columnas": sesion.sala.columnas,
            "sala": sesion.sala.nombre,
        }

    return asientos_por_sesion


def construir_dias_disponibles_desde_hoy(numero_dias=7):
    dias_disponibles = []
    hoy = datetime.now().date()

    for i in range(numero_dias):
        proximo_dia = hoy + timedelta(days=i)
        dias_disponibles.append(
            {
                "fecha": proximo_dia.strftime("%Y-%m-%d"),
                "dia_semana": formatear_fecha_es(proximo_dia),
                "numero_dia": proximo_dia.day,
            }
        )

    return dias_disponibles


def obtener_ids_favoritos_usuario(usuario):
    if not usuario.is_authenticated or usuario.is_staff:
        return set()

    return set(
        Favorito.objects.filter(usuario=usuario).values_list("movie_id", flat=True)
    )


def normalizar_pelicula_favorito_desde_post(request):
    movie_id = request.POST.get("movie_id", "").strip()

    if not movie_id:
        raise ValueError("Falta el identificador de la película.")

    return {
        "movie_id": int(movie_id),
        "titulo": request.POST.get("titulo", "").strip() or "Título no disponible",
        "poster_url": request.POST.get("poster_url", "").strip(),
        "fecha_estreno": request.POST.get("fecha_estreno", "").strip(),
        "valoracion": float(request.POST.get("valoracion") or 0),
    }



def construir_fechas_desde_dias_disponibles(dias_disponibles):
    fechas = []

    for dia in dias_disponibles:
        try:
            fechas.append(datetime.strptime(dia["fecha"], "%Y-%m-%d").date())
        except (KeyError, TypeError, ValueError):
            continue

    return fechas


def obtener_horarios_completos_para_pelicula(pelicula, fecha_sesion):
    apertura = obtener_apertura(fecha_sesion)
    cierre = obtener_cierre(fecha_sesion)
    duracion_total = int(pelicula.get("runtime") or DURACION_POR_DEFECTO) + MARGEN_LIMPIEZA_MINUTOS

    horarios = []
    revisados = set()

    for horario in generar_horarios_realistas_pelicula(pelicula.get("id"), fecha_sesion):
        horario = redondear_a_5_minutos(horario)
        if horario not in revisados:
            horarios.append(horario)
            revisados.add(horario)

    cursor = apertura
    while cursor + timedelta(minutes=duracion_total) <= cierre:
        horario = redondear_a_5_minutos(cursor)
        if horario not in revisados:
            horarios.append(horario)
            revisados.add(horario)
        cursor += timedelta(minutes=5)

    return horarios


def contar_sesiones_futuras_pelicula_dia(movie_id, fecha_sesion):
    return SesionCine.objects.filter(
        movie_id=movie_id,
        fecha=fecha_sesion,
        inicio__isnull=False,
        inicio__gt=timezone.now(),
    ).count()


def obtener_bloqueos_liberables_sala(sala, inicio, fin, movie_id_protegido):
    bloqueos = list(
        SesionCine.objects.filter(
            sala=sala,
            inicio__lt=fin,
            fin__gt=inicio,
            inicio__isnull=False,
            fin__isnull=False,
            inicio__gt=timezone.now(),
        )
        .exclude(movie_id=movie_id_protegido)
        .annotate(total_entradas=Count("entradas"))
        .filter(total_entradas=0)
        .order_by("demanda_estimada", "inicio", "id")
    )

    liberables = []

    for bloqueo in bloqueos:
        sesiones_futuras = contar_sesiones_futuras_pelicula_dia(
            movie_id=bloqueo.movie_id,
            fecha_sesion=bloqueo.fecha,
        )
        if sesiones_futuras > MIN_SESIONES_POR_PELICULA:
            liberables.append(bloqueo)

    return liberables


def preparar_pelicula_minima_programacion(pelicula):
    pelicula = pelicula or {}
    fecha_estreno = obtener_fecha_estreno(pelicula.get("release_date"))

    return {
        "id": pelicula.get("id"),
        "title": pelicula.get("title") or "Título no disponible",
        "runtime": int(pelicula.get("runtime") or DURACION_POR_DEFECTO),
        "popularity": float(pelicula.get("popularity") or 0),
        "vote_average": float(pelicula.get("vote_average") or 0),
        "release_date": pelicula.get("release_date") or "",
        "fecha_estreno_obj": fecha_estreno,
        "demanda_estimada": float(pelicula.get("demanda_estimada") or 0),
    }


def forzar_sesion_diaria_pelicula(pelicula, fecha_sesion, salas=None, permitir_rebalanceo=True):
    if not pelicula or not pelicula.get("id"):
        return False

    if SesionCine.objects.filter(
        movie_id=pelicula["id"],
        fecha=fecha_sesion,
        inicio__isnull=False,
        inicio__gt=timezone.now(),
    ).exists():
        return True

    if salas is None:
        salas = list(Sala.objects.filter(activa=True).order_by("id"))

    if not salas:
        return False

    pelicula_programacion = preparar_pelicula_minima_programacion(pelicula)
    cierre = obtener_cierre(fecha_sesion)
    horarios = obtener_horarios_completos_para_pelicula(pelicula_programacion, fecha_sesion)

    for inicio in horarios:
        duracion_total = pelicula_programacion["runtime"] + MARGEN_LIMPIEZA_MINUTOS
        fin = inicio + timedelta(minutes=duracion_total)

        if inicio <= timezone.now() or fin > cierre:
            continue

        if existe_solapamiento_misma_pelicula(
            movie_id=pelicula_programacion["id"],
            fecha_sesion=fecha_sesion,
            inicio=inicio,
            fin=fin,
        ):
            continue

        salas_ordenadas = sorted(
            salas,
            key=lambda sala: (
                SesionCine.objects.filter(
                    sala=sala,
                    fecha=fecha_sesion,
                    inicio__isnull=False,
                ).count(),
                sala.id,
            ),
        )

        for sala in salas_ordenadas:
            if not existe_solapamiento_en_sala(sala=sala, inicio=inicio, fin=fin):
                sesion = crear_sesion_si_cabe(
                    pelicula=pelicula_programacion,
                    sala=sala,
                    inicio=inicio,
                    cierre=cierre,
                    comprobar_solapamiento=True,
                )
                if sesion:
                    return True
                continue

            if not permitir_rebalanceo:
                continue

            bloqueos_liberables = obtener_bloqueos_liberables_sala(
                sala=sala,
                inicio=inicio,
                fin=fin,
                movie_id_protegido=pelicula_programacion["id"],
            )

            if not bloqueos_liberables:
                continue

            ids_bloqueos = [bloqueo.id for bloqueo in bloqueos_liberables]
            SesionCine.objects.filter(id__in=ids_bloqueos, entradas__isnull=True).delete()

            if existe_solapamiento_en_sala(sala=sala, inicio=inicio, fin=fin):
                continue

            sesion = crear_sesion_si_cabe(
                pelicula=pelicula_programacion,
                sala=sala,
                inicio=inicio,
                cierre=cierre,
                comprobar_solapamiento=True,
            )
            if sesion:
                return True

    return False


def reforzar_minimo_diario_cartelera(peliculas, dias_disponibles):
    crear_salas_iniciales()
    salas = list(Sala.objects.filter(activa=True).order_by("id"))
    fechas = construir_fechas_desde_dias_disponibles(dias_disponibles)

    informe = {}

    if not peliculas or not salas or not fechas:
        return informe

    for fecha_sesion in fechas:
        informe[str(fecha_sesion)] = []
        limpiar_sesiones_incompletas_sin_entradas(fecha_sesion)
        limpiar_solapamientos_futuros_misma_pelicula(fecha_sesion=fecha_sesion)

        for pelicula in peliculas:
            movie_id = pelicula.get("id")
            if not movie_id:
                continue

            tiene_sesion = SesionCine.objects.filter(
                movie_id=movie_id,
                fecha=fecha_sesion,
                inicio__isnull=False,
                inicio__gt=timezone.now(),
            ).exists()

            if tiene_sesion:
                continue

            creada = forzar_sesion_diaria_pelicula(
                pelicula=pelicula,
                fecha_sesion=fecha_sesion,
                salas=salas,
                permitir_rebalanceo=True,
            )

            if not creada:
                informe[str(fecha_sesion)].append(
                    {
                        "movie_id": movie_id,
                        "titulo": pelicula.get("title") or "Título no disponible",
                    }
                )

    return informe

def generar_programacion_cartelera_visible(peliculas):
    if not peliculas:
        return

    ids_cartelera = [
        pelicula.get("id")
        for pelicula in peliculas
        if pelicula.get("id")
    ]

    if not ids_cartelera:
        return

    crear_salas_iniciales()
    dias_disponibles = construir_dias_disponibles_desde_hoy(7)

    for dia in dias_disponibles:
        fecha_sesion = datetime.strptime(dia["fecha"], "%Y-%m-%d").date()
        limpiar_sesiones_incompletas_sin_entradas(fecha_sesion)
        limpiar_solapamientos_futuros_misma_pelicula(fecha_sesion=fecha_sesion)
        generar_programacion_dia(
            fecha_sesion=fecha_sesion,
            pelicula_actual=None,
            peliculas_tmdb=peliculas,
        )

    reforzar_minimo_diario_cartelera(
        peliculas=peliculas,
        dias_disponibles=dias_disponibles,
    )



def pelicula_tiene_sesiones_futuras(movie_id):
    if not movie_id:
        return False

    return SesionCine.objects.filter(
        movie_id=movie_id,
        inicio__isnull=False,
        inicio__gt=timezone.now(),
    ).exists()


def filtrar_cartelera_con_sesiones(peliculas):
    """Devuelve las candidatas actuales que tienen programación futura."""
    return [
        pelicula
        for pelicula in peliculas
        if pelicula_tiene_sesiones_futuras(pelicula.get("id"))
    ]


def obtener_ids_peliculas_con_sesiones_futuras(limite=MAX_PELICULAS_CARTELERA * 2):
    ids = (
        SesionCine.objects.filter(
            inicio__isnull=False,
            inicio__gt=timezone.now(),
        )
        .values("movie_id")
        .annotate(total=Count("id"))
        .order_by("-total")
        .values_list("movie_id", flat=True)[:limite]
    )

    return [movie_id for movie_id in ids if movie_id]


def obtener_sesiones_comprometidas_queryset(movie_id):
    movie_id = normalizar_movie_id(movie_id)
    if not movie_id:
        return SesionCine.objects.none()

    ids_sesiones = (
        Entrada.objects
        .filter(
            movie_id=movie_id,
            sesion__isnull=False,
            sesion__inicio__isnull=False,
            sesion__inicio__gt=timezone.now(),
        )
        .exclude(estado=Entrada.ESTADO_CANCELADA)
        .values_list("sesion_id", flat=True)
        .distinct()
    )

    return (
        SesionCine.objects
        .filter(id__in=ids_sesiones, inicio__gt=timezone.now())
        .select_related("sala")
        .order_by("inicio", "sala__id")
    )


def construir_dias_desde_sesiones_comprometidas(movie_id, limite_dias=7):
    fechas = (
        obtener_sesiones_comprometidas_queryset(movie_id)
        .order_by("fecha")
        .values_list("fecha", flat=True)
        .distinct()[:limite_dias]
    )

    return [
        {
            "fecha": fecha.strftime("%Y-%m-%d"),
            "dia_semana": formatear_fecha_es(fecha),
            "numero_dia": fecha.day,
        }
        for fecha in fechas
    ]


def obtener_sesiones_comprometidas_para_dias(movie_id, dias_disponibles):
    sesiones_por_dia = {}
    sesiones_qs = obtener_sesiones_comprometidas_queryset(movie_id)

    for dia in dias_disponibles:
        fecha_sesion = datetime.strptime(dia["fecha"], "%Y-%m-%d").date()
        sesiones_por_dia[dia["fecha"]] = list(
            sesiones_qs.filter(fecha=fecha_sesion).order_by("inicio", "sala__id")
        )

    return sesiones_por_dia


def preparar_pelicula_cartelera_desde_sesion(movie_id, tipo_cartelera="principal"):
    """Construye una tarjeta pública desde sesiones guardadas.

    tipo_cartelera="principal" representa la cartelera generada por criterios
    actuales. tipo_cartelera="ultimas_sesiones" representa películas antiguas
    con sesiones futuras ya comprometidas por entradas vendidas.
    """
    sesion = (
        SesionCine.objects.filter(
            movie_id=movie_id,
            inicio__isnull=False,
            inicio__gt=timezone.now(),
        )
        .order_by("inicio")
        .first()
    )

    if not sesion:
        return None

    try:
        detalle = obtener_detalle_tmdb(movie_id, exigir_datos_cartelera=True)
    except (requests.RequestException, ValueError, TypeError, KeyError):
        if tipo_cartelera != "ultimas_sesiones":
            eliminar_sesiones_futuras_sin_entradas(movie_id)
        return None

    if not detalle_tiene_datos_minimos_cartelera(detalle):
        if tipo_cartelera != "ultimas_sesiones":
            eliminar_sesiones_futuras_sin_entradas(movie_id)
        return None

    poster_path = detalle.get("poster_path")
    poster_url_respaldo = detalle.get("poster_url") or ""

    return {
        "id": movie_id,
        "title": detalle.get("title") or sesion.titulo_pelicula,
        "overview": detalle.get("overview") or "",
        "release_date": detalle.get("release_date") or (sesion.fecha_estreno.isoformat() if sesion.fecha_estreno else ""),
        "vote_average": detalle.get("vote_average") or sesion.valoracion or 0,
        "popularity": detalle.get("popularity") or sesion.popularidad or 0,
        "runtime": detalle.get("runtime") or sesion.duracion_minutos or DURACION_POR_DEFECTO,
        "poster_path": poster_path,
        "poster_url": (
            f"https://image.tmdb.org/t/p/w342{poster_path}"
            if poster_path
            else poster_url_respaldo
        ),
        "videos": detalle.get("videos") or {},
        "youtube_trailer_key": detalle.get("youtube_trailer_key"),
        "trailer_origen": detalle.get("trailer_origen"),
        "programada_en_ficinema": True,
        "tipo_cartelera": tipo_cartelera,
        "en_cartelera_principal": tipo_cartelera == "principal",
        "en_ultimas_sesiones": tipo_cartelera == "ultimas_sesiones",
    }

def contar_peliculas_cartelera_visible():
    """Cuenta las películas que aparecen en la cartelera pública.

    La cartelera puede tener más películas programadas en la base de datos,
    pero la vista pública muestra como máximo MAX_PELICULAS_CARTELERA. Por eso
    esta métrica usa primero los ids guardados al renderizar la cartelera y,
    si no existe caché, limita el recuento al máximo configurado.
    """
    ids_visibles = obtener_ids_cartelera_visible_cache()

    if ids_visibles:
        return min(len(ids_visibles), MAX_PELICULAS_CARTELERA)

    cache_key = "contador_cartelera_visible_v2"
    cacheado = cache.get(cache_key)

    if cacheado is not None:
        return cacheado

    total = 0

    for movie_id in obtener_ids_peliculas_con_sesiones_futuras(limite=MAX_PELICULAS_CARTELERA * 3):
        try:
            if preparar_pelicula_cartelera_desde_sesion(movie_id):
                total += 1

            if total >= MAX_PELICULAS_CARTELERA:
                break
        except (requests.RequestException, ValueError, TypeError, KeyError):
            continue

    total = min(total, MAX_PELICULAS_CARTELERA)
    cache.set(cache_key, total, 60 * 10)
    return total


def contar_peliculas_con_sesiones_futuras():
    return (
        SesionCine.objects.filter(
            inicio__isnull=False,
            inicio__gt=timezone.now(),
        )
        .values("movie_id")
        .distinct()
        .count()
    )


def formatear_valoracion_usuarios_exportacion(pelicula):
    total_resenas = pelicula.get("resenas", 0) or 0

    if not total_resenas:
        return "Sin reseñas"

    return f"{pelicula.get('valoracion_usuarios', 0)}/5 ({total_resenas} reseña(s))"


def obtener_cartelera_visible_para_informes(limite=MAX_PELICULAS_CARTELERA):
    ids_visibles = list(obtener_ids_cartelera_visible_cache())

    if not ids_visibles:
        ids_visibles = obtener_ids_peliculas_con_sesiones_futuras(limite=limite)

    resultados = []

    for movie_id in ids_visibles[:limite]:
        sesiones_futuras_qs = SesionCine.objects.filter(
            movie_id=movie_id,
            inicio__gt=timezone.now(),
        )

        primera_sesion = sesiones_futuras_qs.order_by("inicio").first()

        if not primera_sesion:
            continue

        resumen_pelicula = obtener_resumen_resenas(movie_id)
        entradas_validas = (
            Entrada.objects.filter(movie_id=movie_id)
            .exclude(estado=Entrada.ESTADO_CANCELADA)
            .count()
        )

        resultados.append(
            {
                "movie_id": movie_id,
                "titulo_pelicula": primera_sesion.titulo_pelicula,
                "sesiones": sesiones_futuras_qs.count(),
                "entradas_validas": entradas_validas,
                "valoracion_usuarios": resumen_pelicula["media"],
                "resenas": resumen_pelicula["total"],
            }
        )

    return sorted(resultados, key=lambda item: item["titulo_pelicula"].lower())


def eliminar_sesiones_futuras_sin_entradas(movie_id):
    """Limpia programación automática incompleta que todavía no se vendió.

    Si por cambios de API una película queda sin sinopsis/tráiler, no debe
    seguir apareciendo como película comprable. Solo se borran sesiones futuras
    sin entradas asociadas; las entradas ya compradas nunca se eliminan aquí.
    """
    if not movie_id:
        return

    SesionCine.objects.filter(
        movie_id=movie_id,
        inicio__isnull=False,
        inicio__gt=timezone.now(),
        entradas__isnull=True,
    ).delete()


def construir_dias_desde_sesiones_futuras(movie_id, limite_dias=7):
    """Devuelve solo fechas que tienen sesiones futuras para la película.

    Evita que el selector muestre una fecha sin sesiones como primera opción.
    """
    fechas = (
        SesionCine.objects.filter(
            movie_id=movie_id,
            inicio__isnull=False,
            inicio__gt=timezone.now(),
        )
        .order_by("fecha")
        .values_list("fecha", flat=True)
        .distinct()[:limite_dias]
    )

    return [
        {
            "fecha": fecha.strftime("%Y-%m-%d"),
            "dia_semana": formatear_fecha_es(fecha),
            "numero_dia": fecha.day,
        }
        for fecha in fechas
    ]


def combinar_peliculas_sin_duplicados(*listas, limite=MAX_PELICULAS_CARTELERA):
    peliculas = []
    ids_usados = set()

    for lista in listas:
        for pelicula in lista or []:
            movie_id = pelicula.get("id")
            if not movie_id or movie_id in ids_usados:
                continue
            ids_usados.add(movie_id)
            peliculas.append(pelicula)
            if len(peliculas) >= limite:
                return peliculas

    return peliculas


def obtener_generos_pelicula(pelicula):
    genero_ids = []
    generos_display = []

    for genero_id in pelicula.get("genre_ids") or []:
        try:
            genero_id_int = int(genero_id)
        except (TypeError, ValueError):
            continue

        if genero_id_int not in genero_ids:
            genero_ids.append(genero_id_int)

        nombre = TMDB_GENEROS.get(genero_id_int)
        if nombre and nombre not in generos_display:
            generos_display.append(nombre)

    for genero in pelicula.get("genres") or []:
        if isinstance(genero, dict):
            genero_id = genero.get("id")
            nombre = genero.get("name")
        else:
            genero_id = None
            nombre = str(genero or "").strip()

        try:
            genero_id_int = int(genero_id)
        except (TypeError, ValueError):
            genero_id_int = None

        if genero_id_int and genero_id_int not in genero_ids:
            genero_ids.append(genero_id_int)

        nombre = (nombre or TMDB_GENEROS.get(genero_id_int) or "").strip()
        if nombre and nombre not in generos_display:
            generos_display.append(nombre)

    return genero_ids, generos_display


def aplicar_generos_presentacion_pelicula(pelicula):
    genero_ids, generos_display = obtener_generos_pelicula(pelicula)
    pelicula["genero_ids"] = [str(genero_id) for genero_id in genero_ids]
    pelicula["generos_display"] = generos_display
    return pelicula


def completar_fechas_estreno_desde_sesiones(peliculas):
    peliculas = list(peliculas or [])

    ids_sin_fecha = [
        normalizar_id_pelicula_diccionario(pelicula)
        for pelicula in peliculas
        if not normalizar_fecha_estreno_iso_pelicula(pelicula)
    ]
    ids_sin_fecha = [movie_id for movie_id in ids_sin_fecha if movie_id]

    if not ids_sin_fecha:
        return peliculas

    fechas_por_pelicula = {
        fila["movie_id"]: fila["fecha_estreno"]
        for fila in (
            SesionCine.objects
            .filter(movie_id__in=ids_sin_fecha, fecha_estreno__isnull=False)
            .values("movie_id")
            .annotate(fecha_estreno=Min("fecha_estreno"))
        )
        if fila.get("fecha_estreno")
    }

    for pelicula in peliculas:
        movie_id = normalizar_id_pelicula_diccionario(pelicula)
        fecha_estreno = fechas_por_pelicula.get(movie_id)

        if fecha_estreno and not normalizar_fecha_estreno_iso_pelicula(pelicula):
            pelicula["release_date"] = fecha_estreno.isoformat()

    return peliculas


def obtener_fecha_ordenacion_pelicula(pelicula):
    """
    Devuelve una fecha comparable para ordenar cartelera.

    En la app pueden convivir fechas que vienen de:
    - TMDB como texto "YYYY-MM-DD".
    - Pandas como Timestamp.
    - Django/Python como date o datetime.
    - Caché, sesiones o recomendaciones como valores vacíos.

    Antes se comparaban directamente Timestamp y str al ordenar por fecha,
    provocando TypeError en algunos dispositivos/rutas.
    """
    fecha = pelicula.get("release_date") or pelicula.get("fecha_estreno")

    if isinstance(fecha, pd.Timestamp):
        if pd.isna(fecha):
            return date.min
        return fecha.date()

    if isinstance(fecha, datetime):
        return fecha.date()

    if isinstance(fecha, date):
        return fecha

    if isinstance(fecha, str):
        fecha = fecha.strip()
        if not fecha:
            return date.min

        for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(fecha, formato).date()
            except ValueError:
                continue

        try:
            fecha_parseada = pd.to_datetime(fecha, errors="coerce")
            if pd.notna(fecha_parseada):
                return fecha_parseada.date()
        except (TypeError, ValueError):
            pass

    return date.min


def normalizar_fecha_estreno_iso_pelicula(pelicula):
    fecha = obtener_fecha_ordenacion_pelicula(pelicula)

    if fecha == date.min:
        return ""

    return fecha.isoformat()


def formatear_fecha_estreno_pelicula(pelicula):
    fecha = obtener_fecha_ordenacion_pelicula(pelicula)

    if fecha == date.min:
        return "Fecha no disponible"

    return fecha.strftime("%d/%m/%Y")


def aplicar_campos_presentacion_pelicula(pelicula):
    pelicula["release_date_iso"] = normalizar_fecha_estreno_iso_pelicula(pelicula)
    pelicula["release_date_display"] = formatear_fecha_estreno_pelicula(pelicula)
    aplicar_generos_presentacion_pelicula(pelicula)
    return pelicula


def obtener_valoracion_ordenacion_pelicula(pelicula):
    valoracion = pelicula.get("vote_average") or pelicula.get("valoracion") or 0

    try:
        return float(valoracion)
    except (TypeError, ValueError):
        return 0.0


def obtener_valoracion_usuarios_ordenacion_pelicula(pelicula):
    resumen = pelicula.get("resumen_resenas") or {}

    try:
        media = float(resumen.get("media") or 0)
    except (TypeError, ValueError):
        media = 0.0

    try:
        total = int(resumen.get("total") or 0)
    except (TypeError, ValueError):
        total = 0

    return (media, total, obtener_valoracion_ordenacion_pelicula(pelicula))


def obtener_sesiones_ordenacion_pelicula(pelicula):
    try:
        sesiones = int(pelicula.get("sesiones_futuras") or 0)
    except (TypeError, ValueError):
        sesiones = 0

    return (sesiones, obtener_valoracion_ordenacion_pelicula(pelicula))


def ordenar_peliculas_cartelera(peliculas, criterio):
    if not peliculas:
        return []

    peliculas_ordenables = list(peliculas)

    if criterio == "Fecha de Lanzamiento":
        return sorted(
            peliculas_ordenables,
            key=obtener_fecha_ordenacion_pelicula,
            reverse=True,
        )

    if criterio == "Valoración":
        return sorted(
            peliculas_ordenables,
            key=obtener_valoracion_ordenacion_pelicula,
            reverse=True,
        )

    if criterio == "Valoración usuarios":
        return sorted(
            peliculas_ordenables,
            key=obtener_valoracion_usuarios_ordenacion_pelicula,
            reverse=True,
        )

    if criterio == "Sesiones disponibles":
        return sorted(
            peliculas_ordenables,
            key=obtener_sesiones_ordenacion_pelicula,
            reverse=True,
        )

    return sorted(
        peliculas_ordenables,
        key=lambda pelicula: (pelicula.get("title") or "").lower(),
    )



def index_peliculas(request):
    filtros_cartelera = obtener_filtros_cartelera(request)
    criterio = filtros_cartelera["ordenar_por"]
    criterio_cache = re.sub(r"[^A-Za-z0-9_.-]", "_", criterio)
    cache_key = f"cartelera_programada_v13_{criterio_cache}"

    peliculas_cacheadas = cache.get(cache_key)
    api_error_cartelera = False

    if peliculas_cacheadas is not None:
        peliculas_principales = peliculas_cacheadas.get("principales", [])
        peliculas_ultimas = peliculas_cacheadas.get("ultimas", [])
    else:
        try:
            data = obtener_peliculas_populares_tmdb(max_paginas=8)
        except (requests.RequestException, ValueError):
            data = []
            api_error_cartelera = True

        if ejecutando_tests():
            peliculas_principales = preparar_cartelera_basica_para_tests(data, criterio)
            peliculas_ultimas = []
        else:
            peliculas_candidatas = []

            for pelicula_base in data:
                movie_id = pelicula_base.get("id")
                if not movie_id:
                    continue

                try:
                    detalle_completo = obtener_detalle_tmdb(
                        movie_id,
                        exigir_datos_cartelera=True,
                    )
                    pelicula_fusionada = {**pelicula_base, **detalle_completo}

                    poster_path = pelicula_fusionada.get("poster_path")
                    poster_url_respaldo = pelicula_fusionada.get("poster_url") or ""
                    pelicula_fusionada["poster_url"] = (
                        f"https://image.tmdb.org/t/p/w342{poster_path}"
                        if poster_path
                        else poster_url_respaldo
                    )
                    pelicula_fusionada["tipo_cartelera"] = "principal"
                    pelicula_fusionada["en_cartelera_principal"] = True
                    pelicula_fusionada["en_ultimas_sesiones"] = False

                    if detalle_tiene_datos_minimos_cartelera(pelicula_fusionada):
                        peliculas_candidatas.append(pelicula_fusionada)

                    if len(peliculas_candidatas) >= MAX_PELICULAS_CARTELERA + 25:
                        break

                except (requests.RequestException, ValueError, TypeError, KeyError):
                    continue

            if peliculas_candidatas:
                df = pd.DataFrame(peliculas_candidatas)

                if not df.empty and "release_date" in df.columns:
                    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
                    df = df.dropna(subset=["release_date"])

                    hoy = pd.Timestamp(datetime.now().date())
                    inicio_cartelera = hoy - pd.Timedelta(days=180)
                    limite_cartelera = hoy + pd.Timedelta(days=90)
                    df = df[
                        (df["release_date"] >= inicio_cartelera)
                        & (df["release_date"] <= limite_cartelera)
                    ]

                    peliculas_candidatas = df.to_dict(orient="records")
                else:
                    peliculas_candidatas = []

            if peliculas_candidatas:
                ids_programacion = "_".join(
                    str(p.get("id")) for p in peliculas_candidatas if p.get("id")
                )
                cache_key_programacion = f"programacion_cartelera_v10_{ids_programacion}"

                if not cache.get(cache_key_programacion):
                    generar_programacion_cartelera_visible(peliculas_candidatas)
                    cache.set(cache_key_programacion, True, 60 * 10)

            peliculas_principales = filtrar_cartelera_con_sesiones(peliculas_candidatas)
            peliculas_principales = ordenar_peliculas_cartelera(peliculas_principales, criterio)
            peliculas_principales = combinar_peliculas_sin_duplicados(
                peliculas_principales,
                limite=MAX_PELICULAS_CARTELERA,
            )

            guardar_ids_cartelera_principal_cache(peliculas_principales)
            ids_principales = {normalizar_id_pelicula_diccionario(p) for p in peliculas_principales}
            ids_principales.discard(None)

            peliculas_ultimas = []
            ids_ultimas = obtener_ids_peliculas_con_sesiones_comprometidas(
                limite=MAX_PELICULAS_CARTELERA,
                excluir_ids=ids_principales,
            )

            for movie_id in ids_ultimas:
                pelicula_ultimas = preparar_pelicula_cartelera_desde_sesion(
                    movie_id,
                    tipo_cartelera="ultimas_sesiones",
                )
                if pelicula_ultimas:
                    peliculas_ultimas.append(pelicula_ultimas)

            peliculas_ultimas = ordenar_peliculas_cartelera(peliculas_ultimas, "Sesiones disponibles")

        cache.set(
            cache_key,
            {
                "principales": peliculas_principales,
                "ultimas": peliculas_ultimas,
            },
            60 * 10,
        )

    for pelicula in peliculas_principales:
        pelicula["tipo_cartelera"] = "principal"
        pelicula["en_cartelera_principal"] = True
        pelicula["en_ultimas_sesiones"] = False

    for pelicula in peliculas_ultimas:
        pelicula["tipo_cartelera"] = "ultimas_sesiones"
        pelicula["en_cartelera_principal"] = False
        pelicula["en_ultimas_sesiones"] = True

    guardar_ids_cartelera_principal_cache(peliculas_principales)

    peliculas_programadas = peliculas_principales + peliculas_ultimas
    peliculas_programadas = enriquecer_peliculas_con_datos_internos(
        peliculas_programadas,
        incluir_calificacion=True,
    )
    peliculas_programadas = filtrar_peliculas_cartelera(
        peliculas_programadas,
        filtros_cartelera,
    )
    peliculas_programadas = ordenar_peliculas_cartelera(
        peliculas_programadas,
        criterio,
    )

    peliculas_busqueda_global = []
    texto_busqueda = filtros_cartelera.get("q") or ""

    if texto_busqueda and not filtros_cartelera.get("solo_con_sesiones"):
        ids_programados = {
            normalizar_id_pelicula_diccionario(pelicula)
            for pelicula in peliculas_programadas
        }
        ids_programados.discard(None)

        try:
            peliculas_busqueda_global = obtener_peliculas_busqueda_global_tmdb(
                texto_busqueda,
                excluir_ids=ids_programados,
                limite=8,
            )
            peliculas_busqueda_global = enriquecer_peliculas_con_datos_internos(
                peliculas_busqueda_global,
                incluir_calificacion=False,
            )
            peliculas_busqueda_global = filtrar_peliculas_cartelera(
                peliculas_busqueda_global,
                filtros_cartelera,
            )
            peliculas_busqueda_global = ordenar_peliculas_cartelera(
                peliculas_busqueda_global,
                criterio,
            )
        except (requests.RequestException, ValueError, TypeError, KeyError):
            peliculas_busqueda_global = []

    peliculas = [
        aplicar_campos_presentacion_pelicula(pelicula)
        for pelicula in peliculas_programadas + peliculas_busqueda_global
    ]

    guardar_ids_cartelera_visible_cache(peliculas_programadas)

    favoritos_ids = obtener_ids_favoritos_usuario(request.user)

    total_principal_visible = sum(
        1 for pelicula in peliculas_programadas
        if pelicula.get("en_cartelera_principal")
    )
    total_ultimas_visible = sum(
        1 for pelicula in peliculas_programadas
        if pelicula.get("en_ultimas_sesiones")
    )

    return render(
        request,
        "peliculas.html",
        {
            "peliculas": peliculas,
            "ordenar_por": criterio,
            "favoritos_ids": favoritos_ids,
            "filtros_cartelera": filtros_cartelera,
            "resumen_filtros_cartelera": construir_resumen_filtros_cartelera(
                filtros_cartelera,
                len(peliculas),
                total_principal_visible,
                total_ultimas_visible,
            ),
            "opciones_filtros_cartelera": obtener_opciones_filtros_cartelera(),
            "api_error_cartelera": api_error_cartelera,
            "total_busqueda_global": len(peliculas_busqueda_global),
        },
    )

def normalizar_certificacion_edad(certificacion):
    valor = str(certificacion or "").strip().upper().replace(" ", "")

    equivalencias = {
        "A": "TP",
        "APTA": "TP",
        "TP": "TP",
        "0": "TP",
        "G": "TP",
        "PG": "+7",
        "7": "+7",
        "+7": "+7",
        "PG-13": "+12",
        "12": "+12",
        "+12": "+12",
        "12A": "+12",
        "R": "+16",
        "16": "+16",
        "+16": "+16",
        "NC-17": "+18",
        "18": "+18",
        "+18": "+18",
        "X": "+18",
    }

    if valor in equivalencias:
        return equivalencias[valor]

    numeros = re.findall(r"\d+", valor)
    if numeros:
        edad = int(numeros[0])
        if edad <= 0:
            return "TP"
        if edad <= 7:
            return "+7"
        if edad <= 12:
            return "+12"
        if edad <= 16:
            return "+16"
        return "+18"

    return ""


def obtener_calificacion_edad_pelicula(movie_id, pelicula=None):
    if pelicula and pelicula.get("adult"):
        return "+18"

    cache_key = f"tmdb_certificacion_edad_{movie_id}"
    valor_cacheado = cache.get(cache_key)

    if valor_cacheado:
        return valor_cacheado

    api_key = settings.TMDB_API_KEY
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates?api_key={api_key}"

    try:
        response = requests.get(url, headers=construir_headers_tmdb(), timeout=5)
        response.raise_for_status()
        resultados = response.json().get("results", [])
    except (requests.RequestException, ValueError):
        resultados = []

    prioridades = ["ES", "US", "GB", "FR"]

    for pais in prioridades:
        for item in resultados:
            if item.get("iso_3166_1") != pais:
                continue

            for release in item.get("release_dates", []):
                calificacion = normalizar_certificacion_edad(
                    release.get("certification")
                )
                if calificacion:
                    cache.set(cache_key, calificacion, 60 * 60 * 12)
                    return calificacion

    cache.set(cache_key, "Sin clasificar", 60 * 60 * 6)
    return "Sin clasificar"


def obtener_resumen_resenas(movie_id):
    resenas_visibles = Resena.objects.filter(movie_id=movie_id, visible=True)
    resumen = resenas_visibles.aggregate(
        media=Avg("puntuacion"),
        total=Count("id"),
    )

    media = resumen.get("media") or 0
    total = resumen.get("total") or 0

    return {
        "media": round(media, 1) if media else 0,
        "total": total,
    }


def normalizar_numero_filtro(valor, minimo=None, maximo=None):
    if valor in (None, ""):
        return None

    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None

    if minimo is not None and numero < minimo:
        return None

    if maximo is not None and numero > maximo:
        return None

    return numero


def obtener_filtros_cartelera(request):
    return {
        "ordenar_por": request.GET.get("ordenar_por", "Título"),
        "q": (request.GET.get("q") or "").strip(),
        "edad": request.GET.get("edad", ""),
        "genero": request.GET.get("genero", ""),
        "valoracion_minima": normalizar_numero_filtro(
            request.GET.get("valoracion_minima"),
            minimo=0,
            maximo=10,
        ),
        "valoracion_usuarios_minima": normalizar_numero_filtro(
            request.GET.get("valoracion_usuarios_minima"),
            minimo=0,
            maximo=5,
        ),
        "solo_con_sesiones": request.GET.get("solo_con_sesiones") == "1",
    }


def obtener_opciones_filtros_cartelera():
    return {
        "edades": ["TP", "+7", "+12", "+16", "+18", "Sin clasificar"],
        "generos": sorted(TMDB_GENEROS.items(), key=lambda item: item[1]),
        "valoraciones_tmdb": [6, 7, 8],
        "valoraciones_usuarios": [3, 4, 5],
        "ordenaciones": [
            ("Título", "Título"),
            ("Fecha de Lanzamiento", "Fecha de lanzamiento"),
            ("Valoración", "Valoración TMDB"),
            ("Valoración usuarios", "Valoración usuarios"),
            ("Sesiones disponibles", "Más sesiones disponibles"),
        ],
    }



def construir_resumen_filtros_cartelera(
    filtros,
    total_resultados,
    total_principal_visible=None,
    total_ultimas_visible=None,
):
    filtros_activos = []

    if filtros.get("q"):
        filtros_activos.append(f"Búsqueda: {filtros['q']}")

    if filtros.get("edad"):
        filtros_activos.append(f"Edad: {filtros['edad']}")

    if filtros.get("genero"):
        try:
            nombre_genero = TMDB_GENEROS.get(int(filtros["genero"]), filtros["genero"])
        except (TypeError, ValueError):
            nombre_genero = filtros["genero"]
        filtros_activos.append(f"Género: {nombre_genero}")

    if filtros.get("valoracion_minima") is not None:
        filtros_activos.append(f"TMDB desde {filtros['valoracion_minima']:g}/10")

    if filtros.get("valoracion_usuarios_minima") is not None:
        filtros_activos.append(f"Usuarios desde {filtros['valoracion_usuarios_minima']:g}/5")

    if filtros.get("solo_con_sesiones"):
        filtros_activos.append("Solo cartelera principal")

    return {
        "total_resultados": total_resultados,
        "total_base": MAX_PELICULAS_CARTELERA,
        "total_principal_visible": total_principal_visible,
        "total_ultimas_visible": total_ultimas_visible,
        "hay_ultimas_sesiones": bool(total_ultimas_visible),
        "hay_filtros": bool(filtros_activos),
        "filtros_activos": filtros_activos,
    }

def normalizar_id_pelicula_diccionario(pelicula):
    try:
        return int(pelicula.get("id") or pelicula.get("movie_id"))
    except (TypeError, ValueError, AttributeError):
        return None


def enriquecer_peliculas_con_datos_internos(peliculas, incluir_calificacion=True):
    peliculas = completar_fechas_estreno_desde_sesiones(peliculas)
    movie_ids = [
        movie_id
        for movie_id in (normalizar_id_pelicula_diccionario(pelicula) for pelicula in peliculas)
        if movie_id
    ]

    if not movie_ids:
        return peliculas

    ahora = timezone.now()
    sesiones_por_pelicula = {
        fila["movie_id"]: fila["total"]
        for fila in (
            SesionCine.objects
            .filter(movie_id__in=movie_ids, inicio__gt=ahora)
            .values("movie_id")
            .annotate(total=Count("id"))
        )
    }

    resenas_por_pelicula = {
        fila["movie_id"]: {
            "media": round(float(fila["media"]), 1) if fila["media"] else 0,
            "total": int(fila["total"] or 0),
        }
        for fila in (
            Resena.objects
            .filter(movie_id__in=movie_ids, visible=True)
            .values("movie_id")
            .annotate(media=Avg("puntuacion"), total=Count("id"))
        )
    }

    for pelicula in peliculas:
        movie_id = normalizar_id_pelicula_diccionario(pelicula)
        if not movie_id:
            continue

        pelicula["sesiones_futuras"] = sesiones_por_pelicula.get(movie_id, 0)

        disponibilidad = obtener_info_disponibilidad_pelicula(movie_id)
        if pelicula.get("en_cartelera_principal"):
            disponibilidad["en_cartelera_principal"] = True
            disponibilidad["en_cartelera_visible"] = True
            disponibilidad["en_ultimas_sesiones"] = False
            disponibilidad["tiene_sesiones"] = pelicula["sesiones_futuras"] > 0
            disponibilidad["texto_disponibilidad"] = f"En cartelera · {pelicula['sesiones_futuras']} sesiones"
        elif pelicula.get("en_ultimas_sesiones"):
            disponibilidad["en_cartelera_principal"] = False
            disponibilidad["en_cartelera_visible"] = True
            disponibilidad["en_ultimas_sesiones"] = True
            disponibilidad["tiene_sesiones"] = pelicula["sesiones_futuras"] > 0
            disponibilidad["texto_disponibilidad"] = f"Últimas sesiones · {pelicula['sesiones_futuras']}"

        pelicula.update(disponibilidad)
        if pelicula.get("en_cartelera_principal"):
            pelicula["sesiones_futuras"] = sesiones_por_pelicula.get(movie_id, 0) if pelicula.get("tiene_sesiones") else 0
        else:
            pelicula["sesiones_futuras"] = disponibilidad.get("sesiones_futuras", 0) if pelicula.get("tiene_sesiones") else 0
        pelicula["resumen_resenas"] = resenas_por_pelicula.get(
            movie_id,
            {"media": 0, "total": 0},
        )

        if incluir_calificacion:
            pelicula["calificacion_edad"] = obtener_calificacion_edad_pelicula(
                movie_id,
                pelicula,
            )

        aplicar_campos_presentacion_pelicula(pelicula)

    return peliculas


def obtener_valoracion_pelicula(pelicula):
    try:
        return float(pelicula.get("vote_average") or 0)
    except (TypeError, ValueError, AttributeError):
        return 0


def filtrar_peliculas_cartelera(peliculas, filtros):
    filtradas = []
    texto_busqueda = (filtros.get("q") or "").lower()
    edad = filtros.get("edad") or ""
    genero = str(filtros.get("genero") or "")
    valoracion_minima = filtros.get("valoracion_minima")
    valoracion_usuarios_minima = filtros.get("valoracion_usuarios_minima")
    solo_con_sesiones = filtros.get("solo_con_sesiones")

    for pelicula in peliculas or []:
        titulo = str(pelicula.get("title") or "")
        sinopsis = str(pelicula.get("overview") or "")

        if texto_busqueda and texto_busqueda not in f"{titulo} {sinopsis}".lower():
            continue

        calificacion_edad = pelicula.get("calificacion_edad") or ""
        if edad == "Sin clasificar":
            if calificacion_edad not in ("", "No disponible", "Sin clasificar"):
                continue
        elif edad and calificacion_edad != edad:
            continue

        if genero:
            generos_pelicula = {str(genero_id) for genero_id in pelicula.get("genero_ids") or []}
            if genero not in generos_pelicula:
                continue

        if valoracion_minima is not None and obtener_valoracion_pelicula(pelicula) < valoracion_minima:
            continue

        resumen_resenas = pelicula.get("resumen_resenas") or {}
        media_usuarios = resumen_resenas.get("media") or 0
        if valoracion_usuarios_minima is not None and media_usuarios < valoracion_usuarios_minima:
            continue

        if solo_con_sesiones and not pelicula.get("en_cartelera_principal"):
            continue

        filtradas.append(pelicula)

    return filtradas


def enriquecer_objetos_favoritos_con_resenas(favoritos):
    movie_ids = [favorito.movie_id for favorito in favoritos]
    resenas_por_pelicula = {
        fila["movie_id"]: {
            "media": round(float(fila["media"]), 1) if fila["media"] else 0,
            "total": int(fila["total"] or 0),
        }
        for fila in (
            Resena.objects
            .filter(movie_id__in=movie_ids, visible=True)
            .values("movie_id")
            .annotate(media=Avg("puntuacion"), total=Count("id"))
        )
    }

    for favorito in favoritos:
        favorito.resumen_resenas = resenas_por_pelicula.get(
            favorito.movie_id,
            {"media": 0, "total": 0},
        )

    return favoritos


def enriquecer_recomendaciones_con_resenas(recomendaciones):
    recomendaciones = list(recomendaciones or [])
    disponibilidad_original = {}

    for pelicula in recomendaciones:
        movie_id = normalizar_id_pelicula_diccionario(pelicula)
        if not movie_id:
            continue

        disponibilidad_original[movie_id] = {
            clave: pelicula.get(clave)
            for clave in (
                "tiene_sesiones",
                "en_cartelera_visible",
                "en_cartelera_principal",
                "en_ultimas_sesiones",
                "sesiones_futuras",
                "texto_disponibilidad",
            )
            if clave in pelicula
        }

    recomendaciones = enriquecer_peliculas_con_datos_internos(
        recomendaciones,
        incluir_calificacion=False,
    )

    for pelicula in recomendaciones:
        movie_id = normalizar_id_pelicula_diccionario(pelicula)
        datos_previos = disponibilidad_original.get(movie_id)
        if not datos_previos:
            continue

        if datos_previos.get("tiene_sesiones"):
            continue

        if datos_previos.get("texto_disponibilidad") == "No disponible en cartelera":
            pelicula.update(datos_previos)

    return recomendaciones


def detalle_pelicula(request, movie_id):
    try:
        pelicula = obtener_detalle_tmdb(movie_id, exigir_datos_cartelera=False)
    except requests.RequestException:
        return render(
            request,
            "detalle_pelicula.html",
            {
                "pelicula": None,
                "video_key": None,
                "dias_disponibles": [],
                "sesiones_por_dia": {},
                "asientos_por_sesion": {},
                "poster_url": "",
                "total_sesiones": 0,
                "entradas_vendidas": 0,
                "ocupacion_media": 0,
                "calificacion_edad": "No disponible",
                "resenas_pelicula": [],
                "resumen_resenas": {"media": 0, "total": 0},
                "resena_usuario": None,
                "error": "No se pudo cargar la información de la película.",
            },
        )
    except ValueError:
        return render(
            request,
            "detalle_pelicula.html",
            {
                "pelicula": None,
                "video_key": None,
                "dias_disponibles": [],
                "sesiones_por_dia": {},
                "asientos_por_sesion": {},
                "poster_url": "",
                "total_sesiones": 0,
                "entradas_vendidas": 0,
                "ocupacion_media": 0,
                "calificacion_edad": "No disponible",
                "resenas_pelicula": [],
                "resumen_resenas": {"media": 0, "total": 0},
                "resena_usuario": None,
                "error": "La respuesta de la API no tiene un formato válido.",
            },
        )

    pelicula["title"] = pelicula.get("title") or "Título no disponible"
    pelicula["overview"] = pelicula.get("overview") or "Sin sinopsis disponible."
    pelicula["vote_average"] = pelicula.get("vote_average") if pelicula.get("vote_average") is not None else 0
    pelicula["runtime"] = pelicula.get("runtime") or DURACION_POR_DEFECTO

    video_key = obtener_trailer_key_desde_detalle(pelicula)
    ficha_publica_completa = detalle_tiene_datos_minimos_cartelera(pelicula)

    fecha_estreno = obtener_fecha_estreno(pelicula.get("release_date"))
    hoy = datetime.now().date()
    inicio_sesion = max(hoy, fecha_estreno) if fecha_estreno else hoy

    dias_generacion = []
    for i in range(7):
        proximo_dia = inicio_sesion + timedelta(days=i)
        dias_generacion.append(
            {
                "fecha": proximo_dia.strftime("%Y-%m-%d"),
                "dia_semana": formatear_fecha_es(proximo_dia),
                "numero_dia": proximo_dia.day,
            }
        )

    pelicula_actual = {
        "id": pelicula.get("id"),
        "title": pelicula.get("title"),
        "runtime": pelicula.get("runtime"),
        "popularity": pelicula.get("popularity"),
        "vote_average": pelicula.get("vote_average"),
        "release_date": pelicula.get("release_date"),
    }

    disponibilidad_pelicula = obtener_info_disponibilidad_pelicula(movie_id)
    pelicula_en_cartelera = ficha_publica_completa and disponibilidad_pelicula["en_cartelera_principal"]
    pelicula_en_ultimas_sesiones = ficha_publica_completa and disponibilidad_pelicula["en_ultimas_sesiones"]
    pelicula_comprable = pelicula_en_cartelera or pelicula_en_ultimas_sesiones

    if ficha_publica_completa and pelicula_en_cartelera:
        crear_salas_iniciales()
        limpiar_solapamientos_futuros_misma_pelicula(movie_id=movie_id)
        salas_activas = list(Sala.objects.filter(activa=True).order_by("id"))
        dias_sin_sesion = obtener_dias_sin_sesion_futura(
            movie_id=movie_id,
            dias_disponibles=dias_generacion,
        )

        for dia in dias_sin_sesion:
            fecha_sesion = datetime.strptime(dia["fecha"], "%Y-%m-%d").date()
            asegurar_sesion_diaria_pelicula(
                pelicula=pelicula_actual,
                fecha_sesion=fecha_sesion,
                salas=salas_activas,
            )

        dias_sin_sesion = obtener_dias_sin_sesion_futura(
            movie_id=movie_id,
            dias_disponibles=dias_generacion,
        )

        if dias_sin_sesion:
            generar_programacion_para_dias(
                dias_disponibles=dias_sin_sesion,
                pelicula_actual=pelicula_actual,
            )

        reforzar_minimo_diario_cartelera(
            peliculas=[pelicula_actual],
            dias_disponibles=dias_generacion,
        )
    elif ficha_publica_completa and pelicula_en_ultimas_sesiones:
        limpiar_solapamientos_futuros_misma_pelicula(movie_id=movie_id)
    else:
        eliminar_sesiones_futuras_sin_entradas(movie_id)

    if not ficha_publica_completa:
        eliminar_sesiones_futuras_sin_entradas(movie_id)

    if pelicula_en_cartelera:
        dias_disponibles = dias_generacion
        sesiones_por_dia_objetos = obtener_sesiones_pelicula_para_dias(
            movie_id=movie_id,
            dias_disponibles=dias_disponibles,
        )
    elif pelicula_en_ultimas_sesiones:
        dias_disponibles = construir_dias_desde_sesiones_comprometidas(movie_id)
        sesiones_por_dia_objetos = obtener_sesiones_comprometidas_para_dias(
            movie_id=movie_id,
            dias_disponibles=dias_disponibles,
        )
    else:
        dias_disponibles = dias_generacion if ejecutando_tests() and ficha_publica_completa else []
        sesiones_por_dia_objetos = {}

    sesiones_por_dia = preparar_sesiones_para_template(sesiones_por_dia_objetos)
    asientos_por_sesion = preparar_asientos_por_sesion(sesiones_por_dia_objetos)

    total_sesiones = sum(len(sesiones) for sesiones in sesiones_por_dia_objetos.values())
    tiene_sesiones_disponibles = ficha_publica_completa and pelicula_comprable and total_sesiones > 0

    entradas_vendidas = (
        Entrada.objects
        .filter(movie_id=movie_id)
        .exclude(estado=Entrada.ESTADO_CANCELADA)
        .count()
    )

    ocupacion_media = 0
    sesiones_movie = SesionCine.objects.filter(movie_id=movie_id).select_related("sala")
    ocupaciones = []

    for sesion in sesiones_movie:
        capacidad = sesion.sala.filas * sesion.sala.columnas
        if capacidad > 0:
            vendidas = (
                Entrada.objects.filter(sesion=sesion)
                .exclude(estado=Entrada.ESTADO_CANCELADA)
                .count()
            )
            ocupaciones.append((vendidas / capacidad) * 100)

    if ocupaciones:
        ocupacion_media = round(sum(ocupaciones) / len(ocupaciones), 2)

    poster_url = (
        f"https://image.tmdb.org/t/p/w500{pelicula['poster_path']}"
        if pelicula.get("poster_path")
        else pelicula.get("poster_url", "")
    )

    es_favorita = (
        request.user.is_authenticated
        and not request.user.is_staff
        and Favorito.objects.filter(usuario=request.user, movie_id=movie_id).exists()
    )

    recomendaciones_detalle = obtener_recomendaciones_para_detalle(
        movie_id=movie_id,
        usuario=request.user,
        limite=6,
    )

    calificacion_edad = obtener_calificacion_edad_pelicula(movie_id, pelicula)
    resenas_pelicula = (
        Resena.objects
        .filter(movie_id=movie_id, visible=True)
        .select_related("usuario")
        .order_by("-actualizada_en")[:8]
    )
    resumen_resenas = obtener_resumen_resenas(movie_id)
    resena_usuario = None

    if request.user.is_authenticated and not request.user.is_staff:
        resena_usuario = Resena.objects.filter(
            usuario=request.user,
            movie_id=movie_id,
        ).first()

    youtube_urls = construir_urls_youtube(video_key, request)

    context = {
        "pelicula": pelicula,
        "video_key": video_key,
        "youtube_embed_url": youtube_urls["embed"],
        "youtube_watch_url": youtube_urls["watch"],
        "dias_disponibles": dias_disponibles,
        "sesiones_por_dia": sesiones_por_dia,
        "asientos_por_sesion": asientos_por_sesion,
        "poster_url": poster_url,
        "total_sesiones": total_sesiones,
        "tiene_sesiones_disponibles": tiene_sesiones_disponibles,
        "pelicula_en_cartelera": pelicula_en_cartelera,
        "pelicula_en_ultimas_sesiones": pelicula_en_ultimas_sesiones,
        "pelicula_comprable": pelicula_comprable,
        "texto_disponibilidad": disponibilidad_pelicula.get("texto_disponibilidad"),
        "entradas_vendidas": entradas_vendidas,
        "ocupacion_media": ocupacion_media,
        "calificacion_edad": calificacion_edad,
        "resenas_pelicula": resenas_pelicula,
        "resumen_resenas": resumen_resenas,
        "resena_usuario": resena_usuario,
        "es_favorita": es_favorita,
        "recomendaciones_detalle": recomendaciones_detalle,
        "ficha_publica_completa": ficha_publica_completa,
        "error": None,
    }

    return render(request, "detalle_pelicula.html", context)


@login_required
@require_POST
def guardar_resena(request, movie_id):
    if request.user.is_staff:
        messages.error(request, "Las cuentas staff no pueden publicar reseñas.")
        return redirect("detalle_pelicula", movie_id=movie_id)

    puntuacion = request.POST.get("puntuacion")
    comentario = (request.POST.get("comentario") or "").strip()

    try:
        puntuacion = int(puntuacion)
    except (TypeError, ValueError):
        messages.error(request, "La puntuación de la reseña no es válida.")
        return redirect("detalle_pelicula", movie_id=movie_id)

    if puntuacion < 1 or puntuacion > 5:
        messages.error(request, "La puntuación debe estar entre 1 y 5.")
        return redirect("detalle_pelicula", movie_id=movie_id)

    if len(comentario) > 600:
        messages.error(request, "La reseña no puede superar los 600 caracteres.")
        return redirect("detalle_pelicula", movie_id=movie_id)

    try:
        pelicula = obtener_detalle_tmdb(movie_id, exigir_datos_cartelera=False)
        titulo = pelicula.get("title") or "Película"
    except (requests.RequestException, ValueError):
        titulo = request.POST.get("titulo_pelicula") or "Película"

    Resena.objects.update_or_create(
        usuario=request.user,
        movie_id=movie_id,
        defaults={
            "titulo_pelicula": titulo,
            "puntuacion": puntuacion,
            "comentario": comentario,
            "visible": True,
        },
    )

    messages.success(request, "Tu reseña se ha guardado correctamente.")
    return redirect("detalle_pelicula", movie_id=movie_id)


@login_required
@require_POST
def eliminar_resena(request, movie_id):
    if request.user.is_staff:
        messages.error(request, "Las cuentas staff no pueden eliminar reseñas personales.")
        return redirect("detalle_pelicula", movie_id=movie_id)

    Resena.objects.filter(usuario=request.user, movie_id=movie_id).delete()
    messages.success(request, "Tu reseña se ha eliminado correctamente.")
    return redirect("detalle_pelicula", movie_id=movie_id)


def obtener_lista_asientos_post(request):
    """Lee uno o varios asientos enviados desde el formulario de compra."""
    valor = request.POST.get("asientos") or request.POST.get("asiento") or ""

    asientos = []
    vistos = set()

    for asiento in str(valor).split(","):
        asiento_limpio = asiento.strip().upper()

        if asiento_limpio and asiento_limpio not in vistos:
            asientos.append(asiento_limpio)
            vistos.add(asiento_limpio)

    return asientos


def validar_asientos_para_sesion(sesion, asientos):
    """Devuelve un mensaje de error si algún asiento no es válido."""
    if not asientos:
        return "Debes seleccionar una sesión y al menos un asiento para comprar entradas."

    asientos_validos = set(sesion.sala.obtener_asientos())

    for asiento in asientos:
        if asiento not in asientos_validos:
            return f"El asiento {asiento} no pertenece a la sala."

    asientos_ocupados = set(
        Entrada.objects
        .filter(
            sesion=sesion,
            asiento__in=asientos,
        )
        .exclude(estado=Entrada.ESTADO_CANCELADA)
        .values_list("asiento", flat=True)
    )

    if asientos_ocupados:
        ocupados = ", ".join(sorted(asientos_ocupados))
        return f"Los siguientes asientos ya están ocupados para esta sesión: {ocupados}."

    return None

def crear_entradas_con_bloqueo(usuario, sesion, asientos, bono_usado=None):
    sesion_bloqueada = (
        SesionCine.objects
        .select_for_update()
        .select_related("sala")
        .get(pk=sesion.pk)
    )

    list(
        Entrada.objects
        .select_for_update()
        .filter(sesion=sesion_bloqueada)
        .exclude(estado=Entrada.ESTADO_CANCELADA)
        .values_list("id", flat=True)
    )

    ahora = timezone.now()

    if sesion_bloqueada.fin and sesion_bloqueada.fin <= ahora:
        raise ValidationError("La sesión ya ha finalizado mientras completabas la compra.")

    if sesion_bloqueada.inicio and sesion_bloqueada.inicio <= ahora:
        raise ValidationError("La sesión ya ha comenzado mientras completabas la compra.")

    error_asientos = validar_asientos_para_sesion(sesion_bloqueada, asientos)

    if error_asientos:
        raise ValidationError(error_asientos)

    entradas_creadas = []

    for asiento in asientos:
        entradas_creadas.append(
            Entrada.objects.create(
                sesion=sesion_bloqueada,
                movie_id=sesion_bloqueada.movie_id,
                titulo_pelicula=sesion_bloqueada.titulo_pelicula,
                fecha=sesion_bloqueada.fecha,
                hora=sesion_bloqueada.hora_inicio_formateada(),
                sala=sesion_bloqueada.sala,
                asiento=asiento,
                usuario=usuario,
                bono_usado=bono_usado,
                estado=Entrada.ESTADO_ACTIVA,
            )
        )

    return entradas_creadas


@login_required
@require_POST
def confirmar_entrada(request):

    if request.user.is_staff:
        messages.error(request, "Las cuentas staff no pueden comprar entradas.")
        return redirect("panel_interno")

    sesion_id = request.POST.get("sesion_id")
    asientos = obtener_lista_asientos_post(request)

    if not sesion_id or not asientos:
        messages.error(request, "Debes seleccionar una sesión y al menos un asiento para comprar entradas.")
        return redirect("index_peliculas")

    sesion = get_object_or_404(
        SesionCine.objects.select_related("sala"),
        id=sesion_id,
    )

    ahora = timezone.now()

    if sesion.fin and sesion.fin <= ahora:
        messages.error(request, "No puedes comprar entradas para una sesión finalizada o pasada.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    if sesion.inicio and sesion.inicio <= ahora:
        messages.error(request, "No puedes comprar entradas para una sesión que ya ha empezado o pasada.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    error_asientos = validar_asientos_para_sesion(sesion, asientos)
    if error_asientos:
        messages.error(request, error_asientos)
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    codigo_bono = request.POST.get("codigo_bono", "").strip()
    cantidad_entradas = len(asientos)

    # ── FLUJO CON BONO ────────────────────────────────────────────────────────
    if codigo_bono:
        try:
            bono = Bono.objects.get(
                codigo=int(codigo_bono),
                usuario=request.user,
                fechaCaducidad__gte=date.today(),
            )
        except (Bono.DoesNotExist, ValueError):
            messages.error(request, "El bono seleccionado no es válido o ha caducado.")
            return redirect("detalle_pelicula", movie_id=sesion.movie_id)

        if bono.usos_restantes < cantidad_entradas:
            messages.error(
                request,
                f"El bono no tiene usos suficientes para {cantidad_entradas} entrada(s). "
                f"Usos disponibles: {bono.usos_restantes}."
            )
            return redirect("detalle_pelicula", movie_id=sesion.movie_id)

        try:
            with transaction.atomic():
                bono = Bono.objects.select_for_update().get(pk=bono.pk)

                if bono.usos_restantes < cantidad_entradas:
                    raise ValidationError("El bono ya no tiene usos suficientes.")

                entradas_creadas = crear_entradas_con_bloqueo(
                    usuario=request.user,
                    sesion=sesion,
                    asientos=asientos,
                    bono_usado=bono,
                )

                bono.usos_restantes -= cantidad_entradas
                bono.save(update_fields=["usos_restantes"])

            cache.delete(f"ocupacion_sesion_{sesion.id}")
            cache.delete(f"entradas_recientes_{sesion.movie_id}")

        except ValidationError as error:
            messages.error(request, error.messages[0] if hasattr(error, "messages") else str(error))
            return redirect("detalle_pelicula", movie_id=sesion.movie_id)

        except IntegrityError:
            messages.error(request, "Alguno de los asientos acaba de ser ocupado por otro usuario.")
            return redirect("detalle_pelicula", movie_id=sesion.movie_id)

        if programar_envio_correo_entradas(request.user, entradas_creadas):
            messages.info(request, mensaje_envio_correo_demo("entradas"))

        messages.success(
            request,
            f"¡Compra completada! {cantidad_entradas} entrada(s) usando el bono {bono.codigo}. "
            f"Usos restantes del bono: {bono.usos_restantes}."
        )
        return redirect("mis_entradas")

    # ── FLUJO SIN BONO: mostrar pantalla de pago ─────────────────────────────
    bonos_disponibles = Bono.objects.filter(
        usuario=request.user,
        fechaCaducidad__gte=date.today(),
        usos_restantes__gte=cantidad_entradas,
    ).order_by("fechaCaducidad", "codigo")

    return render(
        request,
        "confirmar_entrada.html",
        {
            "sesion": sesion,
            "asiento": asientos[0],
            "asientos": asientos,
            "asientos_texto": ", ".join(asientos),
            "cantidad_entradas": cantidad_entradas,
            "movie_id": sesion.movie_id,
            "titulo_pelicula": sesion.titulo_pelicula,
            "fecha": sesion.fecha,
            "hora": sesion.hora_inicio_formateada(),
            "hora_fin": sesion.hora_fin_formateada(),
            "duracion": sesion.duracion_minutos,
            "sala": sesion.sala,
            "bonos_disponibles": bonos_disponibles,
        },
    )


@login_required
@require_POST
def comprar_entrada(request):
    if request.user.is_staff:
        messages.error(request, "Las cuentas staff no pueden comprar entradas.")
        return redirect("panel_interno")

    sesion_id = request.POST.get("sesion_id")
    asientos = obtener_lista_asientos_post(request)
    codigo_bono = request.POST.get("codigo_bono", "").strip()

    if not sesion_id or not asientos:
        messages.error(request, "No se pudo completar la compra porque faltan datos.")
        return redirect("index_peliculas")

    sesion = get_object_or_404(
        SesionCine.objects.select_related("sala"),
        id=sesion_id,
    )

    if not codigo_bono:
        if sesion.inicio and sesion.inicio <= timezone.now():
            messages.error(request, "No puedes comprar entradas para una sesión que ya ha empezado o pasada.")
            return redirect("detalle_pelicula", movie_id=sesion.movie_id)

        error_asientos = validar_asientos_para_sesion(sesion, asientos)

        if error_asientos:
            messages.error(request, error_asientos)
            return redirect("detalle_pelicula", movie_id=sesion.movie_id)

        try:
            with transaction.atomic():
                entradas_creadas = crear_entradas_con_bloqueo(
                    usuario=request.user,
                    sesion=sesion,
                    asientos=asientos,
                )

            cache.delete(f"ocupacion_sesion_{sesion.id}")
            cache.delete(f"entradas_recientes_{sesion.movie_id}")

        except ValidationError as error:
            messages.error(request, error.messages[0] if hasattr(error, "messages") else str(error))
            return redirect("detalle_pelicula", movie_id=sesion.movie_id)

        except IntegrityError:
            messages.error(request, "Alguno de los asientos seleccionados acaba de ser ocupado por otro usuario.")
            return redirect("detalle_pelicula", movie_id=sesion.movie_id)

        if programar_envio_correo_entradas(request.user, entradas_creadas):
            messages.info(request, mensaje_envio_correo_demo("entradas"))

        messages.success(request, f"Compra completada: {len(asientos)} entrada(s).")
        return redirect("mis_entradas")

    if sesion.inicio and sesion.inicio <= timezone.now():
        messages.error(request, "No puedes comprar entradas para una sesión que ya ha empezado o pasada.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    error_asientos = validar_asientos_para_sesion(sesion, asientos)

    if error_asientos:
        messages.error(request, error_asientos)
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    cantidad_entradas = len(asientos)

    try:
        bono_usado = Bono.objects.get(
            codigo=int(codigo_bono),
            usuario=request.user,
            fechaCaducidad__gte=date.today(),
        )
    except (Bono.DoesNotExist, ValueError):
        messages.error(request, "El código de bono introducido no es válido o está caducado.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    if bono_usado.usos_restantes < cantidad_entradas:
        messages.error(
            request,
            f"El bono seleccionado no tiene usos suficientes para {cantidad_entradas} entradas.",
        )
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    try:
        with transaction.atomic():
            bono_usado = Bono.objects.select_for_update().get(pk=bono_usado.pk)

            if bono_usado.usos_restantes < cantidad_entradas:
                raise ValidationError("El bono ya no tiene usos suficientes.")

            entradas_creadas = crear_entradas_con_bloqueo(
                usuario=request.user,
                sesion=sesion,
                asientos=asientos,
                bono_usado=bono_usado,
            )

            bono_usado.usos_restantes -= cantidad_entradas
            bono_usado.save(update_fields=["usos_restantes"])

        cache.delete(f"ocupacion_sesion_{sesion.id}")
        cache.delete(f"entradas_recientes_{sesion.movie_id}")

    except ValidationError as error:
        messages.error(request, error.messages[0] if hasattr(error, "messages") else str(error))
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    except IntegrityError:
        messages.error(request, "Alguno de los asientos seleccionados acaba de ser ocupado por otro usuario.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    if programar_envio_correo_entradas(request.user, entradas_creadas):
        messages.info(request, mensaje_envio_correo_demo("entradas"))

    messages.success(
        request,
        f"Compra completada: {cantidad_entradas} entrada(s) usando el bono {bono_usado.codigo}.",
    )
    return redirect("mis_entradas")

def actualizar_entradas_caducadas_usuario(usuario):
    ahora = timezone.now()

    Entrada.objects.filter(
        usuario=usuario,
        estado=Entrada.ESTADO_ACTIVA,
        sesion__fin__lte=ahora,
    ).update(estado=Entrada.ESTADO_CADUCADA)

    Entrada.objects.filter(
        usuario=usuario,
        estado=Entrada.ESTADO_CADUCADA,
        sesion__fin__gt=ahora,
    ).update(estado=Entrada.ESTADO_ACTIVA)


def obtener_ip_cliente(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def registrar_validacion_entrada(request, codigo_verificacion, entrada, resultado, detalle=""):
    usuario_staff = None
    if request.user.is_authenticated and request.user.is_staff:
        usuario_staff = request.user

    try:
        ValidacionEntrada.objects.create(
            entrada=entrada,
            codigo_verificacion=str(codigo_verificacion or "")[:80],
            resultado=resultado,
            detalle=str(detalle or "")[:255],
            usuario_staff=usuario_staff,
            ip=obtener_ip_cliente(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        )
    except Exception:
        logger.exception("No se pudo registrar la validación de la entrada.")

def construir_codigo_verificacion_entrada(entrada):
    return f"FICINEMA-{entrada.codigo}-{entrada.usuario_id}"


def obtener_entrada_por_codigo_verificacion(codigo_verificacion):
    patron = r"^FICINEMA-(\d+)-(\d+)$"
    coincidencia = re.match(patron, codigo_verificacion.strip(), re.IGNORECASE)

    if not coincidencia:
        return None

    codigo_entrada = int(coincidencia.group(1))
    usuario_id = int(coincidencia.group(2))

    return (
        Entrada.objects.select_related("usuario", "sesion", "sala", "bono_usado")
        .filter(codigo=codigo_entrada, usuario_id=usuario_id)
        .first()
    )


def obtener_resultado_verificacion_entrada(entrada):
    if not entrada:
        return {
            "tipo": "error",
            "titulo": "Entrada no encontrada",
            "mensaje": "El código escaneado no corresponde con ninguna entrada registrada en FICinema.",
            "valida": False,
        }

    entrada.marcar_caducada_si_corresponde()

    if entrada.estado == Entrada.ESTADO_ACTIVA:
        return {
            "tipo": "success",
            "titulo": "Entrada válida",
            "mensaje": "La entrada existe, está activa y puede validarse para acceder a la sala.",
            "valida": True,
        }

    if entrada.estado == Entrada.ESTADO_CANCELADA:
        return {
            "tipo": "error",
            "titulo": "Entrada cancelada",
            "mensaje": "Esta entrada fue cancelada y no permite el acceso a la sala.",
            "valida": False,
        }

    if entrada.estado == Entrada.ESTADO_CADUCADA:
        return {
            "tipo": "warning",
            "titulo": "Entrada caducada",
            "mensaje": "La sesión asociada a esta entrada ya ha finalizado.",
            "valida": False,
        }

    if entrada.estado == Entrada.ESTADO_USADA:
        return {
            "tipo": "warning",
            "titulo": "Entrada ya usada",
            "mensaje": "Esta entrada ya fue validada previamente.",
            "valida": False,
        }

    return {
        "tipo": "warning",
        "titulo": "Estado no verificable",
        "mensaje": "La entrada existe, pero su estado actual no permite validarla automáticamente.",
        "valida": False,
    }


def construir_payload_qr_entrada(entrada, request=None):
    return construir_url_verificacion_entrada(entrada, request=request)


@login_required
def qr_entrada(request, entrada_id):
    entrada = get_object_or_404(
        Entrada.objects.select_related("usuario", "sesion", "sala"),
        id=entrada_id,
    )

    if not request.user.is_staff and entrada.usuario_id != request.user.id:
        return HttpResponse("No tienes permisos para ver este código QR.", status=403)

    entrada.marcar_caducada_si_corresponde()

    if entrada.estado != Entrada.ESTADO_ACTIVA:
        return HttpResponse(
            "Esta entrada no tiene QR de acceso activo.",
            status=410,
        )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(construir_payload_qr_entrada(entrada, request=request))
    qr.make(fit=True)

    imagen = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    imagen.save(buffer, format="PNG")
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Content-Disposition"] = f'inline; filename="entrada-{entrada.codigo}-qr.png"'

    return response



def generar_entrada_pdf_bytes(entrada, request=None):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("No se puede generar el PDF porque falta la dependencia reportlab.") from exc

    entrada.marcar_caducada_si_corresponde()

    codigo_verificacion = construir_codigo_verificacion_entrada(entrada)
    url_verificacion = construir_url_verificacion_entrada(entrada, request=request)
    entrada_verificable = entrada.estado == Entrada.ESTADO_ACTIVA

    qr_buffer = None

    if entrada_verificable:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(url_verificacion)
        qr.make(fit=True)

        qr_buffer = BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(qr_buffer, format="PNG")
        qr_buffer.seek(0)

    pdf_buffer = BytesIO()

    documento = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Entrada FICinema {entrada.codigo}",
    )

    estilos = getSampleStyleSheet()
    estilos.add(
        ParagraphStyle(
            name="FICinemaTitle",
            parent=estilos["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            textColor=colors.HexColor("#0d252a"),
            spaceAfter=8,
        )
    )
    estilos.add(
        ParagraphStyle(
            name="FICinemaSubtitle",
            parent=estilos["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#4f5f66"),
            spaceAfter=16,
        )
    )
    estilos.add(
        ParagraphStyle(
            name="FICinemaSmall",
            parent=estilos["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#4f5f66"),
        )
    )

    logo_path = os.path.join(settings.BASE_DIR, "static", "images", "FICinema.jpg")

    sala = entrada.sala.nombre if entrada.sala else "No asignada"
    bono = f"Bono {entrada.bono_usado.codigo} - {entrada.bono_usado.tipo}" if entrada.bono_usado else "No utilizado"
    hora_inicio = entrada.sesion.hora_inicio_formateada() if entrada.sesion else entrada.hora
    hora_fin = entrada.sesion.hora_fin_formateada() if entrada.sesion else "No disponible"
    duracion = f"{entrada.sesion.duracion_minutos} minutos" if entrada.sesion else "No disponible"
    usuario = entrada.usuario.get_full_name() or entrada.usuario.username

    datos_entrada = [
        ["Código", codigo_verificacion],
        ["Película", entrada.titulo_pelicula or "No disponible"],
        ["Fecha", entrada.fecha.strftime("%d/%m/%Y") if entrada.fecha else "No disponible"],
        ["Hora", f"{hora_inicio} - {hora_fin}"],
        ["Duración", duracion],
        ["Sala", sala],
        ["Asiento", entrada.asiento or "No asignado"],
        ["Estado", entrada.get_estado_display()],
        ["Cliente", usuario],
        ["Bono", bono],
        ["Compra", timezone.localtime(entrada.fechaCompra).strftime("%d/%m/%Y %H:%M")],
    ]

    tabla_datos = Table(datos_entrada, colWidths=[38 * mm, 100 * mm])
    tabla_datos.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#0d252a")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#f4f7fb")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    if entrada_verificable:
        qr_imagen = Image(qr_buffer, width=48 * mm, height=48 * mm)
        bloque_qr = Table(
            [
                [qr_imagen],
                [Paragraph("Escanea este QR para verificar la entrada", estilos["FICinemaSmall"])],
                [Paragraph(codigo_verificacion, estilos["FICinemaSmall"])],
            ],
            colWidths=[58 * mm],
        )
        bloque_qr_background = colors.HexColor("#f8fafc")
        bloque_qr_box_color = colors.HexColor("#0d252a")
    else:
        bloque_qr = Table(
            [
                [Paragraph("ENTRADA NO VÁLIDA PARA ACCESO", estilos["FICinemaSubtitle"])],
                [Paragraph("Esta entrada está cancelada, caducada o usada. Se conserva como justificante, pero no dispone de QR de acceso activo.", estilos["FICinemaSmall"])],
                [Paragraph(codigo_verificacion, estilos["FICinemaSmall"])],
            ],
            colWidths=[58 * mm],
        )
        bloque_qr_background = colors.HexColor("#f1f5f9")
        bloque_qr_box_color = colors.HexColor("#64748b")

    bloque_qr.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.8, bloque_qr_box_color),
                ("BACKGROUND", (0, 0), (-1, -1), bloque_qr_background),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    cabecera = []

    if os.path.exists(logo_path):
        cabecera.append(Image(logo_path, width=22 * mm, height=22 * mm))

    cabecera.extend(
        [
            Paragraph("FICinema", estilos["FICinemaTitle"]),
            Paragraph("Entrada digital con código QR verificable", estilos["FICinemaSubtitle"]),
        ]
    )

    contenido = [
        *cabecera,
        Spacer(1, 6 * mm),
        Table(
            [[tabla_datos, bloque_qr]],
            colWidths=[125 * mm, 58 * mm],
            hAlign="LEFT",
        ),
        Spacer(1, 10 * mm),
        Paragraph(
            "Este documento funciona como justificante de entrada. El acceso a la sala queda condicionado a que el QR figure como válido en el sistema interno de FICinema.",
            estilos["FICinemaSmall"],
        ),
        Spacer(1, 4 * mm),
        Paragraph(
            f"URL de verificación {'activa' if entrada_verificable else 'histórica'}: {url_verificacion}",
            estilos["FICinemaSmall"],
        ),
    ]

    documento.build(contenido)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


def _lanzar_tarea_correo(nombre_tarea, funcion, *args, **kwargs):
    def ejecutar():
        close_old_connections()
        try:
            funcion(*args, **kwargs)
        except Exception:
            logger.exception("Error inesperado en la tarea de correo %s.", nombre_tarea)
        finally:
            close_old_connections()

    hilo = threading.Thread(target=ejecutar, name=nombre_tarea, daemon=True)
    hilo.start()


def hay_destinatario_correo(usuario):
    destinatario_pruebas = getattr(settings, "EMAIL_TEST_RECIPIENT_OVERRIDE", "").strip()
    email_usuario = getattr(usuario, "email", "").strip()

    return bool(destinatario_pruebas or email_usuario)


def mensaje_envio_correo_demo(tipo="entradas"):
    destinatario_pruebas = getattr(settings, "EMAIL_TEST_RECIPIENT_OVERRIDE", "").strip()

    if destinatario_pruebas:
        if tipo == "bono":
            return (
                "Se ha generado el bono correctamente. En modo demo, la confirmación "
                "por correo se envía a la cuenta de pruebas configurada de FICinema."
            )

        return (
            "Se han generado las entradas correctamente. En modo demo, el correo con "
            "los PDF se envía a la cuenta de pruebas configurada de FICinema."
        )

    if tipo == "bono":
        return "Te enviaremos la confirmación del bono a tu correo electrónico."

    return "Te enviaremos las entradas en PDF a tu correo electrónico."


def programar_envio_correo_entradas(usuario, entradas, referencia=None):
    entradas_ids = [entrada.id for entrada in entradas]

    if not hay_destinatario_correo(usuario) or not entradas_ids:
        return False

    usuario_id = usuario.id

    def enviar_despues_commit():
        _lanzar_tarea_correo(
            "ficinema-correo-entradas",
            _enviar_correo_entradas_por_ids,
            usuario_id,
            entradas_ids,
            referencia,
        )

    transaction.on_commit(enviar_despues_commit)
    return True


def _enviar_correo_entradas_por_ids(usuario_id, entradas_ids, referencia=None):
    usuario = Usuario.objects.get(id=usuario_id)
    entradas_por_id = {
        entrada.id: entrada
        for entrada in Entrada.objects.select_related("usuario", "sesion", "sala", "bono_usado").filter(id__in=entradas_ids)
    }
    entradas = [entradas_por_id[entrada_id] for entrada_id in entradas_ids if entrada_id in entradas_por_id]
    enviar_correo_entradas_compra(usuario, entradas, request=None, referencia=referencia)


def programar_envio_correo_bono(usuario, bono, precio, referencia=None):
    if not hay_destinatario_correo(usuario) or bono is None:
        return False

    usuario_id = usuario.id
    bono_id = bono.id

    def enviar_despues_commit():
        _lanzar_tarea_correo(
            "ficinema-correo-bono",
            _enviar_correo_bono_por_id,
            usuario_id,
            bono_id,
            precio,
            referencia,
        )

    transaction.on_commit(enviar_despues_commit)
    return True


def _enviar_correo_bono_por_id(usuario_id, bono_id, precio, referencia=None):
    usuario = Usuario.objects.get(id=usuario_id)
    bono = Bono.objects.get(id=bono_id)
    enviar_correo_bono_compra(usuario, bono, precio, referencia=referencia)


def obtener_destinatarios_correo(usuario):
    destinatario_pruebas = getattr(settings, "EMAIL_TEST_RECIPIENT_OVERRIDE", "").strip()
    if destinatario_pruebas:
        return [destinatario_pruebas]

    if getattr(usuario, "email", ""):
        return [usuario.email]

    return []


def enviar_correo_entradas_compra(usuario, entradas, request=None, referencia=None):
    destinatarios = obtener_destinatarios_correo(usuario)
    if not destinatarios:
        return False

    entradas = list(entradas)

    if not entradas:
        return False

    lineas = [
        f"Hola {usuario.get_full_name() or usuario.username},",
        "",
        "Adjuntamos tus entradas digitales de FICinema en PDF.",
        "Cada PDF incluye el código de verificación que deberá aparecer como activo para acceder a la sala.",
        "",
        "Resumen de la compra:",
    ]

    for entrada in entradas:
        sala = entrada.sala.nombre if entrada.sala else "Sala no asignada"
        lineas.append(
            f"- {entrada.titulo_pelicula} · {entrada.fecha.strftime('%d/%m/%Y')} · "
            f"{entrada.hora} · {sala} · asiento {entrada.asiento}"
        )

    if referencia:
        lineas.extend(["", f"Referencia de pago: {referencia}"])

    lineas.extend([
        "",
        "También puedes consultar y descargar tus entradas desde el apartado Mis entradas.",
        "",
        "FICinema",
    ])

    email = EmailMessage(
        subject=f"Tus entradas FICinema ({len(entradas)})",
        body="\n".join(lineas),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=destinatarios,
    )

    try:
        for entrada in entradas:
            pdf_bytes = generar_entrada_pdf_bytes(entrada, request=request)
            email.attach(
                filename=f"entrada-ficinema-{entrada.codigo}.pdf",
                content=pdf_bytes,
                mimetype="application/pdf",
            )

        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("No se pudo enviar el correo con las entradas de la compra.")
        return False


def enviar_correo_bono_compra(usuario, bono, precio, referencia=None):
    destinatarios = obtener_destinatarios_correo(usuario)
    if not destinatarios:
        return False

    cuerpo = [
        f"Hola {usuario.get_full_name() or usuario.username},",
        "",
        "Tu bono de FICinema se ha comprado correctamente.",
        "",
        f"Código de bono: {bono.codigo}",
        f"Tipo: {bono.tipo} - {bono.get_tipo_display()}",
        f"Usos disponibles: {bono.usos_restantes}",
        f"Fecha de caducidad: {bono.fechaCaducidad.strftime('%d/%m/%Y')}",
        f"Importe: {precio:.2f} €",
    ]

    if referencia:
        cuerpo.append(f"Referencia de pago: {referencia}")

    cuerpo.extend([
        "",
        "Puedes revisar tus bonos desde tu zona personal de FICinema.",
        "",
        "FICinema",
    ])

    email = EmailMessage(
        subject=f"Confirmación de bono FICinema {bono.tipo}",
        body="\n".join(cuerpo),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=destinatarios,
    )

    try:
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("No se pudo enviar el correo de confirmación del bono.")
        return False


@login_required
def descargar_entrada_pdf(request, entrada_id):
    entrada = get_object_or_404(
        Entrada.objects.select_related("usuario", "sesion", "sala", "bono_usado"),
        id=entrada_id,
    )

    if not request.user.is_staff and entrada.usuario_id != request.user.id:
        return HttpResponse("No tienes permisos para descargar esta entrada.", status=403)

    try:
        pdf_bytes = generar_entrada_pdf_bytes(entrada, request=request)
    except RuntimeError as error:
        return HttpResponse(str(error), status=500)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="entrada-ficinema-{entrada.codigo}.pdf"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"

    return response


def verificar_entrada(request, codigo_verificacion):
    codigo_verificacion = str(codigo_verificacion or "").strip().upper()
    entrada = obtener_entrada_por_codigo_verificacion(codigo_verificacion)
    validacion_realizada = False

    if request.method == "POST":
        if not request.user.is_authenticated or not request.user.is_staff:
            registrar_validacion_entrada(
                request,
                codigo_verificacion,
                entrada,
                ValidacionEntrada.RESULTADO_SIN_PERMISO,
                "Intento de validación sin permisos de staff.",
            )
            messages.error(request, "Solo el personal staff puede validar entradas.")
            return redirect("verificar_entrada", codigo_verificacion=codigo_verificacion)

        if not entrada:
            registrar_validacion_entrada(
                request,
                codigo_verificacion,
                None,
                ValidacionEntrada.RESULTADO_NO_ENCONTRADA,
                "Código inexistente o con formato no reconocido.",
            )
            messages.error(request, "No se puede validar una entrada inexistente.")
            return redirect("verificar_entrada", codigo_verificacion=codigo_verificacion)

        entrada.marcar_caducada_si_corresponde()

        if entrada.estado == Entrada.ESTADO_ACTIVA:
            with transaction.atomic():
                actualizadas = Entrada.objects.select_for_update().filter(
                    pk=entrada.pk,
                    estado=Entrada.ESTADO_ACTIVA,
                ).update(estado=Entrada.ESTADO_USADA)

            if actualizadas:
                entrada.refresh_from_db()
                cache.delete(f"ocupacion_sesion_{entrada.sesion_id}")
                registrar_validacion_entrada(
                    request,
                    codigo_verificacion,
                    entrada,
                    ValidacionEntrada.RESULTADO_VALIDA,
                    "Entrada marcada como usada por control de acceso.",
                )
                messages.success(
                    request,
                    f"Acceso validado correctamente. Entrada #{entrada.codigo} marcada como usada.",
                )
            else:
                registrar_validacion_entrada(
                    request,
                    codigo_verificacion,
                    entrada,
                    ValidacionEntrada.RESULTADO_YA_USADA,
                    "La entrada cambió de estado durante la validación.",
                )
                messages.warning(
                    request,
                    "La entrada ya no estaba activa en el momento de validarla.",
                )

        elif entrada.estado == Entrada.ESTADO_USADA:
            registrar_validacion_entrada(
                request,
                codigo_verificacion,
                entrada,
                ValidacionEntrada.RESULTADO_YA_USADA,
                "Intento de validar una entrada ya usada.",
            )
            messages.warning(request, "Esta entrada ya había sido validada anteriormente.")
        elif entrada.estado == Entrada.ESTADO_CANCELADA:
            registrar_validacion_entrada(
                request,
                codigo_verificacion,
                entrada,
                ValidacionEntrada.RESULTADO_CANCELADA,
                "Intento de validar una entrada cancelada.",
            )
            messages.error(request, "No se puede validar una entrada cancelada.")
        elif entrada.estado == Entrada.ESTADO_CADUCADA:
            registrar_validacion_entrada(
                request,
                codigo_verificacion,
                entrada,
                ValidacionEntrada.RESULTADO_CADUCADA,
                "Intento de validar una entrada caducada.",
            )
            messages.error(request, "No se puede validar una entrada caducada.")
        else:
            registrar_validacion_entrada(
                request,
                codigo_verificacion,
                entrada,
                ValidacionEntrada.RESULTADO_ERROR,
                "Estado no contemplado en la validación.",
            )
            messages.error(request, "El estado actual de la entrada no permite validarla.")

        return redirect("verificar_entrada", codigo_verificacion=codigo_verificacion)

    resultado = obtener_resultado_verificacion_entrada(entrada)
    ultimas_validaciones = []
    if entrada:
        ultimas_validaciones = entrada.validaciones.select_related("usuario_staff")[:5]

    return render(
        request,
        "verificar_entrada.html",
        {
            "entrada": entrada,
            "codigo_verificacion": codigo_verificacion,
            "resultado": resultado,
            "validacion_realizada": validacion_realizada,
            "ultimas_validaciones": ultimas_validaciones,
            "puede_validar_staff": bool(
                request.user.is_authenticated
                and request.user.is_staff
                and entrada
                and entrada.estado == Entrada.ESTADO_ACTIVA
                and resultado.get("valida")
            ),
        },
    )

@login_required
@require_POST
def alternar_favorito(request):
    """
    Añade o elimina una película de favoritos.

    Feedback pensado para UX:
    - Desde cartelera: no se muestran mensajes globales para no acumular avisos.
      El botón cambia de estado visualmente al guardar o quitar la película.
    - Desde detalle y favoritos: sí se muestra un mensaje corto porque la acción
      se hace dentro de una pantalla concreta.
    """
    if request.user.is_staff:
        messages.error(
            request,
            "Las cuentas staff no pueden guardar favoritos."
        )
        return redirect("index_peliculas")

    siguiente_url = (
        request.POST.get("next")
        or request.META.get("HTTP_REFERER")
        or reverse("index_peliculas")
    )

    origen = request.POST.get("origen", "").strip()
    mostrar_mensaje = origen in ["detalle", "favoritos", "recomendaciones"]

    movie_id = (
        request.POST.get("movie_id")
        or request.POST.get("pelicula_id")
        or request.POST.get("id")
        or ""
    ).strip()

    if not movie_id:
        if mostrar_mensaje:
            messages.error(request, "No se pudo identificar la película.")
        return redirect(siguiente_url)

    try:
        movie_id = int(movie_id)
    except (TypeError, ValueError):
        if mostrar_mensaje:
            messages.error(request, "El identificador de la película no es válido.")
        return redirect(siguiente_url)

    favorito_existente = Favorito.objects.filter(
        usuario=request.user,
        movie_id=movie_id,
    ).first()

    if favorito_existente:
        favorito_existente.delete()

        if mostrar_mensaje:
            messages.success(request, "Película eliminada de favoritos.")

        return redirect(siguiente_url)

    titulo = (
        request.POST.get("titulo")
        or request.POST.get("title")
        or request.POST.get("titulo_pelicula")
        or "Título no disponible"
    ).strip()

    poster_url = (
        request.POST.get("poster_url")
        or request.POST.get("poster")
        or ""
    ).strip()

    sinopsis = (
        request.POST.get("sinopsis")
        or request.POST.get("overview")
        or "Sin sinopsis disponible."
    ).strip()

    fecha_estreno = (
        request.POST.get("fecha_estreno")
        or request.POST.get("release_date")
        or ""
    ).strip()

    valoracion_raw = (
        request.POST.get("valoracion")
        or request.POST.get("vote_average")
        or "0"
    )

    try:
        valoracion = float(str(valoracion_raw).replace(",", "."))
    except (TypeError, ValueError):
        valoracion = 0

    if not titulo or titulo == "Título no disponible" or not poster_url:
        try:
            detalle = obtener_detalle_tmdb(movie_id)

            titulo = detalle.get("title") or titulo or "Título no disponible"
            sinopsis = detalle.get("overview") or sinopsis or "Sin sinopsis disponible."
            fecha_estreno = detalle.get("release_date") or fecha_estreno
            valoracion = detalle.get("vote_average") or valoracion

            if detalle.get("poster_path"):
                poster_url = f"https://image.tmdb.org/t/p/w500{detalle['poster_path']}"
            elif detalle.get("poster_url"):
                poster_url = detalle.get("poster_url")

        except Exception:
            # Si TMDB falla, guardamos igualmente el favorito con los datos
            # que venían del formulario para no romper la experiencia.
            pass

    try:
        Favorito.objects.create(
            usuario=request.user,
            movie_id=movie_id,
            titulo=titulo or "Título no disponible",
            poster_url=poster_url,
            sinopsis=sinopsis or "Sin sinopsis disponible.",
            fecha_estreno=fecha_estreno,
            valoracion=valoracion,
        )

        if mostrar_mensaje:
            messages.success(request, "Película añadida a favoritos.")

    except IntegrityError:
        # Protección extra por si el usuario hace doble clic muy rápido.
        if mostrar_mensaje:
            messages.info(request, "La película ya estaba en favoritos.")

    except Exception as error:
        logger.exception("Error al actualizar favorito")

        if mostrar_mensaje:
            messages.error(request, "No se pudo actualizar el favorito.")

    return redirect(siguiente_url)

@login_required
def mis_favoritos(request):
    if request.user.is_staff:
        messages.error(request, "Las cuentas staff no tienen favoritos personales.")
        return redirect("panel_interno")

    favoritos_usuario = list(
        Favorito.objects.filter(usuario=request.user)
        .order_by("-creado_en", "titulo")
    )

    for favorito in favoritos_usuario:
        disponibilidad = obtener_info_disponibilidad_pelicula(favorito.movie_id)
        favorito.tiene_sesiones = disponibilidad["tiene_sesiones"]
        favorito.en_cartelera_visible = disponibilidad["en_cartelera_visible"]
        favorito.en_cartelera_principal = disponibilidad["en_cartelera_principal"]
        favorito.en_ultimas_sesiones = disponibilidad["en_ultimas_sesiones"]
        favorito.sesiones_futuras = disponibilidad["sesiones_futuras"]
        favorito.texto_disponibilidad = disponibilidad["texto_disponibilidad"]

    favoritos_usuario = enriquecer_objetos_favoritos_con_resenas(favoritos_usuario)

    return render(
        request,
        "favoritos.html",
        {
            "favoritos": favoritos_usuario,
        },
    )


@login_required
def mis_recomendaciones(request):
    if request.user.is_staff:
        messages.error(request, "Las cuentas staff tienen el panel interno para analizar la cartelera.")
        return redirect("panel_interno")

    genero_filtro = request.GET.get("genero", "").strip()
    nombre_genero_filtro = ""

    if genero_filtro:
        try:
            genero_filtro_int = int(genero_filtro)
            nombre_genero_filtro = TMDB_GENEROS.get(genero_filtro_int, "")
        except (TypeError, ValueError):
            genero_filtro = ""
            genero_filtro_int = None
        else:
            genero_filtro = str(genero_filtro_int) if nombre_genero_filtro else ""
    else:
        genero_filtro_int = None

    generos_interes = obtener_generos_interes_usuario(request.user)
    favoritos_ids = obtener_ids_favoritos_usuario(request.user)
    compradas_ids = obtener_ids_peliculas_compradas_usuario(request.user)

    recomendaciones_base = obtener_recomendaciones_para_usuario(
        usuario=request.user,
        limite=18,
    )

    recomendaciones_genero = []

    if genero_filtro:
        ids_excluir_genero = favoritos_ids | compradas_ids
        recomendaciones_genero = obtener_recomendaciones_tmdb_por_genero(
            genero_filtro,
            excluir_ids=ids_excluir_genero,
            limite=24,
        )

        if not recomendaciones_genero:
            recomendaciones_genero = obtener_recomendaciones_tmdb_por_genero(
                genero_filtro,
                excluir_ids=set(),
                limite=24,
            )

        # Al filtrar, las recomendaciones del género van primero. Si hay cartelera
        # del mismo género, aparecerá con botón de sesiones; el resto queda como
        # ficha informativa para guardar, estilo catálogo de streaming.
        recomendaciones_base = combinar_recomendaciones_sin_duplicados(
            recomendaciones_genero,
            filtrar_recomendaciones_por_genero(recomendaciones_base, genero_filtro),
            recomendaciones_base,
            limite=42,
        )

    recomendaciones_base = aplicar_prioridad_generos_recomendaciones(
        recomendaciones_base,
        generos_interes,
    )
    recomendaciones_base = enriquecer_recomendaciones_con_resenas(recomendaciones_base)

    generos_disponibles = obtener_catalogo_generos_recomendaciones(
        generos_interes,
        recomendaciones_base,
    )

    recomendaciones_usuario = filtrar_recomendaciones_por_genero(
        recomendaciones_base,
        genero_filtro,
    )[:18]

    if genero_filtro and not recomendaciones_usuario and recomendaciones_genero:
        recomendaciones_usuario = recomendaciones_genero[:18]

    recomendaciones_con_sesiones, recomendaciones_sin_sesiones = separar_recomendaciones_por_disponibilidad(
        recomendaciones_usuario
    )

    return render(
        request,
        "recomendaciones.html",
        {
            "recomendaciones_usuario": recomendaciones_usuario,
            "recomendaciones_con_sesiones": recomendaciones_con_sesiones,
            "recomendaciones_sin_sesiones": recomendaciones_sin_sesiones,
            "generos_interes": generos_interes,
            "generos_disponibles": generos_disponibles,
            "genero_filtro": genero_filtro,
            "nombre_genero_filtro": nombre_genero_filtro,
            "total_recomendaciones_base": len(recomendaciones_base),
        },
    )



@login_required
def mis_entradas(request):

    if request.user.is_staff:
        messages.error(
            request,
            "Las cuentas staff no tienen entradas personales."
        )
        return redirect("panel_interno")

    actualizar_entradas_caducadas_usuario(request.user)

    ahora = timezone.now()
    estado_filtro = request.GET.get("estado", "todas").strip().upper()
    busqueda = request.GET.get("q", "").strip()
    estados_permitidos = {
        "TODAS",
        Entrada.ESTADO_ACTIVA,
        Entrada.ESTADO_USADA,
        Entrada.ESTADO_CADUCADA,
        Entrada.ESTADO_CANCELADA,
    }

    if estado_filtro not in estados_permitidos:
        estado_filtro = "TODAS"

    entradas_base = (
        Entrada.objects
        .filter(usuario=request.user)
        .select_related("sala", "sesion", "bono_usado")
    )

    if busqueda:
        entradas_base = entradas_base.filter(
            Q(titulo_pelicula__icontains=busqueda)
            | Q(asiento__icontains=busqueda)
            | Q(sala__nombre__icontains=busqueda)
            | Q(codigo__icontains=busqueda)
        )

    entradas_activas_base = entradas_base.filter(
        estado=Entrada.ESTADO_ACTIVA,
        sesion__fin__gt=ahora,
    )

    if estado_filtro in {"TODAS", Entrada.ESTADO_ACTIVA}:
        entradas_activas = entradas_activas_base.order_by("sesion__inicio", "codigo")
    else:
        entradas_activas = Entrada.objects.none()

    entradas_historial = entradas_base.exclude(id__in=entradas_activas_base.values("id"))
    if estado_filtro != "TODAS":
        entradas_historial = entradas_historial.filter(estado=estado_filtro)
    entradas_historial = entradas_historial.order_by("-fechaCompra", "-codigo")

    resumen_estados = dict(
        Entrada.objects
        .filter(usuario=request.user)
        .values_list("estado")
        .annotate(total=Count("id"))
    )

    return render(
        request,
        "mis_entradas.html",
        {
            "entradas_usuario": entradas_activas,
            "entradas_activas": entradas_activas,
            "entradas_historial": entradas_historial,
            "estado_filtro": estado_filtro,
            "busqueda_entradas": busqueda,
            "resumen_estados": resumen_estados,
            "total_entradas_usuario": sum(resumen_estados.values()),
        },
    )

@login_required
@require_POST
def cancelar_entrada(request, entrada_id):
    entrada = get_object_or_404(
        Entrada.objects.select_related("sesion", "bono_usado"),
        id=entrada_id,
        usuario=request.user,
    )

    try:
        entrada.cancelar_y_devolver_bono()
        cache.delete(f"ocupacion_sesion_{entrada.sesion_id}")
    except ValidationError:
        messages.error(request, "Esta entrada no se puede cancelar porque la sesión ya empezó o ya no está activa.")
        return redirect("mis_entradas")

    if entrada.bono_usado:
        messages.success(request, "Entrada cancelada correctamente. Se ha devuelto 1 uso al bono utilizado.")
    else:
        messages.success(request, "Entrada cancelada correctamente.")

    return redirect("mis_entradas")

@login_required
@require_POST
def cancelar_entrada_staff(request, entrada_id):

    if not request.user.is_staff:
        messages.error(
            request,
            "No tienes permisos."
        )
        return redirect("index_peliculas")

    entrada = get_object_or_404(
        Entrada.objects.select_related(
            "sesion",
            "bono_usado",
            "usuario",
        ),
        id=entrada_id,
    )

    if entrada.estado != Entrada.ESTADO_ACTIVA:
        messages.error(
            request,
            "La entrada ya no está activa."
        )
        return redirect("panel_entradas")

    try:
        entrada.cancelar_y_devolver_bono()
        cache.delete(f"ocupacion_sesion_{entrada.sesion_id}")

    except ValidationError:

        messages.error(
            request,
            "No se pudo cancelar la entrada."
        )

        return redirect("panel_entradas")

    messages.success(
        request,
        f"Entrada #{entrada.codigo} cancelada correctamente."
    )

    return redirect("panel_entradas")

def registro(request):
    if request.user.is_authenticated:
        return redirect("index_peliculas")

    if request.method == "POST":
        form = RegistroUsuarioForm(request.POST)

        if form.is_valid():
            usuario = form.save()
            login(request, usuario)
            return redirect("index_peliculas")
    else:
        form = RegistroUsuarioForm()

    return render(request, "registro.html", {"form": form})


def iniciar_sesion(request):
    if request.user.is_authenticated:
        return redirect("index_peliculas")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        usuario = authenticate(
            request,
            username=username,
            password=password,
        )

        if usuario is not None:
            login(request, usuario)
            return redirect("index_peliculas")

        messages.error(request, "Usuario o contraseña incorrectos.")

    return render(request, "login.html")


def cerrar_sesion(request):
    logout(request)
    return redirect("index_peliculas")


@login_required
def perfil(request):
    return render(request, "perfil.html")


@login_required
def editar_perfil(request):
    if request.method == "POST":
        form = EditarPerfilForm(request.POST, instance=request.user)

        if form.is_valid():
            form.save()
            return redirect("perfil")
    else:
        form = EditarPerfilForm(instance=request.user)

    return render(request, "editar_perfil.html", {"form": form})



@login_required
def socio(request):
    if request.method == "POST":
        if not request.user.socio:
            request.user.socio = True
            request.user.save(update_fields=["socio"])
            messages.success(request, "Te has hecho socio correctamente.")
        else:
            messages.info(request, "Ya eres socio de FICinema.")

        return redirect("perfil")

    return render(request, "socio.html")


@login_required
@require_POST
def baja_socio(request):
    if request.user.socio:
        request.user.socio = False
        request.user.save(update_fields=["socio"])
        messages.success(request, "Te has dado de baja como socio correctamente.")
    else:
        messages.info(request, "Actualmente no eres socio de FICinema.")

    return redirect("perfil")


@login_required
def bonos(request):
    bonos_usuario = request.user.bonos.filter(
        fechaCaducidad__gte=date.today(),
        usos_restantes__gt=0,
    ).order_by("fechaCaducidad", "codigo")

    return render(
        request,
        "bonos.html",
        {
            "tipos_bono": Bono.TIPOS_BONO,
            "bonos_usuario": bonos_usuario,
        },
    )


@login_required
def confirmar_bono(request, tipo):
    if not request.user.socio:
        messages.error(request, "Para comprar bonos debes ser socio de FICinema.")
        return redirect("socio")

    tipos_bono = dict(Bono.TIPOS_BONO)

    if tipo not in tipos_bono:
        messages.error(request, "El tipo de bono seleccionado no es válido.")
        return redirect("bonos")

    fecha_caducidad = date.today() + timedelta(days=365)

    return render(
        request,
        "confirmar_bono.html",
        {
            "tipo": tipo,
            "descripcion": tipos_bono[tipo],
            "fecha_caducidad": fecha_caducidad,
            "precio": PRECIOS_BONO.get(tipo, 0),
            "STRIPE_PUBLISHABLE_KEY": settings.STRIPE_PUBLISHABLE_KEY,
            "PAYMENT_SIMULATION_MODE": getattr(settings, "PAYMENT_SIMULATION_MODE", True),
        },
    )


@login_required
@require_POST
def comprar_bono(request, tipo):
    if not request.user.socio:
        messages.error(request, "Para comprar bonos debes ser socio de FICinema.")
        return redirect("socio")

    tipos_validos = [codigo for codigo, _descripcion in Bono.TIPOS_BONO]

    if tipo not in tipos_validos:
        messages.error(request, "El tipo de bono seleccionado no es válido.")
        return redirect("bonos")

    precio = PRECIOS_BONO.get(tipo, 0)
    titular_pago = normalizar_titular_pago(request.POST.get("titular", ""))
    titular_valido, error_titular = validar_titular_pago(titular_pago)

    if not titular_valido:
        messages.error(request, error_titular)
        return redirect("confirmar_bono", tipo=tipo)

    stripe_token = request.POST.get("stripeToken", "").strip()
    modo_simulacion = getattr(settings, "PAYMENT_SIMULATION_MODE", True)

    if not modo_simulacion and not stripe_token:
        messages.error(request, "No se recibió el token de pago. Inténtalo de nuevo.")
        return redirect("confirmar_bono", tipo=tipo)

    resultado_api = _llamar_api_pago(
        usuario=request.user,
        total=precio,
        stripe_token=stripe_token,
        descripcion=f"Bono {tipo}",
        metadata={
            "usuario_id": request.user.id,
            "tipo_operacion": "bono",
            "bono": tipo,
        },
    )

    if not resultado_api["aprobado"]:
        messages.error(request, f"Pago rechazado: {resultado_api['mensaje']}")
        return redirect("confirmar_bono", tipo=tipo)

    fecha_caducidad = date.today() + timedelta(days=365)

    bono = Bono.objects.create(
        tipo=tipo,
        fechaCaducidad=fecha_caducidad,
        usuario=request.user,
    )

    if programar_envio_correo_bono(request.user, bono, precio, referencia=resultado_api["referencia"]):
        messages.info(request, mensaje_envio_correo_demo("bono"))

    messages.success(
        request,
        f"Bono {tipo} comprado correctamente. Referencia: {resultado_api['referencia']}.",
    )
    return redirect("bonos")


@login_required
def estadisticas(request):
    api_key = settings.TMDB_API_KEY
    url = f"https://api.themoviedb.org/3/movie/popular?api_key={api_key}&language=es-ES"
    headers = construir_headers_tmdb()

    error_api = None
    data = []

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json().get("results", [])
    except requests.RequestException:
        error_api = "No se pudieron cargar las tendencias de cartelera desde TMDB."
    except ValueError:
        error_api = "La respuesta de TMDB no tiene un formato válido."

    ids_cartelera = list(obtener_ids_cartelera_visible_cache())
    if not ids_cartelera:
        ids_cartelera = obtener_ids_peliculas_con_sesiones_futuras(limite=MAX_PELICULAS_CARTELERA)

    peliculas_cartelera = []
    for movie_id in ids_cartelera[:MAX_PELICULAS_CARTELERA]:
        try:
            pelicula_cartelera = preparar_pelicula_cartelera_desde_sesion(movie_id)
        except (requests.RequestException, ValueError, TypeError, KeyError):
            pelicula_cartelera = None

        if pelicula_cartelera:
            peliculas_cartelera.append(pelicula_cartelera)

    if peliculas_cartelera:
        data = peliculas_cartelera
    elif data:
        ids_futuras = set(obtener_ids_peliculas_con_sesiones_futuras(limite=MAX_PELICULAS_CARTELERA))
        if ids_futuras:
            data = [pelicula for pelicula in data if pelicula.get("id") in ids_futuras]

    df = pd.DataFrame(data)

    estadisticas_peliculas = {
        "total_peliculas": 0,
        "valoracion_media": 0,
        "mejor_valorada": "No disponible",
        "peor_valorada": "No disponible",
        "con_sinopsis": 0,
        "sin_sinopsis": 0,
        "con_poster": 0,
        "sin_poster": 0,
        "peliculas_por_anio": [],
        "peliculas_cartelera_visible": 0,
        "peliculas_con_sesiones_futuras": 0,
    }

    if not df.empty:
        if "title" not in df.columns:
            df["title"] = "Título no disponible"

        df["title"] = df["title"].fillna("Título no disponible")
        df["title"] = df["title"].replace("", "Título no disponible")

        if "vote_average" not in df.columns:
            df["vote_average"] = 0

        df["vote_average"] = pd.to_numeric(
            df["vote_average"],
            errors="coerce"
        ).fillna(0)

        if "overview" not in df.columns:
            df["overview"] = ""

        if "poster_path" not in df.columns:
            df["poster_path"] = ""

        if "release_date" not in df.columns:
            df["release_date"] = ""

        df["overview"] = df["overview"].fillna("")
        df["poster_path"] = df["poster_path"].fillna("")
        df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")

        total_peliculas = len(df)
        valoracion_media = (
            round(float(df["vote_average"].mean()), 2)
            if total_peliculas > 0
            else 0
        )

        mejor_pelicula = df.sort_values(by="vote_average", ascending=False).iloc[0]
        peor_pelicula = df.sort_values(by="vote_average", ascending=True).iloc[0]

        con_sinopsis = int(df["overview"].str.strip().ne("").sum())
        sin_sinopsis = int(total_peliculas - con_sinopsis)

        con_poster = int(df["poster_path"].str.strip().ne("").sum())
        sin_poster = int(total_peliculas - con_poster)

        df_fechas = df.dropna(subset=["release_date"]).copy()

        peliculas_por_anio = []

        if not df_fechas.empty:
            df_fechas["anio"] = df_fechas["release_date"].dt.year
            conteo_anios = df_fechas["anio"].value_counts().sort_index()

            peliculas_por_anio = [
                {
                    "anio": int(anio),
                    "cantidad": int(cantidad),
                }
                for anio, cantidad in conteo_anios.items()
            ]

        estadisticas_peliculas = {
            "total_peliculas": total_peliculas,
            "valoracion_media": valoracion_media,
            "mejor_valorada": mejor_pelicula["title"],
            "peor_valorada": peor_pelicula["title"],
            "con_sinopsis": con_sinopsis,
            "sin_sinopsis": sin_sinopsis,
            "con_poster": con_poster,
            "sin_poster": sin_poster,
            "peliculas_por_anio": peliculas_por_anio,
            "peliculas_cartelera_visible": contar_peliculas_cartelera_visible(),
            "peliculas_con_sesiones_futuras": contar_peliculas_con_sesiones_futuras(),
        }

    estadisticas_peliculas["peliculas_cartelera_visible"] = contar_peliculas_cartelera_visible()
    estadisticas_peliculas["peliculas_con_sesiones_futuras"] = contar_peliculas_con_sesiones_futuras()

    estadisticas_usuarios = None
    estadisticas_bonos = None
    estadisticas_resenas = None
    estadisticas_avanzadas = None
    validaciones_qr = None

    if request.user.is_staff:
        total_usuarios = Usuario.objects.count()
        usuarios_socios = Usuario.objects.filter(socio=True).count()
        usuarios_no_socios = total_usuarios - usuarios_socios

        estadisticas_usuarios = {
            "total_usuarios": total_usuarios,
            "usuarios_socios": usuarios_socios,
            "usuarios_no_socios": usuarios_no_socios,
        }

        total_bonos = Bono.objects.count()
        bonos_activos = Bono.objects.filter(
            fechaCaducidad__gte=date.today(),
            usos_restantes__gt=0,
        ).count()
        bonos_agotados = Bono.objects.filter(usos_restantes=0).count()
        bonos_caducados = Bono.objects.filter(fechaCaducidad__lt=date.today()).count()

        bonos_por_tipo = []

        for codigo, descripcion in Bono.TIPOS_BONO:
            cantidad = Bono.objects.filter(tipo=codigo).count()

            bonos_por_tipo.append(
                {
                    "codigo": codigo,
                    "descripcion": descripcion,
                    "cantidad": cantidad,
                }
            )

        estadisticas_bonos = {
            "total_bonos": total_bonos,
            "bonos_activos": bonos_activos,
            "bonos_agotados": bonos_agotados,
            "bonos_caducados": bonos_caducados,
            "bonos_por_tipo": bonos_por_tipo,
        }

        df_resenas = pd.DataFrame(
            list(
                Resena.objects.filter(visible=True).values(
                    "movie_id",
                    "titulo_pelicula",
                    "puntuacion",
                    "actualizada_en",
                )
            )
        )

        estadisticas_resenas = {
            "total_resenas": 0,
            "media_general": 0,
            "peliculas_resenadas": 0,
            "top_peliculas": [],
        }

        if not df_resenas.empty:
            df_resenas["puntuacion"] = pd.to_numeric(
                df_resenas["puntuacion"],
                errors="coerce",
            ).fillna(0)

            resumen_peliculas = (
                df_resenas
                .groupby(["movie_id", "titulo_pelicula"], as_index=False)
                .agg(
                    media=("puntuacion", "mean"),
                    total=("puntuacion", "count"),
                )
                .sort_values(["media", "total"], ascending=[False, False])
            )

            estadisticas_resenas = {
                "total_resenas": int(len(df_resenas)),
                "media_general": round(float(df_resenas["puntuacion"].mean()), 2),
                "peliculas_resenadas": int(df_resenas["movie_id"].nunique()),
                "top_peliculas": [
                    {
                        "movie_id": int(fila["movie_id"]),
                        "titulo_pelicula": fila["titulo_pelicula"],
                        "media": round(float(fila["media"]), 2),
                        "total": int(fila["total"]),
                    }
                    for _, fila in resumen_peliculas.head(8).iterrows()
                ],
            }

        estadisticas_avanzadas = obtener_estadisticas_avanzadas_staff()
        validaciones_qr = obtener_resumen_validaciones_qr()

    return render(
        request,
        "estadisticas.html",
        {
            "error_api": error_api,
            "estadisticas_peliculas": estadisticas_peliculas,
            "mostrar_panel_interno": request.user.is_staff,
            "estadisticas_usuarios": estadisticas_usuarios,
            "estadisticas_bonos": estadisticas_bonos,
            "estadisticas_resenas": estadisticas_resenas,
            "estadisticas_avanzadas": estadisticas_avanzadas,
            "validaciones_qr": validaciones_qr,
        },
    )



def obtener_resumen_validaciones_qr(limite=8):
    ahora = timezone.now()
    inicio_dia = timezone.make_aware(
        datetime.combine(timezone.localdate(), time.min),
        timezone.get_current_timezone(),
    )

    qs = ValidacionEntrada.objects.select_related(
        "entrada",
        "usuario_staff",
    )

    total = qs.count()
    hoy = qs.filter(creado_en__gte=inicio_dia).count()
    correctas = qs.filter(resultado=ValidacionEntrada.RESULTADO_VALIDA).count()
    bloqueadas = qs.exclude(resultado=ValidacionEntrada.RESULTADO_VALIDA).count()
    ultimas_24h = qs.filter(creado_en__gte=ahora - timedelta(hours=24)).count()

    por_resultado = [
        {
            "resultado": item["resultado"],
            "resultado_display": dict(ValidacionEntrada.RESULTADO_CHOICES).get(item["resultado"], item["resultado"]),
            "total": item["total"],
        }
        for item in qs.values("resultado").annotate(total=Count("id")).order_by("resultado")
    ]

    ultimas = []
    for validacion in qs.order_by("-creado_en", "-id")[:limite]:
        ultimas.append({
            "codigo": validacion.codigo_verificacion,
            "resultado": validacion.resultado,
            "resultado_display": validacion.get_resultado_display(),
            "detalle": validacion.detalle,
            "fecha": timezone.localtime(validacion.creado_en).strftime("%d/%m/%Y %H:%M"),
            "staff": validacion.usuario_staff.username if validacion.usuario_staff else "Sin staff",
            "entrada_codigo": validacion.entrada.codigo if validacion.entrada else "-",
        })

    return {
        "total": total,
        "hoy": hoy,
        "ultimas_24h": ultimas_24h,
        "correctas": correctas,
        "bloqueadas": bloqueadas,
        "tasa_correctas": round((correctas / total) * 100, 2) if total else 0,
        "por_resultado": por_resultado,
        "ultimas": ultimas,
    }

def obtener_etiquetas_resumen_estadisticas():
    """
    Etiquetas visibles para informes internos.

    Se evita llamar "vendidas" a todas las entradas válidas porque una
    entrada válida puede estar activa, usada o caducada, pero no cancelada.
    """
    return {
        "entradas_validas": "Entradas válidas",
        "entradas_activas": "Entradas activas",
        "entradas_usadas": "Entradas usadas",
        "entradas_caducadas": "Entradas caducadas",
        "entradas_canceladas": "Entradas canceladas",
        "sesiones_programadas": "Sesiones programadas",
        "sesiones_futuras": "Sesiones futuras",
        "sesiones_pasadas": "Sesiones pasadas",
        "salas_activas": "Salas activas",
        "ocupacion_global": "Ocupación global (%)",
        "capacidad_total_programada": "Plazas programadas",
        "capacidad_media_por_sesion": "Capacidad media por sesión",
        "media_entradas_por_sesion": "Media de entradas por sesión",
        "entradas_sin_bono": "Entradas pagadas individualmente",
        "entradas_con_bono": "Entradas consumidas con bono",
        "porcentaje_entradas_con_bono": "Entradas con bono (%)",
        "porcentaje_cancelacion": "Cancelaciones sobre emitidas (%)",
        "porcentaje_entradas_usadas": "Entradas validadas por QR (%)",
        "valor_entradas_emitidas": "Valor facial de entradas válidas (€)",
        "ingresos_estimados_entradas": "Ingresos por entradas directas (€)",
        "ingresos_estimados_bonos": "Ingresos por bonos (€)",
        "ingresos_estimados_totales": "Total cobrado simulado (€)",
        "actividad_economica_simulada": "Valor total de actividad simulada (€)",
    }


def escribir_fila_estadistica_csv(writer, seccion, indicador, valor, detalle=""):
    writer.writerow([seccion, indicador, valor, detalle])


@login_required
def exportar_estadisticas_csv(request):
    """
    Exporta las métricas internas del cine en formato CSV.

    Solo el staff puede descargar este informe. El CSV usa separador ';' y BOM
    UTF-8 para abrirse correctamente en Excel con textos en español.
    """
    if not request.user.is_staff:
        messages.error(
            request,
            "No tienes permisos para exportar estadísticas internas."
        )
        return redirect("index_peliculas")

    actualizar_entradas_caducadas_global()
    estadisticas_avanzadas = obtener_estadisticas_avanzadas_staff()

    fecha_exportacion = timezone.localtime().strftime("%Y-%m-%d_%H-%M")
    nombre_archivo = f"estadisticas_ficinema_{fecha_exportacion}.csv"

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    response.write("\ufeff")

    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Sección", "Indicador", "Valor", "Detalle"])

    escribir_fila_estadistica_csv(
        writer,
        "Metadatos",
        "Fecha de generación",
        timezone.localtime().strftime("%d/%m/%Y %H:%M"),
        f"Usuario: {request.user.username}",
    )
    escribir_fila_estadistica_csv(
        writer,
        "Metadatos",
        "Modo de pago",
        "Simulación",
        "No se realizan cargos reales. Los bonos se contabilizan al comprarse y sus usos no duplican ingresos.",
    )

    resumen = estadisticas_avanzadas["resumen"]
    etiquetas_resumen = obtener_etiquetas_resumen_estadisticas()

    for clave, etiqueta in etiquetas_resumen.items():
        escribir_fila_estadistica_csv(
            writer,
            "Resumen interno",
            etiqueta,
            resumen.get(clave, 0),
        )

    for pelicula in estadisticas_avanzadas["peliculas_mas_compradas"]:
        escribir_fila_estadistica_csv(
            writer,
            "Películas más compradas",
            pelicula.get("titulo_pelicula", "Sin título"),
            pelicula.get("total", 0),
            f"TMDB ID: {pelicula.get('movie_id', 'No disponible')}",
        )

    for sala in estadisticas_avanzadas["salas_mas_usadas"]:
        escribir_fila_estadistica_csv(
            writer,
            "Salas más usadas",
            sala.get("sala__nombre") or "Sala no asignada",
            sala.get("total", 0),
            "Entradas válidas asociadas a la sala",
        )

    for hora in estadisticas_avanzadas["horas_punta"]:
        escribir_fila_estadistica_csv(
            writer,
            "Horas con más ventas",
            hora.get("hora", "Hora no disponible"),
            hora.get("total", 0),
            "Entradas válidas vendidas en esa hora",
        )

    for usuario in estadisticas_avanzadas["usuarios_mas_activos"]:
        escribir_fila_estadistica_csv(
            writer,
            "Usuarios con más entradas",
            usuario.get("usuario__username", "Usuario no disponible"),
            usuario.get("total", 0),
            f"ID interno: {usuario.get('usuario__codigo', 'No disponible')}",
        )

    for bono in estadisticas_avanzadas["bonos_mas_usados"]:
        escribir_fila_estadistica_csv(
            writer,
            "Bonos más usados",
            bono.get("bono_usado__tipo", "Bono no disponible"),
            bono.get("total", 0),
            "Entradas válidas compradas usando este tipo de bono",
        )

    for sala in estadisticas_avanzadas["ocupacion_por_sala"]:
        escribir_fila_estadistica_csv(
            writer,
            "Ocupación por sala",
            sala.get("sala", "Sala no disponible"),
            f"{sala.get('ocupacion', 0)}%",
            (
                f"{sala.get('entradas', 0)} entradas / "
                f"{sala.get('capacidad', 0)} plazas programadas / "
                f"{sala.get('sesiones', 0)} sesiones"
            ),
        )

    df_resenas = pd.DataFrame(
        list(
            Resena.objects.filter(visible=True).values(
                "movie_id",
                "titulo_pelicula",
                "puntuacion",
            )
        )
    )

    if df_resenas.empty:
        escribir_fila_estadistica_csv(
            writer,
            "Reseñas",
            "Reseñas visibles",
            0,
            "Todavía no hay opiniones públicas",
        )
    else:
        df_resenas["puntuacion"] = pd.to_numeric(
            df_resenas["puntuacion"],
            errors="coerce",
        ).fillna(0)

        escribir_fila_estadistica_csv(
            writer,
            "Reseñas",
            "Valoración media interna",
            round(float(df_resenas["puntuacion"].mean()), 2),
            f"{len(df_resenas)} reseñas visibles",
        )

        resumen_resenas = (
            df_resenas
            .groupby(["movie_id", "titulo_pelicula"], as_index=False)
            .agg(media=("puntuacion", "mean"), total=("puntuacion", "count"))
            .sort_values(["media", "total"], ascending=[False, False])
        )

        for _, pelicula in resumen_resenas.iterrows():
            escribir_fila_estadistica_csv(
                writer,
                "Películas mejor valoradas por usuarios",
                pelicula["titulo_pelicula"],
                f"{round(float(pelicula['media']), 2)}/5",
                f"{int(pelicula['total'])} reseña(s) · TMDB ID: {int(pelicula['movie_id'])}",
            )

    proximas_24h = estadisticas_avanzadas.get("proximas_24h", {})
    for indicador, clave in [
        ("Sesiones próximas", "sesiones"),
        ("Entradas activas", "entradas_activas"),
        ("Plazas programadas", "plazas_programadas"),
        ("Plazas disponibles", "plazas_disponibles"),
        ("Ocupación prevista", "ocupacion_prevista"),
    ]:
        valor = proximas_24h.get(clave, 0)
        if clave == "ocupacion_prevista":
            valor = f"{valor}%"
        escribir_fila_estadistica_csv(
            writer,
            "Próximas 24 horas",
            indicador,
            valor,
            f"Primera sesión: {proximas_24h.get('primera_sesion', 'Sin datos')}",
        )

    for alerta in estadisticas_avanzadas.get("alertas_gestion", []):
        escribir_fila_estadistica_csv(
            writer,
            "Alertas de gestión",
            alerta.get("titulo", "Aviso"),
            alerta.get("valor", ""),
            f"{alerta.get('nivel', '')}: {alerta.get('descripcion', '')}",
        )

    validaciones_qr = obtener_resumen_validaciones_qr(limite=20)
    for indicador, valor in [
        ("Validaciones totales", validaciones_qr["total"]),
        ("Validaciones de hoy", validaciones_qr["hoy"]),
        ("Validaciones últimas 24 horas", validaciones_qr["ultimas_24h"]),
        ("Accesos correctos", validaciones_qr["correctas"]),
        ("Intentos bloqueados", validaciones_qr["bloqueadas"]),
        ("Tasa de accesos correctos", f"{validaciones_qr['tasa_correctas']}%"),
    ]:
        escribir_fila_estadistica_csv(writer, "Control QR", indicador, valor)

    for resultado in validaciones_qr["por_resultado"]:
        escribir_fila_estadistica_csv(
            writer,
            "Control QR por resultado",
            resultado["resultado_display"],
            resultado["total"],
        )

    for validacion in validaciones_qr["ultimas"]:
        escribir_fila_estadistica_csv(
            writer,
            "Últimas validaciones QR",
            validacion["codigo"],
            validacion["resultado_display"],
            f"{validacion['fecha']} · Staff: {validacion['staff']} · Entrada: {validacion['entrada_codigo']}",
        )

    for estado in estadisticas_avanzadas["ventas_por_estado"]:
        escribir_fila_estadistica_csv(
            writer,
            "Entradas por estado",
            estado.get("estado", "Sin estado"),
            estado.get("total", 0),
            "Conteo total por estado registrado",
        )

    for sesion in estadisticas_avanzadas["sesiones_con_mayor_ocupacion"]:
        escribir_fila_estadistica_csv(
            writer,
            "Sesiones con mayor ocupación",
            sesion.get("titulo_pelicula", "Sin título"),
            f"{sesion.get('ocupacion', 0)}%",
            (
                f"{sesion.get('entradas', 0)} entradas / "
                f"{sesion.get('capacidad', 0)} plazas · "
                f"{sesion.get('sala__nombre', 'Sala no disponible')} · "
                f"{sesion.get('inicio_formateado', 'Sin fecha')}"
            ),
        )

    for pelicula in estadisticas_avanzadas["peliculas_con_mayor_ocupacion"]:
        escribir_fila_estadistica_csv(
            writer,
            "Películas con mayor ocupación",
            pelicula.get("titulo_pelicula", "Sin título"),
            f"{pelicula.get('ocupacion', 0)}%",
            (
                f"{pelicula.get('entradas', 0)} entradas / "
                f"{pelicula.get('capacidad', 0)} plazas · "
                f"{pelicula.get('sesiones', 0)} sesiones"
            ),
        )

    for concepto in estadisticas_avanzadas["desglose_ingresos"]:
        escribir_fila_estadistica_csv(
            writer,
            "Desglose de ingresos simulados",
            concepto.get("concepto", "Concepto"),
            f"{concepto.get('ingresos', 0)}€",
            f"Cantidad asociada: {concepto.get('cantidad', 0)} · {concepto.get('detalle', '')}",
        )

    for pelicula in obtener_cartelera_visible_para_informes():
        escribir_fila_estadistica_csv(
            writer,
            "Cartelera visible",
            pelicula["titulo_pelicula"],
            pelicula["sesiones"],
            (
                f"{pelicula['entradas_validas']} entradas válidas · "
                f"Valoración usuarios: "
                f"{formatear_valoracion_usuarios_exportacion(pelicula)} · "
                f"TMDB ID: {pelicula['movie_id']}"
            ),
        )

    return response


def construir_tabla_pdf_estadisticas(datos, col_widths, estilos, colors, Table, TableStyle):
    from reportlab.platypus import Paragraph

    try:
        estilo_celda = estilos["FICinemaTableCell"]
    except KeyError:
        estilo_celda = estilos["Normal"]

    try:
        estilo_cabecera = estilos["FICinemaTableHeader"]
    except KeyError:
        estilo_cabecera = estilo_celda
    datos_pdf = []

    for indice_fila, fila in enumerate(datos):
        estilo = estilo_cabecera if indice_fila == 0 else estilo_celda
        datos_pdf.append([Paragraph(escape(str(celda)), estilo) for celda in fila])

    tabla = Table(datos_pdf, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d252a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fb")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return tabla


@login_required
def exportar_estadisticas_pdf(request):
    """
    Genera un informe PDF de estadísticas internas para el staff.

    Usa los mismos datos internos que el CSV y no llama a APIs externas. Sirve
    como resumen administrativo para defensa, revisión o archivo interno.
    """
    if not request.user.is_staff:
        messages.error(
            request,
            "No tienes permisos para descargar estadísticas internas en PDF."
        )
        return redirect("index_peliculas")

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        return HttpResponse(
            "No se puede generar el PDF porque falta la dependencia reportlab.",
            status=500,
        )

    actualizar_entradas_caducadas_global()
    estadisticas_avanzadas = obtener_estadisticas_avanzadas_staff()
    resumen = estadisticas_avanzadas["resumen"]

    pdf_buffer = BytesIO()
    fecha_exportacion = timezone.localtime()
    nombre_archivo = f"estadisticas_ficinema_{fecha_exportacion.strftime('%Y-%m-%d_%H-%M')}.pdf"

    documento = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Informe de estadísticas internas FICinema",
    )

    estilos = getSampleStyleSheet()
    estilos.add(
        ParagraphStyle(
            name="FICinemaTitle",
            parent=estilos["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=29,
            textColor=colors.HexColor("#0d252a"),
            alignment=1,
            spaceAfter=6,
        )
    )
    estilos.add(
        ParagraphStyle(
            name="FICinemaSubtitle",
            parent=estilos["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#475569"),
            alignment=1,
            spaceAfter=12,
        )
    )
    estilos.add(
        ParagraphStyle(
            name="FICinemaSection",
            parent=estilos["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0d252a"),
            spaceBefore=10,
            spaceAfter=7,
        )
    )
    estilos.add(
        ParagraphStyle(
            name="FICinemaSmall",
            parent=estilos["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569"),
        )
    )
    estilos.add(
        ParagraphStyle(
            name="FICinemaTableCell",
            parent=estilos["Normal"],
            fontSize=8.2,
            leading=10.5,
            textColor=colors.HexColor("#0f172a"),
        )
    )
    estilos.add(
        ParagraphStyle(
            name="FICinemaTableHeader",
            parent=estilos["FICinemaTableCell"],
            fontName="Helvetica-Bold",
            textColor=colors.white,
        )
    )

    contenido = []
    logo_path = os.path.join(settings.BASE_DIR, "static", "images", "FICinema.jpg")

    if os.path.exists(logo_path):
        contenido.append(Image(logo_path, width=20 * mm, height=20 * mm, hAlign="CENTER"))
        contenido.append(Spacer(1, 3 * mm))

    contenido.extend(
        [
            Paragraph("FICinema", estilos["FICinemaTitle"]),
            Paragraph("Informe de estadísticas internas", estilos["FICinemaSubtitle"]),
            Paragraph(
                f"Generado el {fecha_exportacion.strftime('%d/%m/%Y a las %H:%M')} por {request.user.username}.",
                estilos["FICinemaSmall"],
            ),
            Spacer(1, 6 * mm),
            Paragraph("Resumen general", estilos["FICinemaSection"]),
        ]
    )

    etiquetas_resumen = obtener_etiquetas_resumen_estadisticas()
    filas_resumen = [["Indicador", "Valor"]]

    for clave, etiqueta in etiquetas_resumen.items():
        valor = resumen.get(clave, 0)
        if clave == "ocupacion_global":
            valor = f"{valor}%"
        filas_resumen.append([etiqueta, str(valor)])

    contenido.append(
        construir_tabla_pdf_estadisticas(
            filas_resumen,
            [95 * mm, 45 * mm],
            estilos,
            colors,
            Table,
            TableStyle,
        )
    )

    contenido.append(Spacer(1, 4 * mm))
    contenido.append(
        Paragraph(
            "Nota: las entradas válidas incluyen entradas activas, usadas o caducadas. Las entradas canceladas se muestran aparte para no mezclar ventas reales con cancelaciones.",
            estilos["FICinemaSmall"],
        )
    )

    contenido.append(Paragraph("Películas más compradas", estilos["FICinemaSection"]))
    filas_peliculas = [["Película", "Entradas", "Detalle"]]
    for pelicula in estadisticas_avanzadas["peliculas_mas_compradas"]:
        filas_peliculas.append(
            [
                pelicula.get("titulo_pelicula", "Sin título"),
                str(pelicula.get("total", 0)),
                f"TMDB ID: {pelicula.get('movie_id', 'No disponible')}",
            ]
        )
    if len(filas_peliculas) == 1:
        filas_peliculas.append(["Sin datos", "0", "Todavía no hay entradas válidas"])
    contenido.append(construir_tabla_pdf_estadisticas(filas_peliculas, [75 * mm, 25 * mm, 55 * mm], estilos, colors, Table, TableStyle))

    contenido.append(Paragraph("Salas, horas y usuarios", estilos["FICinemaSection"]))

    filas_salas = [["Sala", "Entradas válidas"]]
    for sala in estadisticas_avanzadas["salas_mas_usadas"]:
        filas_salas.append([sala.get("sala__nombre") or "Sala no asignada", str(sala.get("total", 0))])
    if len(filas_salas) == 1:
        filas_salas.append(["Sin datos", "0"])

    filas_horas = [["Hora", "Entradas válidas"]]
    for hora in estadisticas_avanzadas["horas_punta"]:
        filas_horas.append([hora.get("hora", "Hora no disponible"), str(hora.get("total", 0))])
    if len(filas_horas) == 1:
        filas_horas.append(["Sin datos", "0"])

    filas_usuarios = [["Usuario", "Entradas", "ID interno"]]
    for usuario in estadisticas_avanzadas["usuarios_mas_activos"]:
        filas_usuarios.append(
            [
                usuario.get("usuario__username", "Usuario no disponible"),
                str(usuario.get("total", 0)),
                str(usuario.get("usuario__codigo", "No disponible")),
            ]
        )
    if len(filas_usuarios) == 1:
        filas_usuarios.append(["Sin datos", "0", "-"])

    contenido.append(construir_tabla_pdf_estadisticas(filas_salas, [75 * mm, 35 * mm], estilos, colors, Table, TableStyle))
    contenido.append(Spacer(1, 5 * mm))
    contenido.append(construir_tabla_pdf_estadisticas(filas_horas, [75 * mm, 35 * mm], estilos, colors, Table, TableStyle))
    contenido.append(Spacer(1, 5 * mm))
    contenido.append(construir_tabla_pdf_estadisticas(filas_usuarios, [75 * mm, 25 * mm, 35 * mm], estilos, colors, Table, TableStyle))

    contenido.append(Paragraph("Bonos y ocupación por sala", estilos["FICinemaSection"]))

    filas_bonos = [["Tipo de bono", "Usos en entradas válidas"]]
    for bono in estadisticas_avanzadas["bonos_mas_usados"]:
        filas_bonos.append([bono.get("bono_usado__tipo", "Bono no disponible"), str(bono.get("total", 0))])
    if len(filas_bonos) == 1:
        filas_bonos.append(["Sin datos", "0"])
    contenido.append(construir_tabla_pdf_estadisticas(filas_bonos, [75 * mm, 45 * mm], estilos, colors, Table, TableStyle))

    contenido.append(Spacer(1, 5 * mm))

    filas_ocupacion = [["Sala", "Ocupación", "Entradas", "Capacidad", "Sesiones"]]
    for sala in estadisticas_avanzadas["ocupacion_por_sala"]:
        filas_ocupacion.append(
            [
                sala.get("sala", "Sala no disponible"),
                f"{sala.get('ocupacion', 0)}%",
                str(sala.get("entradas", 0)),
                str(sala.get("capacidad", 0)),
                str(sala.get("sesiones", 0)),
            ]
        )
    if len(filas_ocupacion) == 1:
        filas_ocupacion.append(["Sin datos", "0%", "0", "0", "0"])
    contenido.append(construir_tabla_pdf_estadisticas(filas_ocupacion, [40 * mm, 28 * mm, 28 * mm, 31 * mm, 28 * mm], estilos, colors, Table, TableStyle))

    contenido.append(Paragraph("Rendimiento destacado", estilos["FICinemaSection"]))

    filas_rendimiento = [["Indicador", "Valor", "Detalle"]]
    filas_rendimiento.extend([
        [
            "Media de entradas por sesión",
            str(resumen.get("media_entradas_por_sesion", 0)),
            "Entradas válidas repartidas entre todas las sesiones programadas",
        ],
        [
            "Día con más ventas",
            str(resumen.get("dia_mas_ventas", {}).get("total", 0)),
            resumen.get("dia_mas_ventas", {}).get("dia", "Sin datos"),
        ],
        [
            "Entradas con bono",
            f"{resumen.get('porcentaje_entradas_con_bono', 0)}%",
            f"{resumen.get('entradas_con_bono', 0)} de {resumen.get('entradas_validas', 0)} entradas válidas",
        ],
        [
            "Ingresos simulados",
            f"{resumen.get('ingresos_estimados_totales', 0)}€",
            f"Entradas directas: {resumen.get('ingresos_estimados_entradas', 0)}€ · Bonos: {resumen.get('ingresos_estimados_bonos', 0)}€",
        ],
    ])
    contenido.append(construir_tabla_pdf_estadisticas(filas_rendimiento, [62 * mm, 34 * mm, 63 * mm], estilos, colors, Table, TableStyle))
    contenido.append(Spacer(1, 5 * mm))

    contenido.append(Paragraph("Operativa próxima y alertas", estilos["FICinemaSection"]))

    proximas_24h = estadisticas_avanzadas.get("proximas_24h", {})
    filas_proximas = [["Indicador", "Valor", "Detalle"]]
    filas_proximas.extend([
        ["Sesiones próximas", str(proximas_24h.get("sesiones", 0)), f"Primera sesión: {proximas_24h.get('primera_sesion', 'Sin datos')}"] ,
        ["Entradas activas", str(proximas_24h.get("entradas_activas", 0)), "Entradas activas asociadas a sesiones de las próximas 24 horas"],
        ["Plazas disponibles", str(proximas_24h.get("plazas_disponibles", 0)), f"Ocupación prevista: {proximas_24h.get('ocupacion_prevista', 0)}%"],
    ])
    contenido.append(construir_tabla_pdf_estadisticas(filas_proximas, [55 * mm, 32 * mm, 72 * mm], estilos, colors, Table, TableStyle))
    contenido.append(Spacer(1, 5 * mm))

    filas_alertas = [["Aviso", "Valor", "Detalle"]]
    for alerta in estadisticas_avanzadas.get("alertas_gestion", [])[:6]:
        filas_alertas.append([
            alerta.get("titulo", "Aviso"),
            alerta.get("valor", ""),
            f"{alerta.get('nivel', '')}: {alerta.get('descripcion', '')}",
        ])
    if len(filas_alertas) == 1:
        filas_alertas.append(["Sin alertas", "-", "No hay avisos de gestión relevantes en este momento."])
    contenido.append(construir_tabla_pdf_estadisticas(filas_alertas, [45 * mm, 30 * mm, 84 * mm], estilos, colors, Table, TableStyle))
    contenido.append(Spacer(1, 5 * mm))

    contenido.append(Paragraph("Control de acceso QR", estilos["FICinemaSection"]))
    validaciones_qr = obtener_resumen_validaciones_qr(limite=8)
    filas_qr = [["Indicador", "Valor", "Detalle"]]
    filas_qr.extend([
        ["Validaciones totales", str(validaciones_qr["total"]), "Intentos registrados en el control de acceso"],
        ["Validaciones de hoy", str(validaciones_qr["hoy"]), f"Últimas 24 horas: {validaciones_qr['ultimas_24h']}"],
        ["Accesos correctos", str(validaciones_qr["correctas"]), f"Tasa correcta: {validaciones_qr['tasa_correctas']}%"],
        ["Intentos bloqueados", str(validaciones_qr["bloqueadas"]), "Incluye entradas usadas, caducadas, canceladas o inexistentes"],
    ])
    contenido.append(construir_tabla_pdf_estadisticas(filas_qr, [55 * mm, 30 * mm, 75 * mm], estilos, colors, Table, TableStyle))
    contenido.append(Spacer(1, 5 * mm))

    filas_qr_recientes = [["Código", "Resultado", "Detalle"]]
    for validacion in validaciones_qr["ultimas"]:
        filas_qr_recientes.append([
            validacion["codigo"],
            validacion["resultado_display"],
            f"{validacion['fecha']} · {validacion['staff']} · Entrada {validacion['entrada_codigo']}",
        ])
    if len(filas_qr_recientes) == 1:
        filas_qr_recientes.append(["Sin datos", "-", "Aún no hay validaciones registradas"])
    contenido.append(construir_tabla_pdf_estadisticas(filas_qr_recientes, [45 * mm, 35 * mm, 80 * mm], estilos, colors, Table, TableStyle))
    contenido.append(Spacer(1, 5 * mm))

    filas_sesiones_ocupacion = [["Sesión", "Ocupación", "Detalle"]]
    for sesion in estadisticas_avanzadas["sesiones_con_mayor_ocupacion"]:
        filas_sesiones_ocupacion.append([
            sesion.get("titulo_pelicula", "Sin título"),
            f"{sesion.get('ocupacion', 0)}%",
            f"{sesion.get('entradas', 0)}/{sesion.get('capacidad', 0)} · {sesion.get('sala__nombre', 'Sala no disponible')} · {sesion.get('inicio_formateado', 'Sin fecha')}",
        ])
    if len(filas_sesiones_ocupacion) == 1:
        filas_sesiones_ocupacion.append(["Sin datos", "0%", "Todavía no hay sesiones con entradas válidas"])
    contenido.append(construir_tabla_pdf_estadisticas(filas_sesiones_ocupacion, [75 * mm, 27 * mm, 60 * mm], estilos, colors, Table, TableStyle))

    contenido.append(Paragraph("Reseñas y cartelera visible", estilos["FICinemaSection"]))

    filas_resenas = [["Película", "Media usuarios", "Reseñas"]]
    resenas_visibles = (
        Resena.objects.filter(visible=True)
        .values("movie_id", "titulo_pelicula")
        .annotate(media=Avg("puntuacion"), total=Count("id"))
        .order_by("-media", "-total", "titulo_pelicula")[:8]
    )

    for resena in resenas_visibles:
        filas_resenas.append(
            [
                resena.get("titulo_pelicula", "Sin título"),
                f"{round(float(resena.get('media') or 0), 2)}/5",
                str(resena.get("total", 0)),
            ]
        )

    if len(filas_resenas) == 1:
        filas_resenas.append(["Sin datos", "0/5", "0"])

    contenido.append(construir_tabla_pdf_estadisticas(filas_resenas, [82 * mm, 38 * mm, 25 * mm], estilos, colors, Table, TableStyle))
    contenido.append(Spacer(1, 5 * mm))

    filas_cartelera = [["Película", "Sesiones futuras", "Entradas", "Valoración usuarios"]]
    for pelicula in obtener_cartelera_visible_para_informes():
        filas_cartelera.append(
            [
                pelicula["titulo_pelicula"],
                str(pelicula["sesiones"]),
                str(pelicula["entradas_validas"]),
                formatear_valoracion_usuarios_exportacion(pelicula),
            ]
        )

    if len(filas_cartelera) == 1:
        filas_cartelera.append(["Sin datos", "0", "0", "0/5 (0)"])

    contenido.append(construir_tabla_pdf_estadisticas(filas_cartelera, [76 * mm, 32 * mm, 22 * mm, 31 * mm], estilos, colors, Table, TableStyle))

    contenido.append(Spacer(1, 6 * mm))
    contenido.append(
        Paragraph(
            "Informe generado automáticamente desde el panel interno de FICinema. Los datos proceden de la base de datos interna del sistema.",
            estilos["FICinemaSmall"],
        )
    )

    documento.build(contenido)
    pdf_buffer.seek(0)

    response = HttpResponse(pdf_buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    response["Cache-Control"] = "private, max-age=300"

    return response


# =========================
# PANEL INTERNO STAFF
# =========================

def actualizar_entradas_caducadas_global():

    cache_key = "actualizacion_entradas_caducadas"

    if cache.get(cache_key):
        return

    Entrada.objects.filter(
        estado=Entrada.ESTADO_ACTIVA,
        sesion__fin__lte=timezone.now(),
    ).update(
        estado=Entrada.ESTADO_CADUCADA
    )

    cache.set(
        cache_key,
        True,
        60,
    )

def calcular_ocupacion_sesion(sesion):

    if not sesion.sala:

        return {
            "capacidad": 0,
            "entradas_vendidas": 0,
            "ocupacion": 0,
        }

    cache_key = f"ocupacion_sesion_{sesion.id}"

    cacheado = cache.get(cache_key)

    if cacheado:
        return cacheado

    capacidad = (
        sesion.sala.filas
        * sesion.sala.columnas
    )

    entradas_vendidas = (
        Entrada.objects.filter(sesion=sesion)
        .exclude(estado=Entrada.ESTADO_CANCELADA)
        .count()
    )

    ocupacion = (
        round(
            (entradas_vendidas / capacidad) * 100,
            2,
        )
        if capacidad
        else 0
    )

    datos = {
        "capacidad": capacidad,
        "entradas_vendidas": entradas_vendidas,
        "ocupacion": ocupacion,
    }

    cache.set(
        cache_key,
        datos,
        60 * 5,
    )

    return datos


def enriquecer_sesiones_con_ocupacion(sesiones):
    sesiones_enriquecidas = []

    for sesion in sesiones:
        datos_ocupacion = calcular_ocupacion_sesion(sesion)
        sesion.capacidad = datos_ocupacion["capacidad"]
        sesion.entradas_vendidas = datos_ocupacion["entradas_vendidas"]
        sesion.ocupacion = datos_ocupacion["ocupacion"]
        sesiones_enriquecidas.append(sesion)

    return sesiones_enriquecidas


@login_required
def escanear_qr_staff(request):
    if not request.user.is_staff:
        messages.error(request, "No tienes permisos para escanear entradas.")
        return redirect("index_peliculas")

    codigo_manual = request.GET.get("codigo", "").strip()
    if codigo_manual:
        coincidencia = re.search(r"FICINEMA-\d+-\d+", codigo_manual, re.IGNORECASE)
        if coincidencia:
            return redirect("verificar_entrada", codigo_verificacion=coincidencia.group(0).upper())

        messages.error(request, "El código introducido no tiene formato FICINEMA-entrada-usuario.")

    return render(request, "escanear_qr.html")


@login_required
@require_POST
def regenerar_cartelera_staff(request):
    if not request.user.is_staff:
        messages.error(request, "No tienes permisos para regenerar la cartelera.")
        return redirect("index_peliculas")

    try:
        peliculas_base = obtener_peliculas_populares_tmdb(max_paginas=3)
        peliculas_preparadas = []
        ids_usados = set()

        for pelicula in peliculas_base:
            movie_id = pelicula.get("id")
            if not movie_id or movie_id in ids_usados:
                continue

            ids_usados.add(movie_id)

            try:
                detalle = obtener_detalle_tmdb(movie_id, exigir_datos_cartelera=True)
            except (requests.RequestException, ValueError, TypeError, KeyError):
                continue

            fecha_estreno = obtener_fecha_estreno(detalle.get("release_date"))
            hoy = date.today()

            if fecha_estreno and not (hoy - timedelta(days=180) <= fecha_estreno <= hoy + timedelta(days=90)):
                continue

            detalle["id"] = movie_id
            detalle["title"] = detalle.get("title") or pelicula.get("title") or "Título no disponible"
            detalle["runtime"] = detalle.get("runtime") or DURACION_POR_DEFECTO
            detalle["popularity"] = detalle.get("popularity") or pelicula.get("popularity") or 0
            detalle["vote_average"] = detalle.get("vote_average") or pelicula.get("vote_average") or 0
            detalle["fecha_estreno_obj"] = fecha_estreno
            detalle["demanda_estimada"] = calcular_demanda_pelicula(detalle)
            peliculas_preparadas.append(detalle)

            if len(peliculas_preparadas) >= MAX_PELICULAS_CARTELERA:
                break

        if not peliculas_preparadas:
            messages.error(request, "No se encontraron películas válidas para regenerar la cartelera.")
            return redirect("panel_interno")

        peliculas_preparadas = sorted(
            peliculas_preparadas,
            key=lambda item: item.get("demanda_estimada", 0),
            reverse=True,
        )[:MAX_PELICULAS_CARTELERA]

        cache.delete("cartelera_visible_ids_actual")
        cache.delete("contador_cartelera_visible_v1")
        generar_programacion_cartelera_visible(peliculas_preparadas)
        guardar_ids_cartelera_visible_cache(peliculas_preparadas)

    except requests.RequestException:
        logger.exception("Error de API al regenerar la cartelera")
        messages.error(request, "No se pudo regenerar la cartelera porque falló la conexión con TMDB.")
        return redirect("panel_interno")
    except Exception:
        logger.exception("Error inesperado al regenerar la cartelera")
        messages.error(request, "No se pudo regenerar la cartelera. Revisa los registros del servidor.")
        return redirect("panel_interno")

    messages.success(
        request,
        "Cartelera y sesiones futuras regeneradas correctamente sin borrar entradas vendidas.",
    )
    return redirect("panel_interno")


@login_required
def panel_resenas(request):
    if not request.user.is_staff:
        messages.error(request, "No tienes permisos para acceder a la moderación de reseñas.")
        return redirect("index_peliculas")

    estado = request.GET.get("estado", "todas")
    puntuacion = request.GET.get("puntuacion", "")
    busqueda = (request.GET.get("q") or "").strip()

    resenas_qs = Resena.objects.select_related("usuario").order_by("-actualizada_en")

    if estado == "visibles":
        resenas_qs = resenas_qs.filter(visible=True)
    elif estado == "ocultas":
        resenas_qs = resenas_qs.filter(visible=False)

    if puntuacion:
        try:
            valor_puntuacion = int(puntuacion)
        except ValueError:
            valor_puntuacion = None

        if valor_puntuacion in range(1, 6):
            resenas_qs = resenas_qs.filter(puntuacion=valor_puntuacion)

    if busqueda:
        resenas_qs = resenas_qs.filter(
            Q(titulo_pelicula__icontains=busqueda)
            | Q(usuario__username__icontains=busqueda)
            | Q(comentario__icontains=busqueda)
        )

    resenas = list(resenas_qs[:150])
    df_resenas = pd.DataFrame(
        list(
            Resena.objects.values(
                "movie_id",
                "titulo_pelicula",
                "puntuacion",
                "visible",
                "actualizada_en",
            )
        )
    )

    resumen = {
        "total": 0,
        "visibles": 0,
        "ocultas": 0,
        "media": 0,
        "peliculas": 0,
    }

    top_peliculas = []

    if not df_resenas.empty:
        df_resenas["puntuacion"] = pd.to_numeric(df_resenas["puntuacion"], errors="coerce").fillna(0)
        visibles = df_resenas[df_resenas["visible"] == True]

        resumen = {
            "total": int(len(df_resenas)),
            "visibles": int(df_resenas["visible"].sum()),
            "ocultas": int((~df_resenas["visible"]).sum()),
            "media": round(float(visibles["puntuacion"].mean()), 2) if not visibles.empty else 0,
            "peliculas": int(visibles["movie_id"].nunique()) if not visibles.empty else 0,
        }

        if not visibles.empty:
            agrupadas = (
                visibles.groupby(["movie_id", "titulo_pelicula"], as_index=False)
                .agg(media=("puntuacion", "mean"), total=("puntuacion", "count"))
                .sort_values(["media", "total"], ascending=[False, False])
                .head(5)
            )

            top_peliculas = [
                {
                    "movie_id": int(fila["movie_id"]),
                    "titulo_pelicula": fila["titulo_pelicula"],
                    "media": round(float(fila["media"]), 2),
                    "total": int(fila["total"]),
                }
                for _, fila in agrupadas.iterrows()
            ]

    return render(
        request,
        "panel_resenas.html",
        {
            "resenas": resenas,
            "resumen": resumen,
            "top_peliculas": top_peliculas,
            "estado": estado,
            "puntuacion": puntuacion,
            "busqueda": busqueda,
        },
    )


@login_required
@require_POST
def cambiar_visibilidad_resena(request, resena_id):
    if not request.user.is_staff:
        messages.error(request, "No tienes permisos para moderar reseñas.")
        return redirect("index_peliculas")

    resena = get_object_or_404(Resena, id=resena_id)
    accion = request.POST.get("accion")

    if accion == "ocultar":
        resena.visible = False
        resena.save(update_fields=["visible", "actualizada_en"])
        messages.success(request, "La reseña se ha ocultado correctamente.")
    elif accion == "mostrar":
        resena.visible = True
        resena.save(update_fields=["visible", "actualizada_en"])
        messages.success(request, "La reseña vuelve a estar visible.")
    else:
        messages.error(request, "La acción solicitada no es válida.")

    siguiente = request.POST.get("next") or reverse("panel_resenas")
    return redirect(siguiente)


@login_required
def panel_estado_sistema(request):
    if not request.user.is_staff:
        messages.error(request, "No tienes permisos para acceder al estado del sistema.")
        return redirect("index_peliculas")

    public_base_url = (getattr(settings, "PUBLIC_BASE_URL", "") or "").strip()
    email_override = (getattr(settings, "EMAIL_TEST_RECIPIENT_OVERRIDE", "") or "").strip()
    default_from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    email_provider = (getattr(settings, "EMAIL_PROVIDER", "") or "").strip() or "django"
    database_engine = settings.DATABASES.get("default", {}).get("ENGINE", "")

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        estado_bd = "OK"
        detalle_bd = "La conexión con la base de datos responde correctamente."
    except Exception as exc:
        logger.exception("Error comprobando la base de datos desde el panel de estado")
        estado_bd = "Error"
        detalle_bd = f"No se pudo comprobar la base de datos: {exc}"

    public_base_local = public_base_url.startswith("http://localhost") or public_base_url.startswith("http://127.0.0.1")

    integraciones = [
        {
            "nombre": "Base de datos",
            "estado": estado_bd,
            "detalle": detalle_bd,
            "ok": estado_bd == "OK",
        },
        {
            "nombre": "TMDB",
            "estado": "Configurado" if os.getenv("TMDB_ACCESS_TOKEN") or os.getenv("TMDB_API_KEY") else "No configurado",
            "detalle": "Se usa para cartelera, detalles, posters, fechas y popularidad.",
            "ok": bool(os.getenv("TMDB_ACCESS_TOKEN") or os.getenv("TMDB_API_KEY")),
        },
        {
            "nombre": "OMDB",
            "estado": "Configurado" if os.getenv("OMDB_API_KEY") else "No configurado",
            "detalle": "Se usa como fuente complementaria de información cinematográfica.",
            "ok": bool(os.getenv("OMDB_API_KEY")),
        },
        {
            "nombre": "Google Maps",
            "estado": "Configurado" if getattr(settings, "GOOGLE_MAPS_API_KEY", "") else "No configurado",
            "detalle": "Se usa para la página de ubicación del cine.",
            "ok": bool(getattr(settings, "GOOGLE_MAPS_API_KEY", "")),
        },
        {
            "nombre": "Correo Resend",
            "estado": "Modo demo" if email_override else ("Configurado" if default_from_email else "No configurado"),
            "detalle": "Con dominio gratuito se centraliza la prueba en EMAIL_TEST_RECIPIENT_OVERRIDE." if email_override else "Sin override, se intentaría enviar al email del usuario configurado.",
            "ok": bool(email_override or default_from_email),
        },
        {
            "nombre": "QR público",
            "estado": "Revisar en local" if public_base_local else ("Configurado" if public_base_url else "Dinámico"),
            "detalle": "En local/Docker con localhost el QR solo es fiable en el mismo equipo. Para móvil usa la IP del PC o Render.",
            "ok": bool(public_base_url) and not public_base_local,
        },
    ]

    context = {
        "integraciones": integraciones,
        "public_base_url": public_base_url or "No configurado; se calcula desde la petición",
        "public_base_local": public_base_local,
        "email_provider": email_provider,
        "email_override": email_override or "No configurado",
        "default_from_email": default_from_email or "No configurado",
        "database_engine": database_engine or "No detectado",
        "debug_activo": bool(getattr(settings, "DEBUG", False)),
        "payment_simulation": bool(getattr(settings, "PAYMENT_SIMULATION_MODE", True)),
        "render_detectado": bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID")),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }

    return render(request, "panel_estado_sistema.html", context)


@login_required
def panel_interno(request):
    if not request.user.is_staff:
        messages.error(request, "No tienes permisos para acceder al panel interno.")
        return redirect("index_peliculas")

    actualizar_entradas_caducadas_global()

    hoy = timezone.localdate()
    ahora = timezone.now()

    sesiones_destacadas = enriquecer_sesiones_con_ocupacion(
        SesionCine.objects.filter(inicio__gt=ahora)
        .select_related("sala")
        .order_by("inicio")[:6]
    )

    validaciones_qr = obtener_resumen_validaciones_qr(limite=6)
    sesiones_hoy = SesionCine.objects.filter(fecha=hoy).count()
    proximas_sesiones = SesionCine.objects.filter(inicio__gt=ahora).count()
    entradas_activas = Entrada.objects.filter(estado=Entrada.ESTADO_ACTIVA).count()
    resenas_visibles = Resena.objects.filter(visible=True).count()

    checks_defensa = [
        {
            "titulo": "Cartelera",
            "estado": "OK" if proximas_sesiones else "Revisar",
            "descripcion": (
                f"{proximas_sesiones} sesiones futuras disponibles."
                if proximas_sesiones
                else "No hay sesiones futuras: regenera la cartelera antes de la demo."
            ),
        },
        {
            "titulo": "Control QR",
            "estado": "OK" if validaciones_qr.get("total", 0) else "Pendiente",
            "descripcion": (
                f"{validaciones_qr.get('total', 0)} validaciones registradas."
                if validaciones_qr.get("total", 0)
                else "Haz una validación de prueba para enseñar el flujo completo."
            ),
        },
        {
            "titulo": "Entradas activas",
            "estado": "OK" if entradas_activas else "Demo",
            "descripcion": (
                f"{entradas_activas} entradas activas para probar PDF y QR."
                if entradas_activas
                else "Compra una entrada de prueba antes de la defensa."
            ),
        },
        {
            "titulo": "Reseñas",
            "estado": "OK" if resenas_visibles else "Opcional",
            "descripcion": (
                f"{resenas_visibles} reseñas visibles para estadísticas internas."
                if resenas_visibles
                else "Puedes añadir una reseña para reforzar recomendaciones y estadísticas."
            ),
        },
    ]

    context = {
        "sesiones_hoy": sesiones_hoy,
        "proximas_sesiones": proximas_sesiones,
        "entradas_hoy": Entrada.objects.filter(fechaCompra__date=hoy).count(),
        "entradas_activas": entradas_activas,
        "entradas_canceladas": Entrada.objects.filter(estado=Entrada.ESTADO_CANCELADA).count(),
        "entradas_caducadas": Entrada.objects.filter(estado=Entrada.ESTADO_CADUCADA).count(),
        "entradas_usadas": Entrada.objects.filter(estado=Entrada.ESTADO_USADA).count(),
        "usuarios_totales": Usuario.objects.count(),
        "usuarios_socios": Usuario.objects.filter(socio=True).count(),
        "resenas_totales": resenas_visibles,
        "valoracion_media_interna": round(Resena.objects.filter(visible=True).aggregate(media=Avg("puntuacion")).get("media") or 0, 1),
        "bonos_activos": Bono.objects.filter(fechaCaducidad__gte=hoy, usos_restantes__gt=0).count(),
        "bonos_agotados": Bono.objects.filter(usos_restantes=0).count(),
        "bonos_caducados": Bono.objects.filter(fechaCaducidad__lt=hoy).count(),
        "sesiones_destacadas": sesiones_destacadas,
        "validaciones_qr": validaciones_qr,
        "checks_defensa": checks_defensa,
    }

    return render(request, "panel_interno.html", context)


@login_required
def panel_sesiones(request):
    if not request.user.is_staff:
        messages.error(request, "No tienes permisos para acceder a la gestión de sesiones.")
        return redirect("index_peliculas")

    actualizar_entradas_caducadas_global()

    filtro = request.GET.get("filtro", "proximas")
    ahora = timezone.now()
    hoy = timezone.localdate()
    sesiones_query = SesionCine.objects.select_related("sala")

    if filtro == "hoy":
        sesiones_query = sesiones_query.filter(fecha=hoy)
    elif filtro == "pasadas":
        sesiones_query = sesiones_query.filter(fin__lte=ahora)
    else:
        sesiones_query = sesiones_query.filter(inicio__gt=ahora)
        filtro = "proximas"

    sesiones = enriquecer_sesiones_con_ocupacion(
        sesiones_query.order_by("inicio", "sala__id")[:80]
    )

    total_sesiones = len(sesiones)
    total_entradas_vendidas = sum(sesion.entradas_vendidas for sesion in sesiones)
    total_capacidad = sum(sesion.capacidad for sesion in sesiones)

    ocupacion_media = (
        round((total_entradas_vendidas / total_capacidad) * 100, 2)
        if total_capacidad
        else 0
    )

    return render(
        request,
        "panel_sesiones.html",
        {
            "sesiones": sesiones,
            "filtro": filtro,
            "total_sesiones": total_sesiones,
            "total_entradas_vendidas": total_entradas_vendidas,
            "total_capacidad": total_capacidad,
            "ocupacion_media": ocupacion_media,
        },
    )


@login_required
def panel_entradas(request):
    if not request.user.is_staff:
        messages.error(request, "No tienes permisos para acceder a la gestión de entradas.")
        return redirect("index_peliculas")

    actualizar_entradas_caducadas_global()

    estado = request.GET.get("estado", "todas")
    entradas = Entrada.objects.select_related("usuario", "sala", "sesion", "bono_usado")
    estados_validos = [codigo for codigo, _texto in Entrada.ESTADO_CHOICES]

    if estado in estados_validos:
        entradas = entradas.filter(estado=estado)
    else:
        estado = "todas"

    entradas = entradas.order_by("-fechaCompra")[:120]

    return render(
        request,
        "panel_entradas.html",
        {"entradas": entradas, "estado": estado, "estados": Entrada.ESTADO_CHOICES},
    )


@login_required
def panel_bonos(request):
    if not request.user.is_staff:
        messages.error(request, "No tienes permisos para acceder a la gestión de bonos.")
        return redirect("index_peliculas")

    hoy = timezone.localdate()
    filtro = request.GET.get("filtro", "activos")
    bonos = Bono.objects.select_related("usuario")

    if filtro == "agotados":
        bonos = bonos.filter(usos_restantes=0)
    elif filtro == "caducados":
        bonos = bonos.filter(fechaCaducidad__lt=hoy)
    elif filtro == "todos":
        bonos = bonos.all()
    else:
        bonos = bonos.filter(fechaCaducidad__gte=hoy, usos_restantes__gt=0)
        filtro = "activos"

    bonos = bonos.order_by("fechaCaducidad", "codigo")[:120]

    return render(request, "panel_bonos.html", {"bonos": bonos, "filtro": filtro})


@login_required
def panel_usuarios(request):
    if not request.user.is_staff:
        messages.error(request, "No tienes permisos para acceder a la gestión de usuarios.")
        return redirect("index_peliculas")

    filtro = request.GET.get("filtro", "todos")
    usuarios = Usuario.objects.annotate(
        total_entradas=Count("entradas", distinct=True),
        total_bonos=Count("bonos", distinct=True),
    )

    if filtro == "socios":
        usuarios = usuarios.filter(socio=True)
    elif filtro == "staff":
        usuarios = usuarios.filter(is_staff=True)
    elif filtro == "clientes":
        usuarios = usuarios.filter(is_staff=False)
    else:
        filtro = "todos"

    usuarios = usuarios.order_by("username")[:120]

    return render(request, "panel_usuarios.html", {"usuarios": usuarios, "filtro": filtro})


@require_GET
def validar_registro(request):
    campo = request.GET.get("campo", "").strip()
    valor = request.GET.get("valor", "").strip()

    if campo not in ["username", "email"]:
        return JsonResponse(
            {
                "valido": False,
                "mensaje": "Campo no válido.",
            },
            status=400,
        )

    if not valor:
        return JsonResponse(
            {
                "valido": False,
                "mensaje": "Este campo es obligatorio.",
            }
        )

    if campo == "username":
        patron_usuario = r"^[\w.@+-]+$"

        if len(valor) > 150:
            return JsonResponse(
                {
                    "valido": False,
                    "mensaje": "El nombre de usuario no puede superar 150 caracteres.",
                }
            )

        if not re.match(patron_usuario, valor):
            return JsonResponse(
                {
                    "valido": False,
                    "mensaje": "Solo se permiten letras, números y los caracteres @/./+/-/_.",
                }
            )

        if Usuario.objects.filter(username__iexact=valor).exists():
            return JsonResponse(
                {
                    "valido": False,
                    "mensaje": "Ya existe un usuario con este nombre.",
                }
            )

        return JsonResponse(
            {
                "valido": True,
                "mensaje": "Nombre de usuario disponible.",
            }
        )

    if campo == "email":
        patron_email = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"

        if not re.match(patron_email, valor):
            return JsonResponse(
                {
                    "valido": False,
                    "mensaje": "Introduce una dirección de correo electrónico válida.",
                }
            )

        if Usuario.objects.filter(email__iexact=valor).exists():
            return JsonResponse(
                {
                    "valido": False,
                    "mensaje": "Ya existe un usuario con este correo electrónico.",
                }
            )

        return JsonResponse(
            {
                "valido": True,
                "mensaje": "Correo electrónico disponible.",
            }
        )

    return JsonResponse(
        {
            "valido": False,
            "mensaje": "No se pudo validar el campo.",
        },
        status=400,
    )

@login_required
@require_POST
def pago_entrada(request):
    if request.user.is_staff:
        messages.error(request, "Las cuentas staff no pueden comprar entradas.")
        return redirect("panel_interno")

    sesion_id = request.POST.get("sesion_id")
    asientos = obtener_lista_asientos_post(request)
    codigo_bono = request.POST.get("codigo_bono", "").strip()

    if codigo_bono:
        return comprar_entrada(request)

    if not sesion_id or not asientos:
        messages.error(request, "Faltan datos para proceder al pago.")
        return redirect("index_peliculas")

    sesion = get_object_or_404(
        SesionCine.objects.select_related("sala"),
        id=sesion_id,
    )

    ahora = timezone.now()

    if sesion.fin and sesion.fin <= ahora:
        messages.error(request, "No puedes comprar entradas para una sesión finalizada o pasada.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    if sesion.inicio and sesion.inicio <= ahora:
        messages.error(request, "No puedes comprar entradas para una sesión ya iniciada.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    error_asientos = validar_asientos_para_sesion(sesion, asientos)

    if error_asientos:
        messages.error(request, error_asientos)
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    request.session["pago_pendiente"] = signing.dumps(
        {
            "sesion_id": sesion_id,
            "asientos": asientos,
            "user_id": request.user.id,
        }
    )

    cantidad = len(asientos)
    total = round(PRECIO_ENTRADA * cantidad, 2)

    return render(
        request,
        "pago_entrada.html",
        {
            "sesion": sesion,
            "asientos": asientos,
            "asientos_texto": ", ".join(asientos),
            "cantidad_entradas": cantidad,
            "precio_unitario": PRECIO_ENTRADA,
            "total": total,
            "STRIPE_PUBLISHABLE_KEY": settings.STRIPE_PUBLISHABLE_KEY,
            "PAYMENT_SIMULATION_MODE": getattr(settings, "PAYMENT_SIMULATION_MODE", True),
        },
    )


@login_required
@require_POST
def procesar_pago(request):
    if request.user.is_staff:
        messages.error(request, "Las cuentas staff no pueden comprar entradas.")
        return redirect("panel_interno")

    pago_pendiente_firmado = request.session.get("pago_pendiente")

    if not pago_pendiente_firmado:
        messages.error(request, "La sesión de pago ha expirado. Vuelve a seleccionar los asientos.")
        return redirect("index_peliculas")

    try:
        datos_pago = signing.loads(pago_pendiente_firmado)
    except signing.BadSignature:
        request.session.pop("pago_pendiente", None)
        messages.error(request, "Los datos de pago no son válidos. Inténtalo de nuevo.")
        return redirect("index_peliculas")

    if datos_pago.get("user_id") != request.user.id:
        request.session.pop("pago_pendiente", None)
        messages.error(request, "No tienes permiso para completar este pago.")
        return redirect("index_peliculas")

    sesion_id = datos_pago["sesion_id"]
    asientos = datos_pago["asientos"]
    cantidad = len(asientos)

    sesion = get_object_or_404(
        SesionCine.objects.select_related("sala"),
        id=sesion_id,
    )

    ahora = timezone.now()

    if sesion.fin and sesion.fin <= ahora:
        request.session.pop("pago_pendiente", None)
        messages.error(request, "La sesión ya ha finalizado mientras procesabas el pago. Vuelve a elegir una sesión disponible.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    if sesion.inicio and sesion.inicio <= ahora:
        request.session.pop("pago_pendiente", None)
        messages.error(request, "La sesión ya ha comenzado mientras procesabas el pago.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    error_asientos = validar_asientos_para_sesion(sesion, asientos)

    if error_asientos:
        request.session.pop("pago_pendiente", None)
        messages.error(request, error_asientos)
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    titular_pago = normalizar_titular_pago(request.POST.get("titular", ""))
    titular_valido, error_titular = validar_titular_pago(titular_pago)

    if not titular_valido:
        messages.error(request, error_titular)
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    stripe_token = request.POST.get("stripeToken", "").strip()
    modo_simulacion = getattr(settings, "PAYMENT_SIMULATION_MODE", True)

    if not modo_simulacion and not stripe_token:
        messages.error(request, "No se recibió el token de pago. Inténtalo de nuevo.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    total = round(PRECIO_ENTRADA * cantidad, 2)

    resultado_api = _llamar_api_pago(
        usuario=request.user,
        total=total,
        stripe_token=stripe_token,
        descripcion=f"{cantidad} entrada(s) - {sesion.titulo_pelicula}",
        metadata={
            "usuario_id": request.user.id,
            "sesion_id": sesion.id,
            "tipo_operacion": "entrada",
            "cantidad": cantidad,
        },
    )

    if not resultado_api["aprobado"]:
        messages.error(request, f"Pago rechazado: {resultado_api['mensaje']}")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    try:
        with transaction.atomic():
            entradas_creadas = crear_entradas_con_bloqueo(
                usuario=request.user,
                sesion=sesion,
                asientos=asientos,
            )

        cache.delete(f"ocupacion_sesion_{sesion.id}")
        cache.delete(f"entradas_recientes_{sesion.movie_id}")

    except ValidationError as error:
        request.session.pop("pago_pendiente", None)
        messages.error(request, error.messages[0] if hasattr(error, "messages") else str(error))
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    except IntegrityError:
        request.session.pop("pago_pendiente", None)
        messages.error(request, "Alguno de los asientos se ocupó justo antes de completarse el pago.")
        return redirect("detalle_pelicula", movie_id=sesion.movie_id)

    request.session.pop("pago_pendiente", None)

    if programar_envio_correo_entradas(
        request.user,
        entradas_creadas,
        referencia=resultado_api["referencia"],
    ):
        messages.info(request, mensaje_envio_correo_demo("entradas"))

    messages.success(
        request,
        f"Pago completado. Se han generado {cantidad} entrada(s). Referencia: {resultado_api['referencia']}.",
    )
    return redirect("mis_entradas")



def _validar_datos_tarjeta(titular, numero, mes, anio, cvv):
    """Devuelve lista de errores de validación del formulario de tarjeta."""
    errores = []

    if not titular or len(titular) < 3:
        errores.append("El nombre del titular debe tener al menos 3 caracteres.")

    numero_limpio = re.sub(r"\D", "", numero)
    if len(numero_limpio) not in (15, 16):
        errores.append("El número de tarjeta debe tener 15 o 16 dígitos.")

    try:
        mes_int = int(mes)
        if not (1 <= mes_int <= 12):
            raise ValueError
    except (TypeError, ValueError):
        errores.append("El mes de caducidad no es válido.")
        mes_int = None

    try:
        anio_int = int(anio)
        anio_actual = date.today().year % 100  
        if anio_int < anio_actual:
            errores.append("La tarjeta está caducada.")
    except (TypeError, ValueError):
        errores.append("El año de caducidad no es válido.")
        anio_int = None

    if mes_int and anio_int:
        hoy = date.today()
        if anio_int == hoy.year % 100 and mes_int < hoy.month:
            errores.append("La tarjeta está caducada.")

    cvv_limpio = re.sub(r"\D", "", cvv)
    if len(cvv_limpio) not in (3, 4):
        errores.append("El CVV debe tener 3 o 4 dígitos.")

    return errores


def _llamar_api_pago(usuario, total, stripe_token, descripcion, metadata=None):
    if getattr(settings, "PAYMENT_SIMULATION_MODE", True):
        return {
            "aprobado": True,
            "mensaje": "Pago simulado autorizado.",
            "referencia": f"SIM-{uuid.uuid4().hex[:12].upper()}",
        }

    if not settings.STRIPE_SECRET_KEY:
        return {
            "aprobado": False,
            "mensaje": "La pasarela de pago no está configurada.",
            "referencia": None,
        }

    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        importe_centimos = int(round(total * 100))

        charge = stripe.Charge.create(
            amount=importe_centimos,
            currency="eur",
            source=stripe_token,
            description=descripcion,
            metadata=metadata or {"usuario_id": usuario.id},
        )

        return {
            "aprobado": True,
            "mensaje": "Pago autorizado.",
            "referencia": charge.id,
        }

    except stripe.error.CardError as e:
        return {
            "aprobado": False,
            "mensaje": e.user_message or "La tarjeta ha sido rechazada.",
            "referencia": None,
        }
    except stripe.error.StripeError:
        return {
            "aprobado": False,
            "mensaje": "Error al procesar el pago. Inténtalo de nuevo.",
            "referencia": None,
        }

