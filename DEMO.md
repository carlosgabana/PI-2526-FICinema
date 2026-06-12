# Guía rápida de defensa de FICinema

Esta guía resume el recorrido recomendado para demostrar la práctica sin depender de pasos improvisados.

## Comprobación inicial

```bash
python manage.py check
python manage.py test
```

Con Docker:

```bash
docker compose up --build
```

La ruta rápida de salud es:

```text
/healthz/
```

## Recorrido funcional

1. Abrir la aplicación. En Render: `https://ficinema.onrender.com`.
2. Entrar en la cartelera y mostrar que se cargan películas externas.
3. Abrir una ficha de película y enseñar detalle, tráiler, sesiones y asientos.
4. Registrarse o iniciar sesión con un usuario normal.
5. Añadir una película a favoritos.
6. Entrar en recomendaciones y explicar que se basan en favoritos, compras y cartelera disponible.
7. Comprar una entrada con pago simulado.
8. Comprobar que la entrada aparece en “Mis entradas”.
9. Descargar el PDF de la entrada y mostrar el QR.
10. Entrar con un usuario staff.
11. Ir al panel interno y abrir el control QR.
12. Validar la entrada y comprobar que queda marcada como usada.
13. Mostrar estadísticas internas y exportación CSV/PDF.
14. Mostrar el panel de estado del sistema.

## Correo

En local con Gmail SMTP se puede enviar el correo al email real del usuario registrado. En Render, si se usa Resend con `onboarding@resend.dev` y sin dominio propio verificado, el envío se centraliza en:

```text
ficinema.notificaciones@gmail.com
```

Esto se configura con:

```env
EMAIL_TEST_RECIPIENT_OVERRIDE=ficinema.notificaciones@gmail.com
```

La compra no depende del correo: la entrada se genera y queda disponible en la aplicación aunque el proveedor de email falle.

No se deben publicar contraseñas, API keys ni accesos privados en el README ni en Git. Para demostrar el correo, se puede enseñar la bandeja durante la defensa, una captura o los logs del proveedor.

## QR según entorno

En Render el QR es el caso más estable porque usa una URL pública:

```env
PUBLIC_BASE_URL=https://ficinema.onrender.com
```

En local o Docker, `PUBLIC_BASE_URL=http://127.0.0.1:8000` funciona desde el mismo ordenador. Para escanear el QR desde un móvil, cada persona debe cambiarlo por la IP local de su ordenador:

```env
PUBLIC_BASE_URL=http://192.168.1.X:8000
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,192.168.1.X
CSRF_TRUSTED_ORIGINS=http://192.168.1.X:8000
```

No se deja una IP fija porque depende de la red y del equipo de quien ejecute la aplicación.
