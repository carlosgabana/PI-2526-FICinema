# FICinema

Aplicación web de cine desarrollada con **Django** para la práctica final de **Programación Integrativa**.

FICinema permite consultar una cartelera de películas, ver la ficha detallada de cada película, comprar entradas de forma simulada, gestionar bonos, consultar entradas digitales con código QR verificable, guardar favoritos, recibir recomendaciones y acceder a un panel interno para usuarios staff con métricas y exportaciones.

La aplicación utiliza información externa de **TMDB** para obtener datos de películas, pósteres, valoraciones, sinopsis y tráileres. Además, combina esos datos con información interna del sistema, como entradas compradas, sesiones, salas, bonos y actividad de usuario.

---

## Integrantes del grupo

- Ángel Villamor Martínez - angel.villamor.martinez@udc.es
- Lucas García-Boente Rivera - l.garcia-boenter@udc.es
- Carlos Gabana Becerra - carlos.gabana@udc.es

---

## Estado actual del proyecto

El proyecto incluye actualmente:

- Cartelera conectada con TMDB.
- Detalle de películas con póster, sinopsis, valoración, duración y tráiler.
- Registro, inicio y cierre de sesión.
- Perfil de usuario editable.
- Alta y baja como socio.
- Compra simulada de entradas.
- Selección visual de fecha, sesión y asiento.
- Control de asientos ocupados.
- Compra simulada de bonos.
- Uso de bonos en la compra de entradas.
- Página de “Mis entradas”.
- Entrada digital con código QR.
- Verificación real de entradas mediante URL.
- Exportación de entradas a PDF.
- Cancelación de entradas activas.
- Historial de entradas.
- Favoritos.
- Recomendaciones personalizadas.
- Página específica de recomendaciones.
- Tendencias de cartelera.
- Panel interno para staff.
- Gestión interna de sesiones.
- Gestión interna de entradas.
- Gestión interna de usuarios.
- Gestión interna de bonos.
- Estadísticas internas avanzadas.
- Exportación de estadísticas a CSV.
- Exportación de estadísticas a PDF.
- Interfaz responsive para móvil, tablet y escritorio.
- Adaptación a distintas orientaciones y niveles de zoom.
- Mejoras de accesibilidad.
- Skeleton loading y animaciones suaves.
- Tests automatizados.
- Configuración con Docker, Docker Compose y Dev Container.
- Workflow de GitHub Actions preparado para integración continua.

---

## Funcionalidades principales

### Cartelera

La cartelera muestra películas obtenidas desde la API de TMDB. Para cada película se muestra:

- Título.
- Póster.
- Fecha de estreno.
- Valoración.
- Sinopsis resumida.
- Botón para acceder a la compra de entradas.
- Botón de favoritos para usuarios autenticados.

La cartelera permite ordenar las películas por:

- Título.
- Fecha de lanzamiento.
- Valoración.

---

### Detalle de película

Cada película cuenta con una ficha detallada que muestra:

- Título.
- Póster.
- Fecha de estreno.
- Duración.
- Valoración.
- Sinopsis completa.
- Tráiler oficial cuando está disponible.
- Número de sesiones disponibles.
- Número de entradas vendidas.
- Ocupación media.
- Selección de fecha.
- Selección de sesión.
- Selección visual de asiento.
- Botón de compra.
- Botón de favoritos.
- Películas similares o relacionadas.

Si una película similar no forma parte de la cartelera actual, se permite ver su ficha y guardarla como favorita, pero la compra solo aparece cuando existen sesiones reales disponibles.

---

### Registro, login y perfil

La aplicación permite:

- Registro de nuevos usuarios.
- Inicio de sesión.
- Cierre de sesión.
- Consulta de perfil.
- Edición de datos personales.
- Alta como socio.
- Baja como socio.
- Acceso a entradas compradas.
- Acceso a bonos comprados.
- Acceso a favoritos y recomendaciones.

El formulario de registro incluye validaciones para:

- Nombre de usuario obligatorio.
- Nombre de usuario duplicado.
- Email duplicado.
- Formato de email.
- Fecha de nacimiento no futura.
- Coincidencia de contraseñas.
- Seguridad de contraseña.

Además, las validaciones importantes también se realizan en backend.

---

### Socios y bonos

Los usuarios pueden hacerse socios desde su perfil.

Los usuarios socios pueden:

- Comprar bonos.
- Consultar sus bonos.
- Usar bonos disponibles al comprar entradas.
- Conservar los bonos comprados aunque se den de baja como socios.

Los usuarios no socios pueden ver la página de bonos, pero no pueden completar la compra hasta hacerse socios.

Tipos de bonos implementados:

- Bono 5 EN 3.
- Bono 10 EN 5.
- Bono 20 EN 10.

La compra de bonos es simulada y no utiliza pasarela de pago real.

---

### Compra de entradas

El flujo de compra de entradas es:

1. El usuario entra en la cartelera.
2. Selecciona una película.
3. Accede a la ficha detallada.
4. Selecciona una fecha.
5. Selecciona una sesión.
6. Selecciona un asiento disponible.
7. Puede escoger usar un bono si tiene uno válido.
8. Confirma la compra.
9. La entrada queda asociada a su cuenta.
10. Puede consultarla desde “Mis entradas”.

Cada entrada almacena:

- Código interno.
- Código QR público.
- Usuario asociado.
- Película.
- Fecha.
- Hora de inicio.
- Hora aproximada de fin.
- Duración.
- Sala.
- Asiento.
- Estado.
- Bono utilizado, si corresponde.
- Fecha de compra.

Estados contemplados:

- Activa.
- Usada.
- Caducada.
- Cancelada.

---

### Entrada digital con QR verificable

Cada entrada activa dispone de un código QR de acceso.

El QR apunta a una URL de verificación con este formato:

```txt
/entrada/verificar/FICINEMA-<id>-<usuario>/
```

La página de verificación permite comprobar si la entrada:

- Existe.
- Está activa.
- Está cancelada.
- Está caducada.
- Está usada.

Si la entrada no está activa, no se muestra QR activo y se informa de que se conserva únicamente como justificante histórico.

Esto permite simular un sistema real de validación de entradas en la sala.

---

### Exportación de entradas a PDF

Cada entrada puede descargarse como PDF.

El PDF incluye:

- Logo de FICinema.
- Código de entrada.
- Película.
- Fecha.
- Hora.
- Duración.
- Sala.
- Asiento.
- Estado.
- Cliente.
- Bono usado, si procede.
- Fecha de compra.
- QR verificable si la entrada está activa.
- Aviso de entrada no válida si está cancelada, usada o caducada.

---

### Favoritos

Los usuarios autenticados pueden guardar películas como favoritas.

La funcionalidad permite:

- Añadir películas a favoritos.
- Quitar películas de favoritos.
- Ver la lista de favoritos desde una página propia.
- Consultar si una película favorita está actualmente en cartelera.
- Acceder a sus sesiones si hay sesiones reales disponibles.
- Ver detalles si no está disponible en cartelera.

Los favoritos se integran con el sistema de recomendaciones.

---

### Recomendaciones

FICinema incluye una página específica de recomendaciones personalizadas.

Las recomendaciones se calculan combinando:

- Favoritos del usuario.
- Entradas compradas.
- Películas de la cartelera actual.
- Datos externos de TMDB.
- Disponibilidad real de sesiones.

La aplicación diferencia entre:

- Películas disponibles en cartelera.
- Películas no disponibles en cartelera.

Si una película recomendada tiene sesiones reales, aparece la opción de ver sesiones. Si no tiene sesiones, el usuario puede ver detalles o guardarla como favorita para más adelante.

Esta funcionalidad permite defender que la aplicación personaliza la experiencia a partir de la actividad interna del usuario.

---

### Tendencias de cartelera

La página de tendencias muestra información calculada sobre la cartelera cargada desde TMDB:

- Número de películas cargadas.
- Valoración media.
- Películas con sinopsis.
- Películas sin sinopsis.
- Películas con póster.
- Películas sin póster.
- Película mejor valorada.
- Película peor valorada.
- Distribución de películas por año de estreno.

Esta funcionalidad se apoya en Pandas para procesar los datos.

---

## Panel interno para staff

Los usuarios staff tienen acceso a un panel interno de administración funcional.

El panel interno permite consultar:

- Resumen general.
- Gestión de sesiones.
- Gestión de entradas.
- Gestión de usuarios.
- Gestión de bonos.
- Estadísticas internas.

El acceso está restringido a usuarios con `request.user.is_staff`.

---

### Gestión interna de sesiones

El staff puede consultar sesiones:

- Próximas.
- De hoy.
- Pasadas.

Para cada sesión se muestra:

- Película.
- Fecha.
- Horario.
- Sala.
- Capacidad.
- Entradas vendidas.
- Ocupación.

También se muestran métricas globales como:

- Número de sesiones.
- Entradas vendidas.
- Capacidad total.
- Ocupación media.

---

### Gestión interna de entradas

El staff puede consultar entradas filtradas por estado:

- Todas.
- Activas.
- Usadas.
- Caducadas.
- Canceladas.

Desde esta vista se puede:

- Ver información completa de cada entrada.
- Verificar una entrada.
- Descargar su PDF.
- Cancelar entradas activas.
- Ver si tiene bono asociado.

---

### Gestión interna de usuarios

El staff puede consultar usuarios y filtrar por:

- Todos.
- Socios.
- Clientes.
- Staff.

Para cada usuario se muestra:

- Código.
- Usuario.
- Email.
- Tipo.
- Si es socio.
- Número de entradas.
- Número de bonos.

---

### Gestión interna de bonos

El staff puede consultar bonos por estado:

- Activos.
- Agotados.
- Caducados.
- Todos.

Para cada bono se muestra:

- Código.
- Usuario.
- Tipo.
- Usos restantes.
- Caducidad.
- Estado.

Los bonos agotados o caducados no se muestran al cliente como disponibles, pero se conservan internamente para control y estadísticas.

---

### Estadísticas internas

La página de estadísticas internas muestra métricas calculadas a partir de datos reales de la aplicación:

- Entradas válidas.
- Ocupación global.
- Sesiones programadas.
- Salas activas.
- Entradas activas.
- Entradas usadas.
- Entradas caducadas.
- Entradas canceladas.
- Sesiones futuras.
- Sesiones pasadas.
- Películas más compradas.
- Salas más usadas.
- Horas con más ventas.
- Usuarios con más entradas.
- Bonos más usados.
- Ocupación por sala.

En esta sección, “entradas válidas” se refiere a entradas no canceladas, incluyendo entradas activas, usadas o caducadas.

---

### Exportación de estadísticas

El staff puede exportar las estadísticas internas en dos formatos:

#### CSV

El CSV está pensado para abrirse en Excel, LibreOffice o herramientas de análisis externo.

Incluye secciones como:

- Resumen interno.
- Películas más compradas.
- Salas más usadas.
- Horas con más ventas.
- Usuarios con más entradas.
- Bonos más usados.
- Ocupación por sala.

#### PDF

El PDF funciona como informe interno del cine.

Incluye:

- Resumen general.
- Nota explicativa de métricas.
- Rankings internos.
- Ocupación por sala.
- Datos de actividad real de la aplicación.

---

## Responsive y experiencia de usuario

La interfaz se ha revisado para adaptarse a:

- Escritorio.
- Portátiles.
- Tablets.
- Móviles.
- Orientación horizontal.
- Orientación vertical.
- Zoom alto del navegador.

Se han mejorado especialmente:

- Cartelera.
- Detalle de película.
- Selección de asiento.
- Mis entradas.
- Historial de entradas.
- Favoritos.
- Recomendaciones.
- Panel staff.
- Tablas internas.
- Estadísticas.
- Bonos.
- PDFs y enlaces de descarga.

También se han añadido detalles de interfaz como:

- Animaciones suaves.
- Hover en cards y botones.
- Skeleton loading durante la carga.
- Menú responsive.
- Estados visuales para botones.
- Diseño oscuro coherente.

---

## Accesibilidad

Se han añadido mejoras de accesibilidad para facilitar el uso de la aplicación:

- Enlace “Saltar al contenido principal”.
- Uso de `main` con identificador para navegación.
- `aria-label` en botones importantes.
- `aria-current` en enlaces activos.
- Mensajes con `role="alert"` o `role="status"`.
- Textos alternativos en imágenes.
- Focus visible para navegación con teclado.
- Compatibilidad con `prefers-reduced-motion`.
- Botones y enlaces más descriptivos.

Estas mejoras permiten que la aplicación sea más usable mediante teclado y tecnologías de asistencia.

---

## API externa utilizada

La aplicación utiliza la API de **TMDB** para obtener información de películas.

Se usa para:

- Obtener películas populares.
- Obtener detalles de una película.
- Obtener pósteres.
- Obtener valoraciones.
- Obtener fechas de estreno.
- Obtener sinopsis.
- Obtener vídeos asociados.
- Obtener tráileres.
- Obtener películas similares o relacionadas.

Algunas películas pueden no tener sinopsis, póster, duración o tráiler porque la API no siempre proporciona esos datos. En esos casos, la aplicación muestra valores alternativos como:

- `Sin sinopsis disponible.`
- `Sin imagen`
- `Sin vídeo disponible`
- Duración por defecto si no se recibe duración válida.

---

## Uso de Pandas

Pandas se utiliza para procesar los datos recibidos desde TMDB.

Actualmente se usa para:

- Crear un DataFrame con las películas recibidas.
- Convertir fechas de estreno a formato fecha.
- Eliminar películas con fechas inválidas.
- Filtrar películas según fecha de estreno.
- Ordenar películas por título.
- Ordenar películas por fecha de lanzamiento.
- Ordenar películas por valoración.
- Rellenar valores vacíos de título, sinopsis y valoración.
- Calcular estadísticas de cartelera.
- Calcular valoración media.
- Calcular películas con y sin sinopsis.
- Calcular películas con y sin póster.
- Obtener la película mejor valorada.
- Obtener la película peor valorada.
- Agrupar películas por año de estreno.

---

## Tecnologías utilizadas

- Python.
- Django.
- Pandas.
- Requests.
- ReportLab.
- qrcode.
- Pillow.
- HTML.
- CSS.
- JavaScript.
- Docker.
- Docker Compose.
- Dev Containers.
- TMDB API.
- SQLite.
- Git.
- GitHub.

---

## Requisitos previos

Para ejecutar la aplicación en local es necesario tener instalado:

- Python 3.12 o superior.
- pip.
- Git.
- Una clave de API de TMDB.

Django 6.0 se soporta oficialmente en Python 3.12, 3.13 y 3.14. Si se usa una versión anterior de Python, la instalación de dependencias puede fallar.

Para ejecutarla con Docker es necesario tener instalado:

- Docker.
- Docker Compose.

Opcionalmente, para trabajar dentro de un entorno reproducible en Visual Studio Code:

- Visual Studio Code.
- Extensión Dev Containers.

---

## Variables de entorno

El proyecto utiliza un archivo `.env` para guardar claves privadas y variables de configuración.

El archivo `.env` no se sube al repositorio por seguridad.

Para crear el archivo de entorno, copiar el archivo de ejemplo:

```bash
cp .env.example .env
```

En Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Variables habituales:

```env
SECRET_KEY=django-insecure-local-key
DEBUG=True
TMDB_API_KEY=tu_api_key_de_tmdb
TMDB_ACCESS_TOKEN=tu_token_de_tmdb_si_se_usa
```

No se deben subir claves reales al repositorio.

---

## Ejecución en local

Clonar el repositorio:

```bash
git clone <url-del-repositorio>
cd pi2526-leedzeppelin
```

Crear y activar entorno virtual:

```bash
python -m venv .venv
source .venv/bin/activate
```

En Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instalar dependencias:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Aplicar migraciones:

```bash
python manage.py migrate
```

Ejecutar servidor:

```bash
python manage.py runserver
```

Abrir en el navegador:

```txt
http://127.0.0.1:8000/
```

---

## Ejecución con Docker

Construir y levantar los contenedores:

```bash
docker compose up --build
```

Ejecutar migraciones dentro del contenedor:

```bash
docker compose run --rm web python manage.py migrate
```

Ejecutar tests dentro del contenedor:

```bash
docker compose run --rm web python manage.py test
```

---

## Dev Container

El proyecto incluye configuración de Dev Container para trabajar en un entorno reproducible desde Visual Studio Code.

Para usarlo:

1. Instalar Docker.
2. Instalar Visual Studio Code.
3. Instalar la extensión Dev Containers.
4. Abrir el proyecto en VS Code.
5. Ejecutar “Reopen in Container”.

El contenedor instala las dependencias necesarias y permite ejecutar la aplicación en un entorno común para todos los integrantes.

---

## Tests

El proyecto cuenta con una batería de tests automatizados para comprobar modelos, formularios, vistas y flujos principales.

Ejecutar tests:

```bash
python manage.py test
```

También se puede ejecutar con coverage:

```bash
python -m coverage run manage.py test
python -m coverage report
```

El proyecto ha sido probado con más de 150 tests automatizados.

Los tests cubren, entre otros aspectos:

- Registro.
- Login.
- Perfil.
- Socios.
- Bonos.
- Compra de entradas.
- Cancelación de entradas.
- QR verificable.
- PDF de entradas.
- Favoritos.
- Recomendaciones.
- Panel staff.
- Estadísticas.
- Exportación CSV.
- Exportación PDF.
- Restricciones de permisos.

---

## Integración continua

El repositorio incluye un workflow de GitHub Actions en:

```txt
.github/workflows/django-tests.yml
```

El workflow está preparado para:

- Instalar dependencias.
- Comprobar migraciones pendientes.
- Ejecutar tests.
- Generar informe de coverage.

Actualmente, en el repositorio de GitHub Classroom, las Actions están deshabilitadas por política de la organización. Por este motivo, el workflow queda incluido y preparado, pero no puede ejecutarse en este repositorio mientras la organización mantenga esa restricción.

---

## Rutas principales

Algunas rutas importantes de la aplicación son:

```txt
/peliculas/
/peliculas/<movie_id>/
/login/
/registro/
/perfil/
/editar-perfil/
/bonos/
/mis-bonos/
/entradas/
/entrada/verificar/<codigo>/
/favoritos/
/recomendaciones/
/estadisticas/
/estadisticas/exportar/csv/
/estadisticas/exportar/pdf/
/panel-interno/
/panel-interno/sesiones/
/panel-interno/entradas/
/panel-interno/usuarios/
/panel-interno/bonos/
```

---

## Estructura del proyecto

Estructura principal:

```txt
pi2526-leedzeppelin/
├── Django/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── FICinema/
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   ├── urls.py
│   ├── tests.py
│   ├── templates/
│   └── migrations/
├── static/
│   ├── css/
│   ├── js/
│   └── img/
├── docs/
├── .devcontainer/
├── .github/
│   └── workflows/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── manage.py
└── README.md
```

---

## Seguridad y control de acceso

La aplicación aplica restricciones de acceso para evitar operaciones no permitidas:

- Solo los usuarios autenticados pueden comprar entradas.
- Solo los usuarios autenticados pueden comprar bonos.
- Solo los socios pueden comprar bonos.
- Cada usuario solo puede ver sus propias entradas.
- Cada usuario solo puede ver sus propios bonos.
- Cada usuario solo puede gestionar sus favoritos.
- Solo los usuarios staff pueden acceder al panel interno.
- Solo los usuarios staff pueden ver métricas internas.
- Solo las entradas activas muestran QR válido.
- Las entradas canceladas, usadas o caducadas se conservan como histórico, pero no son válidas para acceder a la sala.

---

## Gestión de errores

La aplicación contempla errores como:

- Peticiones fallidas a TMDB.
- Películas sin póster.
- Películas sin sinopsis.
- Películas sin tráiler.
- Datos incompletos en compra.
- Fechas no válidas.
- Sesiones no disponibles.
- Asientos ocupados.
- Intento de acceso sin iniciar sesión.
- Intento de acceso a recursos de otro usuario.
- Intento de acceso a panel interno sin permisos staff.
- Descarga o verificación de entradas no válidas.

---

## Notas sobre la práctica

FICinema es una aplicación académica. Las compras de entradas y bonos son simuladas y no utilizan pasarela de pago real.

El objetivo del proyecto es integrar tecnologías vistas en la asignatura, incluyendo:

- Desarrollo web con Django.
- Consumo de APIs externas.
- Procesamiento de datos con Pandas.
- Gestión de usuarios.
- Persistencia de datos.
- Tests automatizados.
- Dockerización.
- Exportación de datos.
- Diseño responsive.
- Accesibilidad.
- Integración continua preparada.

---

## Comandos útiles

Ejecutar servidor:

```bash
python manage.py runserver
```

Crear migraciones:

```bash
python manage.py makemigrations
```

Aplicar migraciones:

```bash
python manage.py migrate
```

Ejecutar tests:

```bash
python manage.py test
```

Ejecutar tests con coverage:

```bash
python -m coverage run manage.py test
python -m coverage report
```

Ejecutar con Docker:

```bash
docker compose up --build
```

La configuración de `docker-compose.yml` guarda la base de datos SQLite en un volumen persistente del contenedor. Así se evitan errores si `db.sqlite3` no existe todavía en el equipo y los datos no se pierden al parar el contenedor. La aplicación queda disponible en `http://localhost:8000`.

Ejecutar tests con Docker:

```bash
docker compose run --rm web python manage.py test
```

---

## Configuración de correo en producción

La aplicación envía correos de confirmación de compra de entradas y bonos usando el backend de correo configurado en Django. En local, por defecto, se usa el backend de consola, por lo que los mensajes se muestran en la terminal y no se envían a destinatarios reales.

En Render se ha preparado la integración con Resend mediante estas variables de entorno:

```env
EMAIL_PROVIDER=resend
EMAIL_REQUIRED_FOR_PURCHASE=False
EMAIL_TIMEOUT=6
EMAIL_TEST_RECIPIENT_OVERRIDE=ficinema.notificaciones@gmail.com
RESEND_API_KEY=<clave_privada_de_resend>
RESEND_FROM_EMAIL=FICinema <onboarding@resend.dev>
DEFAULT_FROM_EMAIL=FICinema <onboarding@resend.dev>
```

Con la configuración actual, Resend queda en modo de prueba porque se usa el remitente `onboarding@resend.dev`. Este remitente sirve para comprobar que la integración funciona, pero no permite enviar correos libremente a cualquier dirección introducida por los usuarios. Sin un dominio propio verificado en Resend, los envíos quedan limitados al correo asociado a la cuenta de Resend.

Por ese motivo, durante la demostración se usa `EMAIL_TEST_RECIPIENT_OVERRIDE=ficinema.notificaciones@gmail.com`. Aunque el usuario tenga otro email en su perfil, el correo real de prueba se centraliza en esa cuenta. Esto permite enseñar que el sistema genera y envía el email con el PDF adjunto sin comprar un dominio propio. No se deben publicar contraseñas, API keys ni accesos privados en el repositorio ni en el README; la comprobación puede hacerse enseñando la bandeja de entrada, los logs de Resend o una captura durante la defensa.

La compra de entradas y bonos no depende obligatoriamente del envío del correo. Primero se valida el pago simulado y se guardan las entradas o el bono en la base de datos; después se intenta enviar el email. Si Resend rechaza el envío por la limitación del dominio, la compra sigue registrada y el usuario puede consultar o descargar sus entradas desde la aplicación.

Para que el sistema pueda enviar correos a cualquier usuario registrado, habría que comprar o utilizar un dominio propio, añadirlo en Resend, verificar sus registros DNS y cambiar el remitente a una dirección de ese dominio, por ejemplo:

```env
RESEND_FROM_EMAIL=FICinema <entradas@tudominio.com>
DEFAULT_FROM_EMAIL=FICinema <entradas@tudominio.com>
```

---

## Despliegue y QR en producción

En producción se usa una URL pública estable configurada mediante `PUBLIC_BASE_URL`. Esto es importante porque los PDF de las entradas incluyen un QR que apunta a la página pública de verificación.

Variables principales de despliegue:

```env
PUBLIC_BASE_URL=https://ficinema.onrender.com
ALLOWED_HOSTS=ficinema.onrender.com,.onrender.com
CSRF_TRUSTED_ORIGINS=https://ficinema.onrender.com,https://*.onrender.com
```

El panel interno incluye una pantalla de staff para escanear códigos QR de entradas desde cámara o mediante introducción manual. La verificación pública de una entrada puede consultarse sin iniciar sesión, pero solo una cuenta staff puede confirmar el acceso y marcar la entrada como usada.

Ruta principal de staff:

```txt
/panel-interno/escanear-qr/
```

La cámara funciona mejor desde HTTPS. En producción, Render proporciona HTTPS, por lo que el escaneo desde móvil funciona sin depender de túneles temporales.

En local y Docker, `PUBLIC_BASE_URL=http://localhost:8000` funciona bien cuando se compra, descarga y verifica desde el mismo ordenador. Si se quiere escanear el QR desde un móvil, `localhost` no apunta al ordenador, sino al propio móvil. En ese caso hay que configurar la IP local del equipo que ejecuta Django o Docker, por ejemplo:

```env
PUBLIC_BASE_URL=http://192.168.1.50:8000
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,192.168.1.50
CSRF_TRUSTED_ORIGINS=http://192.168.1.50:8000
```

La IP cambia según la red y el equipo de cada persona, por eso la validación móvil local no puede quedar completamente fija en el proyecto. Para una prueba estable desde cualquier dispositivo se recomienda usar la URL pública de Render: `https://ficinema.onrender.com`.

También existe una ruta ligera de comprobación para despliegues:

```txt
/healthz/
```

## Limitaciones del plan gratuito en Render

El despliegue está pensado para funcionar sin coste usando Render. En el plan gratuito, la primera carga puede tardar más si el servicio estaba dormido por inactividad. Además, las bases de datos PostgreSQL gratuitas de Render tienen caducidad, por lo que para conservar datos a largo plazo habría que hacer copias de seguridad o pasar a una base de datos persistente de pago.

Para la entrega, la configuración gratuita es suficiente: la aplicación queda accesible públicamente, los QR apuntan a una URL estable con HTTPS y el panel staff puede validar entradas desde navegador o móvil.

## Estado final

FICinema ha evolucionado desde una cartelera básica conectada con TMDB hasta una aplicación de cine completa con usuarios, socios, bonos, entradas, QR, PDFs, favoritos, recomendaciones, estadísticas internas, exportaciones, panel staff, responsive avanzado, accesibilidad y tests automatizados.

---

## Notas de despliegue local con Docker

La aplicación puede ejecutarse con Docker Compose:

```bash
docker compose up --build
```

El servicio publica el puerto `8000`, por lo que se puede abrir desde el navegador en:

```txt
http://localhost:8000/
```

La base de datos SQLite se guarda en un volumen de Docker llamado `ficinema_sqlite_data`. Los datos se conservan al parar y levantar el contenedor, pero se eliminarán si se borra ese volumen. Para empezar desde cero se puede eliminar el volumen manualmente.

Para probar QR desde un móvil en Docker hay que cambiar `PUBLIC_BASE_URL` por la IP del ordenador en la red local, igual que en ejecución local con Python.

---

## APIs externas utilizadas

- **TMDB**: fuente principal de películas, pósteres, valoraciones, sinopsis y vídeos.
- **OMDb**: respaldo de metadatos cuando TMDB no devuelve algún dato textual.
- **YouTube Data API v3**: respaldo opcional para tráileres cuando TMDB no devuelve un tráiler válido.

Variables de entorno relevantes:

```env
TMDB_API_KEY=
TMDB_ACCESS_TOKEN=
OMDB_API_KEY=
YOUTUBE_API_KEY=
```

En producción se recomienda usar una URL estable mediante `PUBLIC_BASE_URL`, como se explica en el apartado de despliegue y QR. Para pruebas locales con túneles temporales se pueden añadir los dominios del túnel a `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`, pero esa configuración no es la prevista para la entrega final.

---

## Checklist rápido de defensa y evaluación

Antes de enseñar la práctica se recomienda comprobar estas rutas en el entorno que se vaya a evaluar:

```txt
/healthz/
/panel-interno/
/panel-interno/estado/
/panel-interno/escanear-qr/
/estadisticas/
/entradas/
/favoritos/
/recomendaciones/
```

Flujo recomendado para la demostración:

1. Entrar en cartelera y abrir una película con sesiones futuras.
2. Comprar una entrada con pago simulado.
3. Ver que la entrada aparece en **Mis entradas** y que se puede descargar el PDF.
4. Abrir el QR de la entrada.
5. Entrar con una cuenta staff y validar el QR desde el panel interno.
6. Comprobar que la entrada queda marcada como usada y que la validación aparece en estadísticas.
7. Mostrar `/panel-interno/estado/` para justificar APIs, correo, QR público, base de datos y modo de pago.
8. Mostrar `/estadisticas/` y sus exportaciones CSV/PDF para justificar el análisis con Pandas.

### Correo en modo demo

La aplicación guarda la compra antes de intentar enviar el correo. Por tanto, si el correo falla por configuración externa, la entrada o el bono siguen disponibles dentro de la aplicación.

En esta entrega se usa una configuración gratuita de Resend. Sin dominio propio verificado, el envío real queda centralizado en la cuenta de pruebas indicada por `EMAIL_TEST_RECIPIENT_OVERRIDE`. Esto permite demostrar que el sistema genera el correo y adjunta los PDFs, sin publicar credenciales ni comprar un dominio.

No se deben incluir contraseñas, API keys ni accesos privados en el repositorio. Si el profesor necesita comprobar los correos, lo recomendable es enseñarlos durante la defensa o mostrar los logs de Resend, no publicar la contraseña del Gmail en el README.

### QR por entorno

- **Render**: entorno recomendado para validar QR desde móvil porque usa HTTPS y una URL pública estable.
- **Python local**: con `localhost` funciona en el mismo ordenador. Para móvil hay que usar la IP del PC.
- **Docker local**: igual que Python local; depende de la IP del equipo y de la red donde se ejecute.

Por ese motivo no se deja una IP fija en el proyecto. Cada persona que ejecute la aplicación en local debe adaptar `PUBLIC_BASE_URL`, `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` a su red si quiere validar QR desde otro dispositivo.

---

## Configuración recomendada por entorno

Para evitar confusiones entre ejecución local, Docker y Render, el repositorio incluye tres plantillas de variables:

- `.env.local.example`: ejecución con `python manage.py runserver`.
- `.env.docker.example`: ejecución con `docker compose up --build`.
- `.env.render.example`: variables equivalentes para configurar en Render.

En local con Python, si se usa Gmail SMTP, no se debe activar `EMAIL_TEST_RECIPIENT_OVERRIDE` si se quiere comprobar el envío al correo real de cada usuario registrado. En Render, usando Resend sin dominio propio verificado, sí se usa `EMAIL_TEST_RECIPIENT_OVERRIDE=ficinema.notificaciones@gmail.com` para centralizar el correo de prueba y evitar que la compra falle por una limitación del proveedor.

Antes de entregar o defender, se puede ejecutar:

```bash
python manage.py check
python manage.py test
```

En Windows también se incluye:

```powershell
./scripts/check_before_delivery.ps1
```

Y en Linux/macOS:

```bash
./scripts/check_before_delivery.sh
```

La guía rápida de demostración está en `DEMO.md`.
