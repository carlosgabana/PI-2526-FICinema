from datetime import date, time, timedelta
from unittest.mock import Mock, patch
from urllib import response

import requests
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Usuario, Bono, Entrada, Favorito, Resena, Sala, SesionCine
from . import views


class UsuarioModelTest(TestCase):

    def test_usuario_asigna_codigo_automaticamente(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="test12345"
        )

        self.assertEqual(usuario.codigo, 1)
        self.assertFalse(usuario.socio)

    def test_varios_usuarios_tienen_codigos_distintos(self):
        usuario1 = Usuario.objects.create_user(
            username="angel",
            password="test12345"
        )

        usuario2 = Usuario.objects.create_user(
            username="lucas",
            password="test12345"
        )

        self.assertNotEqual(usuario1.codigo, usuario2.codigo)
        self.assertEqual(usuario1.codigo, 1)
        self.assertEqual(usuario2.codigo, 2)

    def test_usuario_genero_por_defecto(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="test12345"
        )

        self.assertEqual(usuario.genero, "N")
        self.assertEqual(usuario.get_genero_display(), "Prefiero no decirlo")

    def test_usuario_puede_guardar_genero(self):
        usuario = Usuario.objects.create_user(
            username="lucas",
            password="test12345",
            genero="M"
        )

        self.assertEqual(usuario.genero, "M")
        self.assertEqual(usuario.get_genero_display(), "Masculino")


class BonoModelTest(TestCase):

    def test_bono_asigna_codigo_automaticamente(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="test12345"
        )

        bono = Bono.objects.create(
            tipo="5 EN 3",
            fechaCaducidad=date(2026, 12, 31),
            usuario=usuario
        )

        self.assertEqual(bono.codigo, 1)
        self.assertEqual(bono.usuario, usuario)

    def test_varios_bonos_tienen_codigos_distintos(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="test12345"
        )

        bono1 = Bono.objects.create(
            tipo="5 EN 3",
            fechaCaducidad=date(2026, 12, 31),
            usuario=usuario
        )

        bono2 = Bono.objects.create(
            tipo="10 EN 5",
            fechaCaducidad=date(2026, 12, 31),
            usuario=usuario
        )

        self.assertNotEqual(bono1.codigo, bono2.codigo)
        self.assertEqual(bono1.codigo, 1)
        self.assertEqual(bono2.codigo, 2)


class PeliculasViewTest(TestCase):

    def setUp(self):
        cache.clear()

    @patch("FICinema.views.requests.get")
    def test_index_peliculas_muestra_peliculas_api(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 1,
                    "title": "Pelicula Test",
                    "release_date": "2024-01-01",
                    "vote_average": 8.5,
                    "poster_path": "/poster.jpg",
                    "overview": "Sinopsis de prueba"
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(reverse("index_peliculas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PELICULA TEST")
        self.assertContains(response, "Comprar entradas")

    @patch("FICinema.views.requests.get")
    def test_index_peliculas_ordena_por_valoracion(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 1,
                    "title": "Pelicula Baja",
                    "release_date": "2024-01-01",
                    "vote_average": 5.0,
                    "poster_path": "/poster1.jpg",
                    "overview": "Sinopsis baja"
                },
                {
                    "id": 2,
                    "title": "Pelicula Alta",
                    "release_date": "2024-01-02",
                    "vote_average": 9.0,
                    "poster_path": "/poster2.jpg",
                    "overview": "Sinopsis alta"
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(
            reverse("index_peliculas"),
            {"ordenar_por": "Valoración"}
        )

        self.assertEqual(response.status_code, 200)
        peliculas = response.context["peliculas"]

        self.assertEqual(peliculas[0]["title"], "Pelicula Alta")
        self.assertEqual(peliculas[1]["title"], "Pelicula Baja")

    @patch("FICinema.views.requests.get")
    def test_index_peliculas_ordena_por_titulo(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 1,
                    "title": "Zeta",
                    "release_date": "2024-01-01",
                    "vote_average": 7.0,
                    "poster_path": "/poster1.jpg",
                    "overview": "Sinopsis zeta"
                },
                {
                    "id": 2,
                    "title": "Alfa",
                    "release_date": "2024-01-02",
                    "vote_average": 8.0,
                    "poster_path": "/poster2.jpg",
                    "overview": "Sinopsis alfa"
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(
            reverse("index_peliculas"),
            {"ordenar_por": "Título"}
        )

        self.assertEqual(response.status_code, 200)
        peliculas = response.context["peliculas"]

        self.assertEqual(peliculas[0]["title"], "Alfa")
        self.assertEqual(peliculas[1]["title"], "Zeta")

    @patch("FICinema.views.requests.get")
    def test_index_peliculas_ordena_por_fecha_lanzamiento(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 1,
                    "title": "Antigua",
                    "release_date": "2024-01-01",
                    "vote_average": 7.0,
                    "poster_path": "/poster1.jpg",
                    "overview": "Sinopsis antigua"
                },
                {
                    "id": 2,
                    "title": "Reciente",
                    "release_date": "2025-01-01",
                    "vote_average": 8.0,
                    "poster_path": "/poster2.jpg",
                    "overview": "Sinopsis reciente"
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(
            reverse("index_peliculas"),
            {"ordenar_por": "Fecha de Lanzamiento"}
        )

        self.assertEqual(response.status_code, 200)
        peliculas = response.context["peliculas"]

        self.assertEqual(peliculas[0]["title"], "Reciente")
        self.assertEqual(peliculas[1]["title"], "Antigua")

    @patch("FICinema.views.requests.get")
    def test_index_peliculas_gestiona_error_api(self, mock_get):
        mock_get.side_effect = requests.RequestException("Error de API")

        response = self.client.get(reverse("index_peliculas"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["peliculas"], [])
        self.assertContains(response, "No hay películas disponibles en este momento.")

    @patch("FICinema.views.requests.get")
    def test_index_peliculas_gestiona_json_invalido(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("JSON inválido")
        mock_get.return_value = mock_response

        response = self.client.get(reverse("index_peliculas"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["peliculas"], [])

    @patch("FICinema.views.requests.get")
    def test_index_peliculas_ignora_fecha_invalida(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 1,
                    "title": "Pelicula Sin Fecha",
                    "release_date": "",
                    "vote_average": 7.0,
                    "poster_path": "/poster.jpg",
                    "overview": "Sinopsis"
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(reverse("index_peliculas"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["peliculas"], [])

    @patch("FICinema.views.requests.get")
    def test_index_peliculas_rellena_campos_vacios(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 1,
                    "title": "",
                    "release_date": "2024-01-01",
                    "vote_average": None,
                    "poster_path": None,
                    "overview": ""
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(reverse("index_peliculas"))

        self.assertEqual(response.status_code, 200)

        pelicula = response.context["peliculas"][0]

        self.assertEqual(pelicula["title"], "Título no disponible")
        self.assertEqual(pelicula["overview"], "Sin sinopsis disponible.")
        self.assertEqual(pelicula["vote_average"], 0)
        self.assertEqual(pelicula["poster_url"], "")

    @patch("FICinema.views.requests.get")
    def test_index_peliculas_navbar_sin_sesion(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(reverse("index_peliculas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Iniciar sesión")
        self.assertContains(response, "Registrarse")
        self.assertNotContains(response, "Cerrar sesión")

    @patch("FICinema.views.requests.get")
    def test_index_peliculas_navbar_con_sesion(self, mock_get):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
        )
        self.client.force_login(usuario)

        mock_response = Mock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(reverse("index_peliculas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "angel")
        self.assertContains(response, "Cerrar sesión")
        self.assertNotContains(response, "Registrarse")

    @patch("FICinema.views.requests.get")
    def test_detalle_pelicula_muestra_informacion_api(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 1,
            "title": "Pelicula Detalle",
            "release_date": "2026-04-17",
            "vote_average": 7.5,
            "poster_path": "/poster.jpg",
            "overview": "Sinopsis de detalle",
            "videos": {
                "results": [
                    {
                        "site": "YouTube",
                        "type": "Trailer",
                        "key": "abc123"
                    }
                ]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(reverse("detalle_pelicula", args=[1]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pelicula Detalle")
        self.assertContains(response, "abc123")
        self.assertContains(response, "Ver tráiler oficial")
        self.assertIn("dias_disponibles", response.context)
        self.assertEqual(len(response.context["dias_disponibles"]), 7)

    @patch("FICinema.views.requests.get")
    def test_detalle_pelicula_sin_trailer(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 1,
            "title": "Pelicula Sin Trailer",
            "release_date": "2026-04-17",
            "vote_average": 6.5,
            "poster_path": "/poster.jpg",
            "overview": "Sinopsis sin trailer",
            "videos": {
                "results": []
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(reverse("detalle_pelicula", args=[1]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pelicula Sin Trailer")
        self.assertContains(response, "Sin vídeo disponible")
        self.assertIsNone(response.context["video_key"])

    @patch("FICinema.views.requests.get")
    def test_detalle_pelicula_con_video_no_youtube_no_lo_usa(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 1,
            "title": "Pelicula Video Externo",
            "release_date": "2026-04-17",
            "vote_average": 6.5,
            "poster_path": "/poster.jpg",
            "overview": "Sinopsis",
            "videos": {
                "results": [
                    {
                        "site": "Vimeo",
                        "type": "Trailer",
                        "key": "vimeo123"
                    }
                ]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(reverse("detalle_pelicula", args=[1]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sin vídeo disponible")
        self.assertIsNone(response.context["video_key"])

    @patch("FICinema.views.requests.get")
    def test_detalle_pelicula_con_video_youtube_no_trailer_no_lo_usa(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 1,
            "title": "Pelicula Teaser",
            "release_date": "2026-04-17",
            "vote_average": 6.5,
            "poster_path": "/poster.jpg",
            "overview": "Sinopsis",
            "videos": {
                "results": [
                    {
                        "site": "YouTube",
                        "type": "Teaser",
                        "key": "teaser123"
                    }
                ]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(reverse("detalle_pelicula", args=[1]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sin vídeo disponible")
        self.assertIsNone(response.context["video_key"])

    @patch("FICinema.views.requests.get")
    def test_detalle_pelicula_error_api(self, mock_get):
        mock_get.side_effect = requests.RequestException("Error de API")

        response = self.client.get(reverse("detalle_pelicula", args=[999999]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No se pudo cargar la información de la película.")

    @patch("FICinema.views.requests.get")
    def test_detalle_pelicula_respuesta_json_invalida(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("JSON inválido")
        mock_get.return_value = mock_response

        response = self.client.get(reverse("detalle_pelicula", args=[1]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La respuesta de la API no tiene un formato válido.")

    @patch("FICinema.views.requests.get")
    def test_detalle_pelicula_rellena_campos_vacios(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 1,
            "title": "",
            "release_date": "",
            "vote_average": None,
            "poster_path": None,
            "overview": "",
            "videos": {
                "results": []
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(reverse("detalle_pelicula", args=[1]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Título no disponible")
        self.assertContains(response, "Sin sinopsis disponible.")
        self.assertContains(response, "Sin imagen")
        self.assertContains(response, "Sin vídeo disponible")
        self.assertEqual(response.context["pelicula"]["vote_average"], 0)


class AutenticacionViewTest(TestCase):

    def test_pagina_registro_carga_correctamente(self):
        response = self.client.get(reverse("registro"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crear cuenta")
        self.assertContains(response, "Iniciar sesión")

    def test_pagina_login_carga_correctamente(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Iniciar sesión")
        self.assertContains(response, "Regístrate")

    def test_perfil_redirige_si_no_esta_logueado(self):
        response = self.client.get(reverse("perfil"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_registro_crea_usuario_e_inicia_sesion(self):
        response = self.client.post(
            reverse("registro"),
            {
                "username": "nuevo_usuario",
                "first_name": "Nuevo",
                "last_name": "Usuario",
                "email": "nuevo@example.com",
                "fechaNacimiento": "2000-01-01",
                "genero": "M",
                "password1": "PasswordSeguro12345",
                "password2": "PasswordSeguro12345",
            },
        )

        UsuarioModelo = get_user_model()

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("index_peliculas"))
        self.assertTrue(UsuarioModelo.objects.filter(username="nuevo_usuario").exists())

        usuario = UsuarioModelo.objects.get(username="nuevo_usuario")
        self.assertEqual(usuario.email, "nuevo@example.com")
        self.assertEqual(usuario.first_name, "Nuevo")
        self.assertEqual(usuario.last_name, "Usuario")
        self.assertEqual(usuario.genero, "M")

    def test_registro_no_permite_email_duplicado(self):
        Usuario.objects.create_user(
            username="usuario1",
            email="repetido@example.com",
            password="PasswordSeguro12345",
        )

        response = self.client.post(
            reverse("registro"),
            {
                "username": "usuario2",
                "first_name": "Usuario",
                "last_name": "Dos",
                "email": "repetido@example.com",
                "fechaNacimiento": "2000-01-01",
                "genero": "N",
                "password1": "PasswordSeguro12345",
                "password2": "PasswordSeguro12345",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un usuario con este correo electrónico.")
        self.assertFalse(Usuario.objects.filter(username="usuario2").exists())

    def test_registro_no_permite_passwords_distintas(self):
        response = self.client.post(
            reverse("registro"),
            {
                "username": "usuario_error",
                "first_name": "Usuario",
                "last_name": "Error",
                "email": "error@example.com",
                "fechaNacimiento": "2000-01-01",
                "genero": "N",
                "password1": "PasswordSeguro12345",
                "password2": "PasswordDistinto12345",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Los dos campos de contraseña no coinciden.")
        self.assertFalse(Usuario.objects.filter(username="usuario_error").exists())

    def test_registro_no_permite_username_duplicado(self):
        Usuario.objects.create_user(
            username="angel",
            email="angel1@example.com",
            password="PasswordSeguro12345",
        )

        response = self.client.post(
            reverse("registro"),
            {
                "username": "angel",
                "first_name": "Angel",
                "last_name": "Duplicado",
                "email": "angel2@example.com",
                "fechaNacimiento": "2000-01-01",
                "genero": "N",
                "password1": "PasswordSeguro12345",
                "password2": "PasswordSeguro12345",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un usuario con este nombre.")
        self.assertEqual(Usuario.objects.filter(username="angel").count(), 1)

    def test_usuario_logueado_no_puede_acceder_a_registro(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("registro"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("index_peliculas"))

    def test_login_correcto_redirige_a_cartelera(self):
        Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
        )

        response = self.client.post(
            reverse("login"),
            {
                "username": "angel",
                "password": "PasswordSeguro12345",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("index_peliculas"))

    def test_login_incorrecto_muestra_error(self):
        Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
        )

        response = self.client.post(
            reverse("login"),
            {
                "username": "angel",
                "password": "mal",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Usuario o contraseña incorrectos.")

    def test_usuario_logueado_no_puede_acceder_a_login(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("index_peliculas"))

    def test_perfil_carga_si_esta_logueado(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            email="angel@example.com",
            first_name="Angel",
            last_name="Villamor",
            fechaNacimiento=date(2000, 1, 1),
            genero="M",
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("perfil"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mi perfil")
        self.assertContains(response, "angel")
        self.assertContains(response, "Angel")
        self.assertContains(response, "Villamor")
        self.assertContains(response, "angel@example.com")
        self.assertContains(response, "Género")
        self.assertContains(response, "Masculino")
        self.assertContains(response, "Editar perfil")
        self.assertContains(response, "No")

    def test_logout_cierra_sesion_y_redirige(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("logout"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("index_peliculas"))

        response_perfil = self.client.get(reverse("perfil"))
        self.assertEqual(response_perfil.status_code, 302)
        self.assertIn(reverse("login"), response_perfil.url)

    def test_registro_no_permite_fecha_nacimiento_futura(self):
        response = self.client.post(
            reverse("registro"),
            {
                "username": "usuario_futuro",
                "first_name": "Usuario",
                "last_name": "Futuro",
                "email": "futuro@example.com",
                "fechaNacimiento": "2999-01-01",
                "genero": "N",
                "password1": "PasswordSeguro12345",
                "password2": "PasswordSeguro12345",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La fecha de nacimiento no puede ser futura.")
        self.assertFalse(Usuario.objects.filter(username="usuario_futuro").exists())

    def test_validar_registro_username_disponible(self):
        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "username",
                "valor": "usuario_disponible",
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertTrue(data["valido"])
        self.assertEqual(data["mensaje"], "Nombre de usuario disponible.")

    def test_validar_registro_username_duplicado(self):
        Usuario.objects.create_user(
            username="angel",
            email="angel@example.com",
            password="PasswordSeguro12345",
        )

        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "username",
                "valor": "angel",
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["valido"])
        self.assertEqual(data["mensaje"], "Ya existe un usuario con este nombre.")

    def test_validar_registro_username_duplicado_no_distingue_mayusculas(self):
        Usuario.objects.create_user(
            username="angel",
            email="angel@example.com",
            password="PasswordSeguro12345",
        )

        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "username",
                "valor": "ANGEL",
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["valido"])
        self.assertEqual(data["mensaje"], "Ya existe un usuario con este nombre.")

    def test_validar_registro_username_invalido(self):
        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "username",
                "valor": "usuario???",
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["valido"])
        self.assertEqual(
            data["mensaje"],
            "Solo se permiten letras, números y los caracteres @/./+/-/_.",
        )

    def test_validar_registro_username_vacio(self):
        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "username",
                "valor": "",
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["valido"])
        self.assertEqual(data["mensaje"], "Este campo es obligatorio.")

    def test_validar_registro_email_disponible(self):
        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "email",
                "valor": "nuevo@example.com",
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertTrue(data["valido"])
        self.assertEqual(data["mensaje"], "Correo electrónico disponible.")

    def test_validar_registro_email_duplicado(self):
        Usuario.objects.create_user(
            username="angel",
            email="angel@example.com",
            password="PasswordSeguro12345",
        )

        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "email",
                "valor": "angel@example.com",
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["valido"])
        self.assertEqual(data["mensaje"], "Ya existe un usuario con este correo electrónico.")

    def test_validar_registro_email_duplicado_no_distingue_mayusculas(self):
        Usuario.objects.create_user(
            username="angel",
            email="angel@example.com",
            password="PasswordSeguro12345",
        )

        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "email",
                "valor": "ANGEL@EXAMPLE.COM",
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["valido"])
        self.assertEqual(data["mensaje"], "Ya existe un usuario con este correo electrónico.")

    def test_validar_registro_email_invalido(self):
        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "email",
                "valor": "correo_invalido",
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["valido"])
        self.assertEqual(data["mensaje"], "Introduce una dirección de correo electrónico válida.")

    def test_validar_registro_email_vacio(self):
        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "email",
                "valor": "",
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["valido"])
        self.assertEqual(data["mensaje"], "Este campo es obligatorio.")

    def test_validar_registro_campo_no_valido(self):
        response = self.client.get(
            reverse("validar_registro"),
            {
                "campo": "telefono",
                "valor": "123456789",
            },
        )

        self.assertEqual(response.status_code, 400)

        data = response.json()

        self.assertFalse(data["valido"])
        self.assertEqual(data["mensaje"], "Campo no válido.")

    def test_editar_perfil_redirige_si_no_esta_logueado(self):
        response = self.client.get(reverse("editar_perfil"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_editar_perfil_carga_si_esta_logueado(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            email="angel@example.com",
            first_name="Angel",
            last_name="Villamor",
            fechaNacimiento=date(2000, 1, 1),
            genero="M",
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("editar_perfil"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editar perfil")
        self.assertContains(response, "angel@example.com")
        self.assertContains(response, "Guardar cambios")
        self.assertContains(response, "Volver al perfil")

    def test_editar_perfil_actualiza_datos_correctamente(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            email="angel@example.com",
            first_name="Angel",
            last_name="Villamor",
            fechaNacimiento=date(2000, 1, 1),
            genero="N",
        )

        self.client.force_login(usuario)

        response = self.client.post(
            reverse("editar_perfil"),
            {
                "first_name": "Ángel",
                "last_name": "Villamor Martínez",
                "email": "nuevo@example.com",
                "fechaNacimiento": "2001-02-03",
                "genero": "M",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("perfil"))

        usuario.refresh_from_db()

        self.assertEqual(usuario.first_name, "Ángel")
        self.assertEqual(usuario.last_name, "Villamor Martínez")
        self.assertEqual(usuario.email, "nuevo@example.com")
        self.assertEqual(usuario.fechaNacimiento, date(2001, 2, 3))
        self.assertEqual(usuario.genero, "M")

    def test_editar_perfil_no_permite_email_duplicado_de_otro_usuario(self):
        Usuario.objects.create_user(
            username="lucas",
            password="PasswordSeguro12345",
            email="lucas@example.com",
        )

        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            email="angel@example.com",
        )

        self.client.force_login(usuario)

        response = self.client.post(
            reverse("editar_perfil"),
            {
                "first_name": "Angel",
                "last_name": "Villamor",
                "email": "lucas@example.com",
                "fechaNacimiento": "2000-01-01",
                "genero": "N",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un usuario con este correo electrónico.")

        usuario.refresh_from_db()
        self.assertEqual(usuario.email, "angel@example.com")

    def test_editar_perfil_permite_mantener_su_mismo_email(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            email="angel@example.com",
            first_name="Angel",
            last_name="Villamor",
            genero="N",
        )

        self.client.force_login(usuario)

        response = self.client.post(
            reverse("editar_perfil"),
            {
                "first_name": "Angel",
                "last_name": "Villamor",
                "email": "angel@example.com",
                "fechaNacimiento": "2000-01-01",
                "genero": "O",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("perfil"))

        usuario.refresh_from_db()
        self.assertEqual(usuario.email, "angel@example.com")
        self.assertEqual(usuario.genero, "O")

    def test_editar_perfil_no_permite_fecha_futura(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            email="angel@example.com",
        )

        self.client.force_login(usuario)

        response = self.client.post(
            reverse("editar_perfil"),
            {
                "first_name": "Angel",
                "last_name": "Villamor",
                "email": "angel@example.com",
                "fechaNacimiento": "2999-01-01",
                "genero": "N",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La fecha de nacimiento no puede ser futura.")

    def test_perfil_muestra_genero_del_usuario(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            email="angel@example.com",
            first_name="Angel",
            last_name="Villamor",
            fechaNacimiento=date(2000, 1, 1),
            genero="M",
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("perfil"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Género")
        self.assertContains(response, "Masculino")
        self.assertContains(response, "Editar perfil")

    def test_socio_redirige_si_no_esta_logueado(self):
        response = self.client.get(reverse("socio"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_socio_carga_si_esta_logueado_y_no_es_socio(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=False,
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("socio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hacerse socio")
        self.assertContains(response, "Confirmar alta como socio")
        self.assertContains(response, "Volver al perfil")

    def test_socio_post_marca_usuario_como_socio(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=False,
        )

        self.client.force_login(usuario)

        response = self.client.post(reverse("socio"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("perfil"))

        usuario.refresh_from_db()
        self.assertTrue(usuario.socio)

    def test_socio_post_si_ya_es_socio_no_rompe(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.post(reverse("socio"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("perfil"))

        usuario.refresh_from_db()
        self.assertTrue(usuario.socio)

    def test_bonos_redirige_si_no_esta_logueado(self):
        response = self.client.get(reverse("bonos"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_bonos_carga_tipos_disponibles_si_es_socio(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("bonos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bonos FICinema")
        self.assertContains(response, "5 EN 3")
        self.assertContains(response, "10 EN 5")
        self.assertContains(response, "20 EN 10")
        self.assertContains(response, "Ir a compra")
        self.assertContains(response, "No tienes bonos activos disponibles.")

    def test_confirmar_bono_redirige_si_no_esta_logueado(self):
        response = self.client.get(reverse("confirmar_bono", args=["5 EN 3"]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_confirmar_bono_carga_bono_valido_si_es_socio(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("confirmar_bono", args=["5 EN 3"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirmar compra")
        self.assertContains(response, "5 EN 3")
        self.assertContains(response, "Ves 5 pagas 3")
        self.assertContains(response, "Cancelar")
        self.assertContains(response, "compra se simula")

    def test_confirmar_bono_invalido_redirige_a_bonos_si_es_socio(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("confirmar_bono", args=["BONO INVALIDO"]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("bonos"))

    def test_comprar_bono_crea_bono_asociado_al_usuario_si_es_socio(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.post(reverse("comprar_bono", args=["5 EN 3"]), {"titular": "Angel Villamor"})

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("bonos"))

        self.assertEqual(Bono.objects.count(), 1)

        bono = Bono.objects.first()

        self.assertEqual(bono.usuario, usuario)
        self.assertEqual(bono.tipo, "5 EN 3")
        self.assertGreaterEqual(bono.fechaCaducidad, date.today())

    def test_comprar_varios_bonos_los_muestra_en_bonos_si_es_socio(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        self.client.post(reverse("comprar_bono", args=["5 EN 3"]), {"titular": "Angel Villamor"})
        self.client.post(reverse("comprar_bono", args=["10 EN 5"]), {"titular": "Angel Villamor"})

        response = self.client.get(reverse("bonos"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Bono.objects.filter(usuario=usuario).count(), 2)
        self.assertContains(response, "5 EN 3")
        self.assertContains(response, "10 EN 5")
        self.assertContains(response, "Código:")

    def test_comprar_bono_invalido_no_crea_bono_si_es_socio(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.post(reverse("comprar_bono", args=["BONO INVALIDO"]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("bonos"))
        self.assertEqual(Bono.objects.count(), 0)

    def test_comprar_bono_por_get_no_esta_permitido(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("comprar_bono", args=["5 EN 3"]))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(Bono.objects.count(), 0)

    def test_registro_no_permite_username_duplicado_con_mayusculas(self):
        Usuario.objects.create_user(
            username="angel",
            email="angel@example.com",
            password="PasswordSeguro12345",
        )

        response = self.client.post(
            reverse("registro"),
            {
                "username": "ANGEL",
                "first_name": "Angel",
                "last_name": "Duplicado",
                "email": "angel2@example.com",
                "fechaNacimiento": "2000-01-01",
                "genero": "N",
                "password1": "PasswordSeguro12345",
                "password2": "PasswordSeguro12345",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un usuario con este nombre.")
        self.assertFalse(Usuario.objects.filter(username="ANGEL").exists())

    def test_registro_no_permite_email_duplicado_con_mayusculas(self):
        Usuario.objects.create_user(
            username="usuario1",
            email="angel@example.com",
            password="PasswordSeguro12345",
        )

        response = self.client.post(
            reverse("registro"),
            {
                "username": "usuario2",
                "first_name": "Usuario",
                "last_name": "Dos",
                "email": "ANGEL@EXAMPLE.COM",
                "fechaNacimiento": "2000-01-01",
                "genero": "N",
                "password1": "PasswordSeguro12345",
                "password2": "PasswordSeguro12345",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un usuario con este correo electrónico.")
        self.assertFalse(Usuario.objects.filter(username="usuario2").exists())

    def test_editar_perfil_no_permite_email_duplicado_con_mayusculas(self):
        Usuario.objects.create_user(
            username="lucas",
            password="PasswordSeguro12345",
            email="lucas@example.com",
        )

        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            email="angel@example.com",
        )

        self.client.force_login(usuario)

        response = self.client.post(
            reverse("editar_perfil"),
            {
                "first_name": "Angel",
                "last_name": "Villamor",
                "email": "LUCAS@EXAMPLE.COM",
                "fechaNacimiento": "2000-01-01",
                "genero": "N",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un usuario con este correo electrónico.")

        usuario.refresh_from_db()
        self.assertEqual(usuario.email, "angel@example.com")

    def test_usuario_no_socio_ve_bonos_pero_no_puede_ir_a_compra(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=False,
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("bonos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bonos FICinema")
        self.assertContains(response, "Hazte socio para comprar")
        self.assertContains(response, "Para comprar bonos debes darte de alta como socio")
        self.assertNotContains(response, "Ir a compra")

    def test_usuario_no_socio_no_puede_acceder_a_confirmar_bono(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=False,
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("confirmar_bono", args=["5 EN 3"]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("socio"))

    def test_usuario_no_socio_no_puede_comprar_bono_por_post(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=False,
        )

        self.client.force_login(usuario)

        response = self.client.post(reverse("comprar_bono", args=["5 EN 3"]), {"titular": "Angel Villamor"})

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("socio"))
        self.assertEqual(Bono.objects.filter(usuario=usuario).count(), 0)

    def test_usuario_socio_puede_acceder_a_confirmar_bono(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("confirmar_bono", args=["5 EN 3"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirmar compra")
        self.assertContains(response, "5 EN 3")
        self.assertContains(response, "Cancelar")

    def test_usuario_socio_puede_comprar_bono(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.post(reverse("comprar_bono", args=["10 EN 5"]), {"titular": "Angel Villamor"})

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("bonos"))

        self.assertEqual(Bono.objects.filter(usuario=usuario).count(), 1)

        bono = Bono.objects.get(usuario=usuario)
        self.assertEqual(bono.tipo, "10 EN 5")

    def test_usuario_socio_puede_darse_de_baja(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.post(reverse("baja_socio"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("perfil"))

        usuario.refresh_from_db()
        self.assertFalse(usuario.socio)

    def test_baja_socio_conserva_bonos_comprados(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        Bono.objects.create(
            tipo="5 EN 3",
            fechaCaducidad=date(2027, 5, 10),
            usuario=usuario,
        )

        self.client.force_login(usuario)

        response = self.client.post(reverse("baja_socio"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("perfil"))

        usuario.refresh_from_db()

        self.assertFalse(usuario.socio)
        self.assertEqual(Bono.objects.filter(usuario=usuario).count(), 1)

    def test_usuario_no_socio_puede_hacer_post_baja_sin_romper(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=False,
        )

        self.client.force_login(usuario)

        response = self.client.post(reverse("baja_socio"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("perfil"))

        usuario.refresh_from_db()
        self.assertFalse(usuario.socio)

    def test_usuario_no_logueado_no_puede_acceder_a_bonos(self):
        response = self.client.get(reverse("bonos"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_usuario_no_logueado_no_puede_acceder_a_socio(self):
        response = self.client.get(reverse("socio"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_usuario_no_logueado_no_puede_acceder_a_confirmar_bono(self):
        response = self.client.get(reverse("confirmar_bono", args=["5 EN 3"]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_usuario_no_logueado_no_puede_comprar_bono(self):
        response = self.client.post(reverse("comprar_bono", args=["5 EN 3"]), {"titular": "Angel Villamor"})

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_confirmar_bono_tipo_invalido_redirige_a_bonos(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.get(reverse("confirmar_bono", args=["BONO INVENTADO"]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("bonos"))

    def test_comprar_bono_tipo_invalido_no_crea_bono(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
            socio=True,
        )

        self.client.force_login(usuario)

        response = self.client.post(reverse("comprar_bono", args=["BONO INVENTADO"]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("bonos"))
        self.assertEqual(Bono.objects.filter(usuario=usuario).count(), 0)

class EntradaModelTest(TestCase):

    def test_entrada_asigna_codigo_automaticamente(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
        )

        entrada = Entrada.objects.create(
            movie_id=1,
            titulo_pelicula="Pelicula Test",
            fecha=date.today() + timedelta(days=1),
            hora="16:00",
            usuario=usuario,
        )

        self.assertEqual(entrada.codigo, 1)
        self.assertEqual(entrada.usuario, usuario)
        self.assertEqual(entrada.titulo_pelicula, "Pelicula Test")

    def test_varias_entradas_tienen_codigos_distintos(self):
        usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
        )

        entrada1 = Entrada.objects.create(
            movie_id=1,
            titulo_pelicula="Pelicula 1",
            fecha=date.today() + timedelta(days=1),
            hora="16:00",
            usuario=usuario,
        )

        entrada2 = Entrada.objects.create(
            movie_id=2,
            titulo_pelicula="Pelicula 2",
            fecha=date.today() + timedelta(days=2),
            hora="18:30",
            usuario=usuario,
        )

        self.assertNotEqual(entrada1.codigo, entrada2.codigo)
        self.assertEqual(entrada1.codigo, 1)
        self.assertEqual(entrada2.codigo, 2)


class EntradaViewTest(TestCase):

    def setUp(self):
        cache.clear()

        self.usuario = Usuario.objects.create_user(
            username="angel",
            password="PasswordSeguro12345",
        )

        self.otro_usuario = Usuario.objects.create_user(
            username="lucas",
            password="PasswordSeguro12345",
        )

        self.sala = Sala.objects.create(
            nombre="Sala Test",
            filas=5,
            columnas=5,
            activa=True,
        )

        inicio = timezone.make_aware(
            timezone.datetime.combine(
                date.today() + timedelta(days=1),
                time(18, 0),
            )
        )

        fin = inicio + timedelta(minutes=140)

        self.sesion = SesionCine.objects.create(
            movie_id=999,
            titulo_pelicula="Avatar Test",
            fecha=date.today() + timedelta(days=1),
            inicio=inicio,
            fin=fin,
            duracion_minutos=120,
            margen_limpieza_minutos=20,
            popularidad=90,
            valoracion=8.5,
            demanda_estimada=100,
            sala=self.sala,
        )

    def crear_sesion_pasada(self):
        inicio = timezone.make_aware(
            timezone.datetime.combine(
                date.today() - timedelta(days=1),
                time(18, 0),
            )
        )

        fin = inicio + timedelta(minutes=140)

        return SesionCine.objects.create(
            movie_id=1000,
            titulo_pelicula="Película Pasada",
            fecha=date.today() - timedelta(days=1),
            inicio=inicio,
            fin=fin,
            duracion_minutos=120,
            margen_limpieza_minutos=20,
            popularidad=50,
            valoracion=6.0,
            demanda_estimada=60,
            sala=self.sala,
        )

    def test_mis_entradas_redirige_si_no_esta_logueado(self):
        response = self.client.get(reverse("mis_entradas"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_mis_entradas_carga_si_esta_logueado_y_no_tiene_entradas(self):
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("mis_entradas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mis entradas")
        self.assertContains(response, "No tienes entradas activas.")
        self.assertContains(response, "Aún no tienes entradas en el historial.")

    def test_mis_entradas_muestra_entradas_del_usuario(self):
        Entrada.objects.create(
            sesion=self.sesion,
            movie_id=self.sesion.movie_id,
            titulo_pelicula=self.sesion.titulo_pelicula,
            fecha=self.sesion.fecha,
            hora=self.sesion.hora_inicio_formateada(),
            sala=self.sala,
            asiento="B3",
            usuario=self.usuario,
        )

        self.client.force_login(self.usuario)

        response = self.client.get(reverse("mis_entradas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Avatar Test")
        self.assertContains(response, "B3")
        self.assertContains(response, "Sala Test")
        self.assertContains(response, "Código:")

    def test_mis_entradas_no_muestra_entradas_de_otro_usuario(self):
        Entrada.objects.create(
            sesion=self.sesion,
            movie_id=self.sesion.movie_id,
            titulo_pelicula="Entrada de Lucas",
            fecha=self.sesion.fecha,
            hora=self.sesion.hora_inicio_formateada(),
            sala=self.sala,
            asiento="A1",
            usuario=self.otro_usuario,
        )

        self.client.force_login(self.usuario)

        response = self.client.get(reverse("mis_entradas"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Entrada de Lucas")
        self.assertContains(response, "No tienes entradas activas.")
        self.assertContains(response, "Aún no tienes entradas en el historial.")
    
    def test_confirmar_entrada_redirige_si_no_esta_logueado(self):
        response = self.client.post(
            reverse("confirmar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "A1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_confirmar_entrada_carga_si_datos_validos(self):
        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("confirmar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "A1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirmar compra")
        self.assertContains(response, "Avatar Test")
        self.assertContains(response, "A1")
        self.assertContains(response, "Sala Test")

    def test_confirmar_entrada_con_datos_incompletos_redirige(self):
        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("confirmar_entrada"),
            {
                "sesion_id": "",
                "asiento": "A1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("index_peliculas"))

    def test_confirmar_entrada_no_permite_fecha_pasada(self):
        sesion_pasada = self.crear_sesion_pasada()
        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("confirmar_entrada"),
            {
                "sesion_id": sesion_pasada.id,
                "asiento": "A1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("detalle_pelicula", args=[sesion_pasada.movie_id]))

    def test_confirmar_entrada_no_permite_asiento_inexistente(self):
        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("confirmar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "Z99",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("detalle_pelicula", args=[self.sesion.movie_id]))

    def test_confirmar_entrada_no_permite_asiento_ocupado(self):
        Entrada.objects.create(
            sesion=self.sesion,
            movie_id=self.sesion.movie_id,
            titulo_pelicula=self.sesion.titulo_pelicula,
            fecha=self.sesion.fecha,
            hora=self.sesion.hora_inicio_formateada(),
            sala=self.sala,
            asiento="A1",
            usuario=self.otro_usuario,
        )

        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("confirmar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "A1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("detalle_pelicula", args=[self.sesion.movie_id]))

    def test_confirmar_entrada_por_get_no_esta_permitido(self):
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("confirmar_entrada"))

        self.assertEqual(response.status_code, 405)

    def test_comprar_entrada_redirige_si_no_esta_logueado(self):
        response = self.client.post(
            reverse("comprar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "A1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(Entrada.objects.count(), 0)

    def test_comprar_entrada_crea_entrada_asociada_al_usuario(self):
        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("comprar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "A1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("mis_entradas"))
        self.assertEqual(Entrada.objects.count(), 1)

        entrada = Entrada.objects.first()

        self.assertEqual(entrada.usuario, self.usuario)
        self.assertEqual(entrada.sesion, self.sesion)
        self.assertEqual(entrada.movie_id, self.sesion.movie_id)
        self.assertEqual(entrada.titulo_pelicula, "Avatar Test")
        self.assertEqual(entrada.fecha, self.sesion.fecha)
        self.assertEqual(entrada.hora, self.sesion.hora_inicio_formateada())
        self.assertEqual(entrada.sala, self.sala)
        self.assertEqual(entrada.asiento, "A1")

    def test_comprar_entrada_con_datos_incompletos_no_crea_entrada(self):
        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("comprar_entrada"),
            {
                "sesion_id": "",
                "asiento": "A1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("index_peliculas"))
        self.assertEqual(Entrada.objects.count(), 0)

    def test_comprar_entrada_no_permite_fecha_pasada(self):
        sesion_pasada = self.crear_sesion_pasada()
        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("comprar_entrada"),
            {
                "sesion_id": sesion_pasada.id,
                "asiento": "A1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("detalle_pelicula", args=[sesion_pasada.movie_id]))
        self.assertEqual(Entrada.objects.count(), 0)

    def test_comprar_entrada_no_permite_asiento_inexistente(self):
        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("comprar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "Z99",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("detalle_pelicula", args=[self.sesion.movie_id]))
        self.assertEqual(Entrada.objects.count(), 0)

    def test_comprar_entrada_no_permite_asiento_ocupado(self):
        Entrada.objects.create(
            sesion=self.sesion,
            movie_id=self.sesion.movie_id,
            titulo_pelicula=self.sesion.titulo_pelicula,
            fecha=self.sesion.fecha,
            hora=self.sesion.hora_inicio_formateada(),
            sala=self.sala,
            asiento="A1",
            usuario=self.otro_usuario,
        )

        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("comprar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "A1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("detalle_pelicula", args=[self.sesion.movie_id]))
        self.assertEqual(Entrada.objects.count(), 1)

    def test_comprar_entrada_por_get_no_esta_permitido(self):
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("comprar_entrada"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(Entrada.objects.count(), 0)

    def test_comprar_entrada_con_bono_descuenta_uso_y_guarda_bono(self):
        bono = Bono.objects.create(
            tipo="5 EN 3",
            fechaCaducidad=date.today() + timedelta(days=30),
            usuario=self.usuario,
        )

        usos_iniciales = bono.usos_restantes

        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("comprar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "C1",
                "codigo_bono": str(bono.codigo),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("mis_entradas"))

        entrada = Entrada.objects.get(usuario=self.usuario, asiento="C1")
        bono.refresh_from_db()

        self.assertEqual(entrada.bono_usado, bono)
        self.assertEqual(bono.usos_restantes, usos_iniciales - 1)

    def test_comprar_entrada_no_permite_bono_agotado(self):
        bono = Bono.objects.create(
            tipo="5 EN 3",
            fechaCaducidad=date.today() + timedelta(days=30),
            usuario=self.usuario,
        )
        bono.usos_restantes = 0
        bono.save(update_fields=["usos_restantes"])

        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("comprar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "C2",
                "codigo_bono": str(bono.codigo),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("detalle_pelicula", args=[self.sesion.movie_id]))
        self.assertFalse(Entrada.objects.filter(usuario=self.usuario, asiento="C2").exists())

    def test_comprar_entrada_no_permite_sesion_ya_empezada_hoy(self):
        inicio = timezone.now() - timedelta(minutes=10)
        fin = timezone.now() + timedelta(minutes=120)

        sesion_empezada = SesionCine.objects.create(
            movie_id=2000,
            titulo_pelicula="Sesión empezada",
            fecha=timezone.localdate(),
            inicio=inicio,
            fin=fin,
            duracion_minutos=120,
            margen_limpieza_minutos=20,
            popularidad=50,
            valoracion=7,
            demanda_estimada=60,
            sala=self.sala,
        )

        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("comprar_entrada"),
            {
                "sesion_id": sesion_empezada.id,
                "asiento": "A2",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("detalle_pelicula", args=[sesion_empezada.movie_id]))
        self.assertFalse(Entrada.objects.filter(sesion=sesion_empezada).exists())

    def test_confirmar_entrada_no_permite_sesion_ya_empezada_hoy(self):
        inicio = timezone.now() - timedelta(minutes=10)
        fin = timezone.now() + timedelta(minutes=120)

        sesion_empezada = SesionCine.objects.create(
            movie_id=2001,
            titulo_pelicula="Sesión empezada confirmar",
            fecha=timezone.localdate(),
            inicio=inicio,
            fin=fin,
            duracion_minutos=120,
            margen_limpieza_minutos=20,
            popularidad=50,
            valoracion=7,
            demanda_estimada=60,
            sala=self.sala,
        )

        self.client.force_login(self.usuario)

        response = self.client.post(
            reverse("confirmar_entrada"),
            {
                "sesion_id": sesion_empezada.id,
                "asiento": "A3",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("detalle_pelicula", args=[sesion_empezada.movie_id]))

    def test_cancelar_entrada_devuelve_uso_al_bono(self):
        bono = Bono.objects.create(
            tipo="5 EN 3",
            fechaCaducidad=date.today() + timedelta(days=30),
            usuario=self.usuario,
        )

        bono.usos_restantes = 4
        bono.save(update_fields=["usos_restantes"])

        entrada = Entrada.objects.create(
            sesion=self.sesion,
            movie_id=self.sesion.movie_id,
            titulo_pelicula=self.sesion.titulo_pelicula,
            fecha=self.sesion.fecha,
            hora=self.sesion.hora_inicio_formateada(),
            sala=self.sala,
            asiento="D1",
            usuario=self.usuario,
            bono_usado=bono,
        )

        self.client.force_login(self.usuario)

        response = self.client.post(reverse("cancelar_entrada", args=[entrada.id]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("mis_entradas"))

        entrada.refresh_from_db()
        bono.refresh_from_db()

        self.assertEqual(entrada.estado, Entrada.ESTADO_CANCELADA)
        self.assertEqual(bono.usos_restantes, 5)

    def test_mis_entradas_mueve_entrada_pasada_a_historial(self):
        sesion_pasada = self.crear_sesion_pasada()

        entrada = Entrada.objects.create(
            sesion=sesion_pasada,
            movie_id=sesion_pasada.movie_id,
            titulo_pelicula=sesion_pasada.titulo_pelicula,
            fecha=sesion_pasada.fecha,
            hora=sesion_pasada.hora_inicio_formateada(),
            sala=self.sala,
            asiento="E1",
            usuario=self.usuario,
        )

        self.client.force_login(self.usuario)

        response = self.client.get(reverse("mis_entradas"))

        entrada.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(entrada.estado, Entrada.ESTADO_CADUCADA)
        self.assertContains(response, "Historial de entradas")
        self.assertContains(response, "Película Pasada")

    def test_perfil_muestra_enlace_a_mis_entradas(self):
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("perfil"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mis entradas")


class StaffPanelViewTest(TestCase):

    def setUp(self):
        cache.clear()

        self.staff = Usuario.objects.create_user(
            username="admin",
            password="PasswordSeguro12345",
            is_staff=True,
        )

        self.usuario = Usuario.objects.create_user(
            username="cliente",
            password="PasswordSeguro12345",
            is_staff=False,
        )

        self.sala = Sala.objects.create(
            nombre="Sala Ocupacion",
            filas=2,
            columnas=5,
            activa=True,
        )

        inicio = timezone.make_aware(
            timezone.datetime.combine(
                timezone.localdate() + timedelta(days=1),
                time(18, 0),
            )
        )
        fin = inicio + timedelta(minutes=140)

        self.sesion = SesionCine.objects.create(
            movie_id=3000,
            titulo_pelicula="Pelicula Staff",
            fecha=timezone.localdate() + timedelta(days=1),
            inicio=inicio,
            fin=fin,
            duracion_minutos=120,
            margen_limpieza_minutos=20,
            popularidad=80,
            valoracion=8.0,
            demanda_estimada=90,
            sala=self.sala,
        )

        for asiento in ["A1", "A2", "A3", "A4"]:
            Entrada.objects.create(
                sesion=self.sesion,
                movie_id=self.sesion.movie_id,
                titulo_pelicula=self.sesion.titulo_pelicula,
                fecha=self.sesion.fecha,
                hora=self.sesion.hora_inicio_formateada(),
                sala=self.sala,
                asiento=asiento,
                usuario=self.usuario,
            )

    def test_perfil_usuario_normal_muestra_id_usuario_y_mis_entradas(self):
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("perfil"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ID USUARIO")
        self.assertNotContains(response, "ID STAFF")
        self.assertContains(response, "Mis entradas")

    def test_perfil_staff_muestra_id_staff_y_no_mis_entradas(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("perfil"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ID STAFF")
        self.assertNotContains(response, "ID USUARIO")
        self.assertNotContains(response, "Mis entradas")

    def test_staff_no_puede_acceder_a_mis_entradas_personales(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("mis_entradas"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("panel_interno"))

    def test_staff_no_puede_comprar_entrada(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("comprar_entrada"),
            {
                "sesion_id": self.sesion.id,
                "asiento": "B1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("panel_interno"))
        self.assertFalse(
            Entrada.objects.filter(
                usuario=self.staff,
                sesion=self.sesion,
                asiento="B1",
            ).exists()
        )

    def test_usuario_normal_no_puede_acceder_al_panel_interno(self):
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("panel_interno"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("index_peliculas"))

    def test_panel_interno_muestra_resumen_staff(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("panel_interno"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Panel interno")
        self.assertEqual(response.context["proximas_sesiones"], 1)
        self.assertEqual(response.context["entradas_activas"], 4)
        self.assertEqual(response.context["usuarios_totales"], 2)
        self.assertEqual(len(response.context["sesiones_destacadas"]), 1)

    def test_panel_interno_calcula_ocupacion_sesion_destacada(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("panel_interno"))

        sesion = response.context["sesiones_destacadas"][0]

        self.assertEqual(sesion.capacidad, 10)
        self.assertEqual(sesion.entradas_vendidas, 4)
        self.assertEqual(sesion.ocupacion, 40.0)

    def test_panel_sesiones_muestra_ocupacion_por_sesion(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("panel_sesiones"), {"filtro": "proximas"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtro"], "proximas")
        self.assertEqual(len(response.context["sesiones"]), 1)

        sesion = response.context["sesiones"][0]

        self.assertEqual(sesion.titulo_pelicula, "Pelicula Staff")
        self.assertEqual(sesion.capacidad, 10)
        self.assertEqual(sesion.entradas_vendidas, 4)
        self.assertEqual(sesion.ocupacion, 40.0)
        self.assertEqual(response.context["total_sesiones"], 1)
        self.assertEqual(response.context["total_entradas_vendidas"], 4)
        self.assertEqual(response.context["total_capacidad"], 10)
        self.assertEqual(response.context["ocupacion_media"], 40.0)

    def test_panel_sesiones_pasadas_mantiene_vendidas_y_ocupacion_historica(self):
        inicio_pasado = timezone.make_aware(
            timezone.datetime.combine(
                timezone.localdate() - timedelta(days=1),
                time(18, 0),
            )
        )
        fin_pasado = inicio_pasado + timedelta(minutes=140)

        sesion_pasada = SesionCine.objects.create(
            movie_id=3001,
            titulo_pelicula="Pelicula Historica",
            fecha=timezone.localdate() - timedelta(days=1),
            inicio=inicio_pasado,
            fin=fin_pasado,
            duracion_minutos=120,
            margen_limpieza_minutos=20,
            popularidad=70,
            valoracion=7.5,
            demanda_estimada=80,
            sala=self.sala,
        )

        Entrada.objects.create(
            sesion=sesion_pasada,
            asiento="B1",
            usuario=self.usuario,
            estado=Entrada.ESTADO_CADUCADA,
        )
        Entrada.objects.create(
            sesion=sesion_pasada,
            asiento="B2",
            usuario=self.usuario,
            estado=Entrada.ESTADO_USADA,
        )
        Entrada.objects.create(
            sesion=sesion_pasada,
            asiento="B3",
            usuario=self.usuario,
            estado=Entrada.ESTADO_CANCELADA,
        )

        self.client.force_login(self.staff)

        response = self.client.get(reverse("panel_sesiones"), {"filtro": "pasadas"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtro"], "pasadas")

        sesiones = list(response.context["sesiones"])
        sesion = next(item for item in sesiones if item.id == sesion_pasada.id)

        self.assertEqual(sesion.capacidad, 10)
        self.assertEqual(sesion.entradas_vendidas, 2)
        self.assertEqual(sesion.ocupacion, 20.0)
        self.assertGreaterEqual(response.context["total_sesiones"], 1)
        self.assertGreaterEqual(response.context["total_entradas_vendidas"], 2)
        self.assertGreaterEqual(response.context["total_capacidad"], 10)
        self.assertIn("ocupacion_media", response.context)

    def test_panel_sesiones_filtro_hoy_no_muestra_sesion_futura(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("panel_sesiones"), {"filtro": "hoy"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtro"], "hoy")
        self.assertEqual(len(response.context["sesiones"]), 0)

    def test_panel_entradas_filtra_por_activas(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("panel_entradas"), {"estado": Entrada.ESTADO_ACTIVA})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["estado"], Entrada.ESTADO_ACTIVA)
        self.assertEqual(len(response.context["entradas"]), 4)

        for entrada in response.context["entradas"]:
            self.assertEqual(entrada.estado, Entrada.ESTADO_ACTIVA)

    def test_panel_bonos_cuenta_y_filtra_bonos_activos_agotados_y_caducados(self):
        Bono.objects.create(
            tipo="5 EN 3",
            fechaCaducidad=date.today() + timedelta(days=30),
            usuario=self.usuario,
        )

        bono_agotado = Bono.objects.create(
            tipo="10 EN 5",
            fechaCaducidad=date.today() + timedelta(days=30),
            usuario=self.usuario,
        )
        bono_agotado.usos_restantes = 0
        bono_agotado.save(update_fields=["usos_restantes"])

        Bono.objects.create(
            tipo="20 EN 10",
            fechaCaducidad=date.today() - timedelta(days=1),
            usuario=self.usuario,
        )

        self.client.force_login(self.staff)

        response_activos = self.client.get(reverse("panel_bonos"), {"filtro": "activos"})
        response_agotados = self.client.get(reverse("panel_bonos"), {"filtro": "agotados"})
        response_caducados = self.client.get(reverse("panel_bonos"), {"filtro": "caducados"})

        self.assertEqual(response_activos.status_code, 200)
        self.assertEqual(response_agotados.status_code, 200)
        self.assertEqual(response_caducados.status_code, 200)

        self.assertEqual(len(response_activos.context["bonos"]), 1)
        self.assertEqual(len(response_agotados.context["bonos"]), 1)
        self.assertEqual(len(response_caducados.context["bonos"]), 1)

    def test_panel_usuarios_muestra_totales_por_usuario(self):
        Bono.objects.create(
            tipo="5 EN 3",
            fechaCaducidad=date.today() + timedelta(days=30),
            usuario=self.usuario,
        )

        self.client.force_login(self.staff)

        response = self.client.get(reverse("panel_usuarios"), {"filtro": "clientes"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtro"], "clientes")
        self.assertEqual(len(response.context["usuarios"]), 1)

        usuario = response.context["usuarios"][0]

        self.assertEqual(usuario.username, "cliente")
        self.assertEqual(usuario.total_entradas, 4)
        self.assertEqual(usuario.total_bonos, 1)



class QREntradaRealTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="usuarioqr",
            email="usuarioqr@example.com",
            password="testpass123",
        )
        self.otro_usuario = Usuario.objects.create_user(
            username="otroqr",
            email="otroqr@example.com",
            password="testpass123",
        )
        self.staff = Usuario.objects.create_user(
            username="staffqr",
            email="staffqr@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.sala = Sala.objects.create(nombre="Sala QR", filas=5, columnas=5)
        inicio = timezone.now() + timedelta(days=1)
        self.sesion = SesionCine.objects.create(
            movie_id=12345,
            titulo_pelicula="Película QR",
            fecha=timezone.localdate() + timedelta(days=1),
            inicio=inicio,
            fin=inicio + timedelta(minutes=120),
            duracion_minutos=100,
            margen_limpieza_minutos=20,
            sala=self.sala,
        )
        self.entrada = Entrada.objects.create(
            sesion=self.sesion,
            movie_id=self.sesion.movie_id,
            titulo_pelicula=self.sesion.titulo_pelicula,
            fecha=self.sesion.fecha,
            hora=self.sesion.hora_inicio_formateada(),
            sala=self.sala,
            asiento="A1",
            usuario=self.usuario,
        )

    def test_qr_entrada_devuelve_png_al_propietario(self):
        self.client.login(username="usuarioqr", password="testpass123")

        response = self.client.get(reverse("qr_entrada", args=[self.entrada.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))

    def test_qr_entrada_es_distinto_para_entradas_distintas(self):
        otra_entrada = Entrada.objects.create(
            sesion=self.sesion,
            movie_id=self.sesion.movie_id,
            titulo_pelicula=self.sesion.titulo_pelicula,
            fecha=self.sesion.fecha,
            hora=self.sesion.hora_inicio_formateada(),
            sala=self.sala,
            asiento="A2",
            usuario=self.usuario,
        )
        self.client.login(username="usuarioqr", password="testpass123")

        response_uno = self.client.get(reverse("qr_entrada", args=[self.entrada.id]))
        response_dos = self.client.get(reverse("qr_entrada", args=[otra_entrada.id]))

        self.assertNotEqual(response_uno.content, response_dos.content)

    def test_otro_usuario_no_puede_ver_qr_ajeno(self):
        self.client.login(username="otroqr", password="testpass123")

        response = self.client.get(reverse("qr_entrada", args=[self.entrada.id]))

        self.assertEqual(response.status_code, 403)

    def test_staff_puede_ver_qr_de_cualquier_entrada(self):
        self.client.login(username="staffqr", password="testpass123")

        response = self.client.get(reverse("qr_entrada", args=[self.entrada.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_entrada_cancelada_no_devuelve_qr_activo(self):
        self.entrada.estado = Entrada.ESTADO_CANCELADA
        self.entrada.save(update_fields=["estado"])
        self.client.login(username="usuarioqr", password="testpass123")

        response = self.client.get(reverse("qr_entrada", args=[self.entrada.id]))

        self.assertEqual(response.status_code, 410)
        self.assertContains(response, "no tiene QR de acceso activo", status_code=410)


class VerificacionEntradaQRTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="usuarioverifica",
            email="usuarioverifica@example.com",
            password="testpass123",
        )
        self.sala = Sala.objects.create(nombre="Sala Verificación", filas=4, columnas=5)
        inicio = timezone.now() + timedelta(days=1)
        self.sesion = SesionCine.objects.create(
            movie_id=54321,
            titulo_pelicula="Película Verificable",
            fecha=timezone.localdate() + timedelta(days=1),
            inicio=inicio,
            fin=inicio + timedelta(minutes=120),
            duracion_minutos=100,
            margen_limpieza_minutos=20,
            sala=self.sala,
        )
        self.entrada = Entrada.objects.create(
            sesion=self.sesion,
            movie_id=self.sesion.movie_id,
            titulo_pelicula=self.sesion.titulo_pelicula,
            fecha=self.sesion.fecha,
            hora=self.sesion.hora_inicio_formateada(),
            sala=self.sala,
            asiento="A1",
            usuario=self.usuario,
        )

    def codigo_verificacion(self):
        return f"FICINEMA-{self.entrada.codigo}-{self.usuario.id}"

    def test_verificar_entrada_activa_muestra_entrada_valida(self):
        response = self.client.get(
            reverse("verificar_entrada", args=[self.codigo_verificacion()])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Entrada válida")
        self.assertContains(response, "Película Verificable")
        self.assertTrue(response.context["resultado"]["valida"])

    def test_verificar_entrada_cancelada_muestra_entrada_cancelada(self):
        self.entrada.estado = Entrada.ESTADO_CANCELADA
        self.entrada.save(update_fields=["estado"])

        response = self.client.get(
            reverse("verificar_entrada", args=[self.codigo_verificacion()])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Entrada cancelada")
        self.assertFalse(response.context["resultado"]["valida"])

    def test_verificar_entrada_inexistente_muestra_error(self):
        response = self.client.get(
            reverse("verificar_entrada", args=["FICINEMA-99999-99999"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Entrada no encontrada")
        self.assertIsNone(response.context["entrada"])
        self.assertFalse(response.context["resultado"]["valida"])

    def test_verificar_codigo_mal_formado_muestra_error(self):
        response = self.client.get(
            reverse("verificar_entrada", args=["CODIGO-MAL-FORMADO"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Entrada no encontrada")
        self.assertFalse(response.context["resultado"]["valida"])



class EntradaPDFTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="usuariopdf",
            email="usuariopdf@example.com",
            password="testpass123",
        )
        self.otro_usuario = Usuario.objects.create_user(
            username="otropdf",
            email="otropdf@example.com",
            password="testpass123",
        )
        self.staff = Usuario.objects.create_user(
            username="staffpdf",
            email="staffpdf@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.sala = Sala.objects.create(nombre="Sala PDF", filas=4, columnas=5)
        inicio = timezone.now() + timedelta(days=1)
        self.sesion = SesionCine.objects.create(
            movie_id=7777,
            titulo_pelicula="Película PDF",
            fecha=timezone.localdate() + timedelta(days=1),
            inicio=inicio,
            fin=inicio + timedelta(minutes=140),
            duracion_minutos=120,
            margen_limpieza_minutos=20,
            sala=self.sala,
        )
        self.entrada = Entrada.objects.create(
            sesion=self.sesion,
            movie_id=self.sesion.movie_id,
            titulo_pelicula=self.sesion.titulo_pelicula,
            fecha=self.sesion.fecha,
            hora=self.sesion.hora_inicio_formateada(),
            sala=self.sala,
            asiento="A1",
            usuario=self.usuario,
        )

    def test_usuario_propietario_puede_descargar_pdf(self):
        self.client.login(username="usuariopdf", password="testpass123")

        response = self.client.get(reverse("descargar_entrada_pdf", args=[self.entrada.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn("attachment", response["Content-Disposition"])

    def test_otro_usuario_no_puede_descargar_pdf_ajeno(self):
        self.client.login(username="otropdf", password="testpass123")

        response = self.client.get(reverse("descargar_entrada_pdf", args=[self.entrada.id]))

        self.assertEqual(response.status_code, 403)

    def test_staff_puede_descargar_pdf_de_cualquier_entrada(self):
        self.client.login(username="staffpdf", password="testpass123")

        response = self.client.get(reverse("descargar_entrada_pdf", args=[self.entrada.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_pdf_redirige_si_no_hay_sesion_iniciada(self):
        response = self.client.get(reverse("descargar_entrada_pdf", args=[self.entrada.id]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_pdf_de_entrada_cancelada_se_puede_descargar_como_justificante(self):
        self.entrada.estado = Entrada.ESTADO_CANCELADA
        self.entrada.save(update_fields=["estado"])
        self.client.login(username="usuariopdf", password="testpass123")

        response = self.client.get(reverse("descargar_entrada_pdf", args=[self.entrada.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))



class FavoritosTest(TestCase):

    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="usuariofavoritos",
            email="usuariofavoritos@example.com",
            password="testpass123",
        )
        self.staff = Usuario.objects.create_user(
            username="stafffavoritos",
            email="stafffavoritos@example.com",
            password="testpass123",
            is_staff=True,
        )

    def test_usuario_puede_anadir_pelicula_a_favoritos(self):
        self.client.login(username="usuariofavoritos", password="testpass123")

        response = self.client.post(
            reverse("alternar_favorito"),
            {
                "movie_id": "83533",
                "titulo": "Avatar: Fuego y ceniza",
                "poster_url": "https://image.tmdb.org/t/p/w342/test.jpg",
                "fecha_estreno": "17/12/2025",
                "valoracion": "7.4",
                "next": reverse("index_peliculas"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Favorito.objects.filter(
                usuario=self.usuario,
                movie_id=83533,
            ).exists()
        )

    def test_usuario_puede_quitar_pelicula_de_favoritos(self):
        Favorito.objects.create(
            usuario=self.usuario,
            movie_id=83533,
            titulo="Avatar: Fuego y ceniza",
            poster_url="",
            fecha_estreno="17/12/2025",
            valoracion=7.4,
        )

        self.client.login(username="usuariofavoritos", password="testpass123")

        response = self.client.post(
            reverse("alternar_favorito"),
            {
                "movie_id": "83533",
                "titulo": "Avatar: Fuego y ceniza",
                "next": reverse("mis_favoritos"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Favorito.objects.filter(
                usuario=self.usuario,
                movie_id=83533,
            ).exists()
        )

    def test_mis_favoritos_muestra_favoritos_del_usuario(self):
        Favorito.objects.create(
            usuario=self.usuario,
            movie_id=83533,
            titulo="Avatar: Fuego y ceniza",
            poster_url="",
            fecha_estreno="17/12/2025",
            valoracion=7.4,
        )

        self.client.login(username="usuariofavoritos", password="testpass123")

        response = self.client.get(reverse("mis_favoritos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Avatar: Fuego y ceniza")
        self.assertTemplateUsed(response, "favoritos.html")

    def test_staff_no_puede_gestionar_favoritos_personales(self):
        self.client.login(username="stafffavoritos", password="testpass123")

        response = self.client.post(
            reverse("alternar_favorito"),
            {
                "movie_id": "83533",
                "titulo": "Avatar: Fuego y ceniza",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Favorito.objects.filter(
                usuario=self.staff,
                movie_id=83533,
            ).exists()
        )

class RecomendacionesPersonalizadasTest(TestCase):

    def setUp(self):
        cache.clear()
        self.usuario = Usuario.objects.create_user(
            username="usuariorecomendaciones",
            email="usuariorecomendaciones@example.com",
            password="testpass123",
        )
        self.staff = Usuario.objects.create_user(
            username="staffrecomendaciones",
            email="staffrecomendaciones@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.sala = Sala.objects.create(
            nombre="Sala Recomendaciones",
            filas=5,
            columnas=10,
        )

    def crear_sesion_futura(self, movie_id=9001, titulo="Película recomendada en cartelera"):
        inicio = timezone.now() + timedelta(days=2)
        fin = inicio + timedelta(minutes=140)

        return SesionCine.objects.create(
            movie_id=movie_id,
            titulo_pelicula=titulo,
            fecha=timezone.localdate() + timedelta(days=2),
            inicio=inicio,
            fin=fin,
            duracion_minutos=120,
            margen_limpieza_minutos=20,
            popularidad=80,
            valoracion=8.2,
            fecha_estreno=date(2026, 5, 1),
            demanda_estimada=95,
            sala=self.sala,
        )

    def pelicula_recomendada(self, movie_id, titulo, motivo="Porque guardaste una película"):
        return {
            "id": movie_id,
            "title": titulo,
            "overview": "Sinopsis recomendada de prueba.",
            "poster_url": "https://image.tmdb.org/t/p/w342/poster.jpg",
            "release_date": "2026-05-01",
            "vote_average": 8.0,
            "motivo": motivo,
            "tiene_sesiones": False,
            "sesiones_futuras": 0,
            "texto_disponibilidad": "No disponible en cartelera",
        }

    @patch("FICinema.views.obtener_recomendaciones_para_usuario")
    def test_pagina_recomendaciones_muestra_recomendaciones_del_usuario(self, mock_recomendaciones):
        mock_recomendaciones.return_value = [
            self.pelicula_recomendada(
                9100,
                "Guardianes de la Galaxia Vol. 2",
            )
        ]

        self.client.login(username="usuariorecomendaciones", password="testpass123")

        response = self.client.get(reverse("mis_recomendaciones"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "recomendaciones.html")
        self.assertContains(response, "Recomendadas para ti")
        self.assertContains(response, "Guardianes de la Galaxia Vol. 2")
        self.assertContains(response, "No disponible en cartelera")
        mock_recomendaciones.assert_called_once()

    def test_staff_no_accede_a_recomendaciones_personales(self):
        self.client.login(username="staffrecomendaciones", password="testpass123")

        response = self.client.get(reverse("mis_recomendaciones"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("panel_interno"), response.url)

    @patch("FICinema.views.obtener_recomendaciones_tmdb")
    def test_recomendaciones_para_usuario_excluyen_favoritas_y_compradas(self, mock_tmdb):
        from FICinema import views

        sesion_comprada = self.crear_sesion_futura(
            movie_id=9200,
            titulo="Película ya comprada",
        )

        Favorito.objects.create(
            usuario=self.usuario,
            movie_id=9100,
            titulo="Película ya favorita",
            poster_url="",
            fecha_estreno="2026-05-01",
            valoracion=7.5,
        )

        Entrada.objects.create(
            sesion=sesion_comprada,
            movie_id=9200,
            titulo_pelicula="Película ya comprada",
            fecha=sesion_comprada.fecha,
            hora=sesion_comprada.hora_inicio_formateada(),
            sala=self.sala,
            asiento="A1",
            usuario=self.usuario,
        )

        mock_tmdb.return_value = [
            self.pelicula_recomendada(9100, "Película ya favorita"),
            self.pelicula_recomendada(9200, "Película ya comprada"),
            self.pelicula_recomendada(9300, "Película nueva recomendada"),
        ]

        recomendaciones = views.obtener_recomendaciones_para_usuario(
            self.usuario,
            limite=1,
        )

        ids_recomendados = {pelicula["id"] for pelicula in recomendaciones}

        self.assertEqual(ids_recomendados, {9300})
        self.assertNotIn(9100, ids_recomendados)
        self.assertNotIn(9200, ids_recomendados)

    @patch("FICinema.views.obtener_detalle_tmdb")
    def test_recomendaciones_internas_marcan_peliculas_en_cartelera(self, mock_detalle):
        from FICinema import views

        self.crear_sesion_futura(
            movie_id=9400,
            titulo="Película interna disponible",
        )

        mock_detalle.return_value = {
            "id": 9400,
            "title": "Película interna disponible",
            "overview": "Disponible dentro de la cartelera interna.",
            "poster_path": "/poster-disponible.jpg",
            "release_date": "2026-05-01",
            "vote_average": 8.6,
        }

        recomendaciones = views.obtener_recomendaciones_internas(limite=1)

        self.assertEqual(len(recomendaciones), 1)
        self.assertEqual(recomendaciones[0]["id"], 9400)
        self.assertTrue(recomendaciones[0]["tiene_sesiones"])
        self.assertEqual(recomendaciones[0]["sesiones_futuras"], 1)
        self.assertIn("sesiones", recomendaciones[0]["texto_disponibilidad"])

    @patch("FICinema.views.pelicula_aparece_en_cartelera_actual", return_value=False)
    @patch("FICinema.views.obtener_recomendaciones_para_detalle")
    @patch("FICinema.views.obtener_detalle_tmdb")
    def test_detalle_pelicula_sin_sesiones_no_muestra_compra_como_disponible(
        self,
        mock_detalle,
        mock_recomendaciones,
        _mock_en_cartelera,
    ):
        mock_detalle.return_value = {
            "id": 9500,
            "title": "Película recomendada sin sesiones",
            "overview": "Ficha informativa sin sesiones disponibles.",
            "poster_path": "/poster-sin-sesiones.jpg",
            "release_date": "2026-05-01",
            "runtime": 120,
            "vote_average": 7.1,
            "videos": {"results": []},
        }
        mock_recomendaciones.return_value = [
            self.pelicula_recomendada(9600, "Otra recomendación")
        ]

        self.client.login(username="usuariorecomendaciones", password="testpass123")

        response = self.client.get(reverse("detalle_pelicula", args=[9500]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["tiene_sesiones_disponibles"])
        self.assertFalse(response.context["pelicula_en_cartelera"])
        self.assertEqual(response.context["total_sesiones"], 0)
        self.assertContains(response, "No hay sesiones disponibles")
        self.assertContains(response, "Ver recomendaciones")
        self.assertContains(response, "Películas similares")
        self.assertContains(response, "Otra recomendación")

    @patch("FICinema.views.obtener_recomendaciones_tmdb")
    def test_recomendaciones_de_detalle_excluyen_pelicula_actual_y_favoritas(self, mock_tmdb):
        from FICinema import views

        Favorito.objects.create(
            usuario=self.usuario,
            movie_id=9700,
            titulo="Favorita que no debe repetirse",
            poster_url="",
            fecha_estreno="2026-05-01",
            valoracion=7.5,
        )

        mock_tmdb.return_value = [
            self.pelicula_recomendada(9500, "Película actual"),
            self.pelicula_recomendada(9700, "Favorita que no debe repetirse"),
            self.pelicula_recomendada(9800, "Recomendación válida"),
        ]

        recomendaciones = views.obtener_recomendaciones_para_detalle(
            movie_id=9500,
            usuario=self.usuario,
            limite=1,
        )

        ids_recomendados = {pelicula["id"] for pelicula in recomendaciones}

        self.assertEqual(ids_recomendados, {9800})
        self.assertNotIn(9500, ids_recomendados)
        self.assertNotIn(9700, ids_recomendados)



class FavoritosFeedbackUXTest(TestCase):

    def setUp(self):
        cache.clear()
        self.usuario = Usuario.objects.create_user(
            username="usuariofeedback",
            email="usuariofeedback@example.com",
            password="testpass123",
        )

    def obtener_mensajes_respuesta(self, response):
        from django.contrib.messages import get_messages

        return [str(message) for message in get_messages(response.wsgi_request)]

    def test_favorito_desde_cartelera_no_acumula_mensaje_global(self):
        self.client.login(username="usuariofeedback", password="testpass123")

        response = self.client.post(
            reverse("alternar_favorito"),
            {
                "movie_id": "10001",
                "titulo": "Favorito desde cartelera",
                "poster_url": "https://image.tmdb.org/t/p/w342/cartelera.jpg",
                "fecha_estreno": "2026-05-01",
                "valoracion": "8.1",
                "origen": "cartelera",
                "next": reverse("index_peliculas"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Favorito.objects.filter(
                usuario=self.usuario,
                movie_id=10001,
            ).exists()
        )
        self.assertEqual(self.obtener_mensajes_respuesta(response), [])

    def test_favorito_desde_detalle_muestra_mensaje_de_confirmacion(self):
        self.client.login(username="usuariofeedback", password="testpass123")

        response = self.client.post(
            reverse("alternar_favorito"),
            {
                "movie_id": "10002",
                "titulo": "Favorito desde detalle",
                "poster_url": "https://image.tmdb.org/t/p/w342/detalle.jpg",
                "fecha_estreno": "2026-05-01",
                "valoracion": "8.3",
                "origen": "detalle",
                "next": reverse("detalle_pelicula", args=[10002]),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Favorito.objects.filter(
                usuario=self.usuario,
                movie_id=10002,
            ).exists()
        )
        self.assertIn(
            "Película añadida a favoritos.",
            self.obtener_mensajes_respuesta(response),
        )

    def test_favorito_desde_favoritos_muestra_mensaje_al_quitar(self):
        Favorito.objects.create(
            usuario=self.usuario,
            movie_id=10003,
            titulo="Favorito a quitar",
            poster_url="https://image.tmdb.org/t/p/w342/quitar.jpg",
            fecha_estreno="2026-05-01",
            valoracion=7.9,
        )

        self.client.login(username="usuariofeedback", password="testpass123")

        response = self.client.post(
            reverse("alternar_favorito"),
            {
                "movie_id": "10003",
                "origen": "favoritos",
                "next": reverse("mis_favoritos"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Favorito.objects.filter(
                usuario=self.usuario,
                movie_id=10003,
            ).exists()
        )
        self.assertIn(
            "Película eliminada de favoritos.",
            self.obtener_mensajes_respuesta(response),
        )


class EstadisticasAvanzadasStaffTest(TestCase):

    def setUp(self):
        cache.clear()

        self.staff = Usuario.objects.create_user(
            username="staffstats",
            password="PasswordSeguro12345",
            is_staff=True,
        )

        self.usuario = Usuario.objects.create_user(
            username="clientestats",
            password="PasswordSeguro12345",
            is_staff=False,
        )

        self.otro_usuario = Usuario.objects.create_user(
            username="clientestats2",
            password="PasswordSeguro12345",
            is_staff=False,
        )

        self.sala = Sala.objects.create(
            nombre="Sala Estadísticas",
            filas=2,
            columnas=3,
            activa=True,
        )

        inicio = timezone.now() + timedelta(days=1)

        self.sesion = SesionCine.objects.create(
            movie_id=9001,
            titulo_pelicula="Película Más Comprada",
            fecha=timezone.localdate() + timedelta(days=1),
            inicio=inicio,
            fin=inicio + timedelta(minutes=140),
            duracion_minutos=120,
            margen_limpieza_minutos=20,
            popularidad=90,
            valoracion=8.8,
            demanda_estimada=100,
            sala=self.sala,
        )

    def crear_respuesta_tmdb_vacia(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

    @patch("FICinema.views.requests.get")
    def test_staff_ve_estadisticas_avanzadas_internas(self, mock_get):
        self.crear_respuesta_tmdb_vacia(mock_get)

        Entrada.objects.create(
            sesion=self.sesion,
            asiento="A1",
            usuario=self.usuario,
        )
        Entrada.objects.create(
            sesion=self.sesion,
            asiento="A2",
            usuario=self.usuario,
        )
        Entrada.objects.create(
            sesion=self.sesion,
            asiento="A3",
            usuario=self.otro_usuario,
            estado=Entrada.ESTADO_CANCELADA,
        )

        self.client.force_login(self.staff)

        response = self.client.get(reverse("estadisticas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rendimiento interno de FICinema")
        self.assertContains(response, "Películas más compradas")
        self.assertContains(response, "Salas más usadas")
        self.assertContains(response, "Horas con más ventas")

        avanzadas = response.context["estadisticas_avanzadas"]

        self.assertIsNotNone(avanzadas)
        self.assertEqual(avanzadas["resumen"]["entradas_validas"], 2)
        self.assertEqual(avanzadas["resumen"]["entradas_canceladas"], 1)
        self.assertEqual(avanzadas["resumen"]["sesiones_programadas"], 1)
        self.assertEqual(avanzadas["resumen"]["salas_activas"], 1)
        self.assertEqual(avanzadas["peliculas_mas_compradas"][0]["titulo_pelicula"], "Película Más Comprada")
        self.assertEqual(avanzadas["peliculas_mas_compradas"][0]["total"], 2)
        self.assertEqual(avanzadas["salas_mas_usadas"][0]["sala__nombre"], "Sala Estadísticas")
        self.assertEqual(avanzadas["salas_mas_usadas"][0]["total"], 2)

    @patch("FICinema.views.requests.get")
    def test_usuario_normal_no_ve_estadisticas_avanzadas_staff(self, mock_get):
        self.crear_respuesta_tmdb_vacia(mock_get)

        Entrada.objects.create(
            sesion=self.sesion,
            asiento="B1",
            usuario=self.usuario,
        )

        self.client.force_login(self.usuario)

        response = self.client.get(reverse("estadisticas"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Rendimiento interno de FICinema")
        self.assertNotContains(response, "Usuarios con más entradas")
        self.assertIsNone(response.context["estadisticas_avanzadas"])

    @patch("FICinema.views.requests.get")
    def test_estadisticas_avanzadas_calculan_bonos_y_usuarios_activos(self, mock_get):
        self.crear_respuesta_tmdb_vacia(mock_get)

        bono = Bono.objects.create(
            tipo="5 EN 3",
            fechaCaducidad=date.today() + timedelta(days=30),
            usuario=self.usuario,
        )

        Entrada.objects.create(
            sesion=self.sesion,
            asiento="A1",
            usuario=self.usuario,
            bono_usado=bono,
        )
        Entrada.objects.create(
            sesion=self.sesion,
            asiento="A2",
            usuario=self.usuario,
        )

        self.client.force_login(self.staff)

        response = self.client.get(reverse("estadisticas"))
        avanzadas = response.context["estadisticas_avanzadas"]

        self.assertEqual(avanzadas["usuarios_mas_activos"][0]["usuario__username"], "clientestats")
        self.assertEqual(avanzadas["usuarios_mas_activos"][0]["total"], 2)
        self.assertEqual(avanzadas["bonos_mas_usados"][0]["bono_usado__tipo"], "5 EN 3")
        self.assertEqual(avanzadas["bonos_mas_usados"][0]["total"], 1)

    @patch("FICinema.views.requests.get")
    def test_estadisticas_avanzadas_no_rompen_sin_datos_internos(self, mock_get):
        self.crear_respuesta_tmdb_vacia(mock_get)

        SesionCine.objects.all().delete()
        Sala.objects.all().delete()
        Entrada.objects.all().delete()

        self.client.force_login(self.staff)

        response = self.client.get(reverse("estadisticas"))
        avanzadas = response.context["estadisticas_avanzadas"]

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rendimiento interno de FICinema")
        self.assertEqual(avanzadas["resumen"]["entradas_validas"], 0)
        self.assertEqual(avanzadas["resumen"]["ocupacion_global"], 0)
        self.assertEqual(avanzadas["peliculas_mas_compradas"], [])
        self.assertEqual(avanzadas["ocupacion_por_sala"], [])

    def test_staff_puede_exportar_estadisticas_csv(self):
        Entrada.objects.create(
            sesion=self.sesion,
            asiento="A1",
            usuario=self.usuario,
        )
        Entrada.objects.create(
            sesion=self.sesion,
            asiento="A2",
            usuario=self.usuario,
        )

        self.client.force_login(self.staff)

        response = self.client.get(reverse("exportar_estadisticas_csv"))
        contenido = response.content.decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("estadisticas_ficinema_", response["Content-Disposition"])
        self.assertIn("Sección;Indicador;Valor;Detalle", contenido)
        self.assertIn("Resumen interno;Entradas válidas;2;", contenido)
        self.assertIn("Películas más compradas;Película Más Comprada;2;TMDB ID: 9001", contenido)
        self.assertIn("Salas más usadas;Sala Estadísticas;2;Entradas válidas asociadas a la sala", contenido)
        self.assertIn("Ocupación por sala;Sala Estadísticas;", contenido)

    def test_usuario_normal_no_puede_exportar_estadisticas_csv(self):
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("exportar_estadisticas_csv"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("index_peliculas"))

    def test_staff_puede_exportar_estadisticas_pdf(self):
        Entrada.objects.create(
            sesion=self.sesion,
            asiento="A1",
            usuario=self.usuario,
        )

        self.client.force_login(self.staff)

        response = self.client.get(reverse("exportar_estadisticas_pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("estadisticas_ficinema_", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_usuario_normal_no_puede_exportar_estadisticas_pdf(self):
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("exportar_estadisticas_pdf"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("index_peliculas"))

    @patch("FICinema.views.requests.get")
    def test_estadisticas_muestra_boton_exportar_csv_solo_staff(self, mock_get):
        self.crear_respuesta_tmdb_vacia(mock_get)

        self.client.force_login(self.staff)
        response_staff = self.client.get(reverse("estadisticas"))

        self.assertEqual(response_staff.status_code, 200)
        self.assertContains(response_staff, "Exportar CSV")
        self.assertContains(response_staff, "Descargar PDF")
        self.assertContains(response_staff, reverse("exportar_estadisticas_csv"))
        self.assertContains(response_staff, reverse("exportar_estadisticas_pdf"))

        self.client.logout()
        self.client.force_login(self.usuario)
        response_usuario = self.client.get(reverse("estadisticas"))

        self.assertEqual(response_usuario.status_code, 200)
        self.assertNotContains(response_usuario, "Exportar CSV")
        self.assertNotContains(response_usuario, "Descargar PDF")



class FinalDeliveryRegressionTest(TestCase):

    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="cliente",
            password="PasswordSeguro12345",
        )
        self.staff = Usuario.objects.create_user(
            username="staff",
            password="PasswordSeguro12345",
            is_staff=True,
        )
        self.sala = Sala.objects.create(nombre="Sala Test", filas=2, columnas=3)
        self.sesion_futura = SesionCine.objects.create(
            movie_id=100,
            titulo_pelicula="Película futura",
            fecha=timezone.localdate() + timedelta(days=2),
            inicio=timezone.now() + timedelta(days=2),
            fin=timezone.now() + timedelta(days=2, hours=2),
            duracion_minutos=100,
            sala=self.sala,
        )
        self.sesion_pasada = SesionCine.objects.create(
            movie_id=101,
            titulo_pelicula="Película pasada",
            fecha=timezone.localdate() - timedelta(days=2),
            inicio=timezone.now() - timedelta(days=2, hours=2),
            fin=timezone.now() - timedelta(days=2),
            duracion_minutos=100,
            sala=self.sala,
        )

    def test_entrada_futura_aparece_como_activa(self):
        self.client.force_login(self.usuario)
        Entrada.objects.create(
            usuario=self.usuario,
            sesion=self.sesion_futura,
            asiento="A1",
            movie_id=self.sesion_futura.movie_id,
            titulo_pelicula=self.sesion_futura.titulo_pelicula,
            fecha=self.sesion_futura.fecha,
            hora=self.sesion_futura.hora_inicio_formateada(),
            sala=self.sala,
            estado=Entrada.ESTADO_ACTIVA,
        )

        response = self.client.get(reverse("mis_entradas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Película futura")
        self.assertContains(response, "Entradas activas")

    def test_entrada_pasada_se_muestra_en_historial(self):
        self.client.force_login(self.usuario)
        Entrada.objects.create(
            usuario=self.usuario,
            sesion=self.sesion_pasada,
            asiento="A2",
            movie_id=self.sesion_pasada.movie_id,
            titulo_pelicula=self.sesion_pasada.titulo_pelicula,
            fecha=self.sesion_pasada.fecha,
            hora=self.sesion_pasada.hora_inicio_formateada(),
            sala=self.sala,
            estado=Entrada.ESTADO_ACTIVA,
        )

        response = self.client.get(reverse("mis_entradas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historial de entradas")
        self.assertContains(response, "Película pasada")

    def test_qr_usado_no_puede_validarse_dos_veces(self):
        self.client.force_login(self.staff)
        entrada = Entrada.objects.create(
            usuario=self.usuario,
            sesion=self.sesion_futura,
            asiento="A3",
            movie_id=self.sesion_futura.movie_id,
            titulo_pelicula=self.sesion_futura.titulo_pelicula,
            fecha=self.sesion_futura.fecha,
            hora=self.sesion_futura.hora_inicio_formateada(),
            sala=self.sala,
            estado=Entrada.ESTADO_ACTIVA,
        )
        codigo = f"FICINEMA-{entrada.codigo}-{self.usuario.codigo}"

        primera = self.client.post(reverse("verificar_entrada", args=[codigo]), follow=True)
        entrada.refresh_from_db()
        segunda = self.client.post(reverse("verificar_entrada", args=[codigo]), follow=True)

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(entrada.estado, Entrada.ESTADO_USADA)
        self.assertContains(segunda, "Entrada ya consta como usada")

    def test_staff_puede_entrar_a_estadisticas_con_pandas(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("estadisticas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rendimiento interno de FICinema")


class ResenasYFiltrosViewTest(TestCase):

    def setUp(self):
        cache.clear()
        self.usuario = Usuario.objects.create_user(
            username="pepa",
            password="PasswordSeguro12345",
        )
        self.staff = Usuario.objects.create_user(
            username="staff",
            password="PasswordSeguro12345",
            is_staff=True,
        )

    @patch("FICinema.views.requests.get")
    def test_cartelera_filtra_por_valoracion_minima(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 101,
                    "title": "Pelicula Baja",
                    "release_date": "2024-01-01",
                    "vote_average": 5.0,
                    "poster_path": "/baja.jpg",
                    "overview": "Sinopsis baja",
                },
                {
                    "id": 102,
                    "title": "Pelicula Alta",
                    "release_date": "2024-01-02",
                    "vote_average": 8.0,
                    "poster_path": "/alta.jpg",
                    "overview": "Sinopsis alta",
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(
            reverse("index_peliculas"),
            {"valoracion_minima": "7"},
        )

        self.assertEqual(response.status_code, 200)
        titulos = [pelicula["title"] for pelicula in response.context["peliculas"]]
        self.assertIn("Pelicula Alta", titulos)
        self.assertNotIn("Pelicula Baja", titulos)


    @patch("FICinema.views.requests.get")
    def test_index_peliculas_ordena_por_valoracion_usuarios(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 201,
                    "title": "Sin reseñas",
                    "release_date": "2024-01-01",
                    "vote_average": 8.0,
                    "poster_path": "/sin.jpg",
                    "overview": "Sinopsis sin reseñas",
                },
                {
                    "id": 202,
                    "title": "Mejor para usuarios",
                    "release_date": "2024-01-02",
                    "vote_average": 6.0,
                    "poster_path": "/mejor.jpg",
                    "overview": "Sinopsis con reseñas",
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        Resena.objects.create(
            usuario=self.usuario,
            movie_id=202,
            titulo_pelicula="Mejor para usuarios",
            puntuacion=5,
            comentario="Excelente",
        )

        response = self.client.get(
            reverse("index_peliculas"),
            {"ordenar_por": "Valoración usuarios"},
        )

        self.assertEqual(response.status_code, 200)
        peliculas = response.context["peliculas"]
        self.assertEqual(peliculas[0]["title"], "Mejor para usuarios")

    @patch("FICinema.views.obtener_calificacion_edad_pelicula", return_value="Sin clasificar")
    @patch("FICinema.views.requests.get")
    def test_cartelera_filtra_por_edad_sin_clasificar(self, mock_get, _mock_calificacion):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 301,
                    "title": "Sin edad",
                    "release_date": "2024-01-01",
                    "vote_average": 7.0,
                    "poster_path": "/edad.jpg",
                    "overview": "Sinopsis",
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get(
            reverse("index_peliculas"),
            {"edad": "Sin clasificar"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edad sin clasificar")

    def test_usuario_puede_crear_y_actualizar_resena(self):
        self.client.force_login(self.usuario)

        with patch("FICinema.views.obtener_detalle_tmdb") as mock_detalle:
            mock_detalle.return_value = {"title": "Pelicula Reseñada"}
            response = self.client.post(
                reverse("guardar_resena", args=[123]),
                {"puntuacion": "4", "comentario": "Muy buena"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Resena.objects.filter(usuario=self.usuario, movie_id=123).exists())

        with patch("FICinema.views.obtener_detalle_tmdb") as mock_detalle:
            mock_detalle.return_value = {"title": "Pelicula Reseñada"}
            self.client.post(
                reverse("guardar_resena", args=[123]),
                {"puntuacion": "5", "comentario": "Mejor de lo esperado"},
            )

        self.assertEqual(Resena.objects.filter(usuario=self.usuario, movie_id=123).count(), 1)
        resena = Resena.objects.get(usuario=self.usuario, movie_id=123)
        self.assertEqual(resena.puntuacion, 5)
        self.assertEqual(resena.comentario, "Mejor de lo esperado")

    def test_staff_puede_ocultar_y_mostrar_resena(self):
        resena = Resena.objects.create(
            usuario=self.usuario,
            movie_id=123,
            titulo_pelicula="Pelicula Reseñada",
            puntuacion=4,
            comentario="Correcta",
        )
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("cambiar_visibilidad_resena", args=[resena.id]),
            {"accion": "ocultar"},
        )
        self.assertEqual(response.status_code, 302)
        resena.refresh_from_db()
        self.assertFalse(resena.visible)

        response = self.client.post(
            reverse("cambiar_visibilidad_resena", args=[resena.id]),
            {"accion": "mostrar"},
        )
        self.assertEqual(response.status_code, 302)
        resena.refresh_from_db()
        self.assertTrue(resena.visible)

    def test_staff_puede_exportar_estadisticas_csv(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("exportar_estadisticas_csv"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])


class DeploymentReadinessTest(TestCase):

    def test_healthz_devuelve_ok(self):
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

    def test_estado_sistema_requiere_staff(self):
        usuario = Usuario.objects.create_user(
            username="cliente_estado",
            password="test12345"
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("panel_estado_sistema"))

        self.assertRedirects(response, reverse("index_peliculas"))

    def test_estado_sistema_accesible_para_staff(self):
        staff = Usuario.objects.create_user(
            username="staff_estado",
            password="test12345",
            is_staff=True
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("panel_estado_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Estado del sistema")
        self.assertContains(response, "PUBLIC_BASE_URL")

    @override_settings(EMAIL_TEST_RECIPIENT_OVERRIDE="ficinema.notificaciones@gmail.com")
    def test_email_demo_permite_destinatario_sin_correo_de_usuario(self):
        usuario = Usuario.objects.create_user(
            username="sin_email_demo",
            password="test12345",
            email=""
        )

        self.assertTrue(views.hay_destinatario_correo(usuario))
        self.assertIn("modo demo", views.mensaje_envio_correo_demo("entradas").lower())


class BusquedaGlobalCarteleraTest(TestCase):

    def setUp(self):
        cache.clear()

    @patch("FICinema.views.obtener_detalle_tmdb")
    @patch("FICinema.views.requests.get")
    def test_busqueda_global_prepara_peliculas_fuera_de_cartelera(self, mock_get, mock_detalle):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 321,
                    "title": "Interestelar",
                    "overview": "Viaje espacial",
                    "release_date": "2014-11-07",
                    "vote_average": 8.7,
                    "poster_path": "/poster.jpg",
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        mock_detalle.return_value = {
            "id": 321,
            "title": "Interestelar",
            "overview": "Viaje espacial",
            "release_date": "2014-11-07",
            "vote_average": 8.7,
            "poster_path": "/poster.jpg",
        }

        resultados = views.obtener_peliculas_busqueda_global_tmdb("Interestelar")

        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["id"], 321)
        self.assertTrue(resultados[0]["resultado_busqueda_global"])
        self.assertFalse(resultados[0]["en_cartelera_principal"])
        self.assertEqual(resultados[0]["sesiones_futuras"], 0)

    @patch("FICinema.views.requests.get")
    def test_busqueda_global_ignora_ids_ya_programados(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 999,
                    "title": "Ya programada",
                    "overview": "Duplicada",
                    "release_date": "2026-01-01",
                    "vote_average": 7.0,
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        resultados = views.obtener_peliculas_busqueda_global_tmdb(
            "Ya programada",
            excluir_ids={999},
        )

        self.assertEqual(resultados, [])


class ValidacionPagoSimuladoTest(TestCase):

    def test_titular_pago_acepta_letras_espacios_y_acentos(self):
        valido, error = views.validar_titular_pago("Ángel Villamor-Martínez")

        self.assertTrue(valido)
        self.assertEqual(error, "")

    def test_titular_pago_rechaza_numeros(self):
        valido, error = views.validar_titular_pago("Angel 123")

        self.assertFalse(valido)
        self.assertIn("números", error)

    def test_titular_pago_rechaza_caracteres_no_permitidos(self):
        valido, error = views.validar_titular_pago("Angel @@@")

        self.assertFalse(valido)
        self.assertIn("solo puede contener", error)


class AsientosCanceladosDisponiblesTest(TestCase):

    def test_asiento_cancelado_vuelve_a_quedar_disponible(self):
        usuario = Usuario.objects.create_user(
            username="angel_cancelacion",
            password="PasswordSeguro12345",
        )
        otro_usuario = Usuario.objects.create_user(
            username="lucas_cancelacion",
            password="PasswordSeguro12345",
        )
        sala = Sala.objects.create(
            nombre="Sala Cancelacion",
            filas=5,
            columnas=5,
            activa=True,
        )
        inicio = timezone.make_aware(
            timezone.datetime.combine(
                date.today() + timedelta(days=1),
                time(20, 0),
            )
        )
        sesion = SesionCine.objects.create(
            movie_id=2222,
            titulo_pelicula="Prueba cancelación",
            fecha=date.today() + timedelta(days=1),
            inicio=inicio,
            fin=inicio + timedelta(minutes=140),
            duracion_minutos=120,
            margen_limpieza_minutos=20,
            sala=sala,
        )

        entrada = Entrada.objects.create(
            sesion=sesion,
            movie_id=sesion.movie_id,
            titulo_pelicula=sesion.titulo_pelicula,
            fecha=sesion.fecha,
            hora=sesion.hora_inicio_formateada(),
            sala=sala,
            asiento="A1",
            usuario=usuario,
        )

        entrada.cancelar_y_devolver_bono()

        nueva_entrada = Entrada.objects.create(
            sesion=sesion,
            movie_id=sesion.movie_id,
            titulo_pelicula=sesion.titulo_pelicula,
            fecha=sesion.fecha,
            hora=sesion.hora_inicio_formateada(),
            sala=sala,
            asiento="A1",
            usuario=otro_usuario,
        )

        self.assertEqual(entrada.estado, Entrada.ESTADO_CANCELADA)
        self.assertEqual(nueva_entrada.asiento, "A1")
        self.assertEqual(nueva_entrada.estado, Entrada.ESTADO_ACTIVA)
