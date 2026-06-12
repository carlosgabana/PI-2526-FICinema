$ErrorActionPreference = "Stop"

Write-Host "== FICinema: comprobación previa a entrega =="
python manage.py check
python manage.py test
python manage.py collectstatic --noinput
Write-Host "Comprobación finalizada correctamente."
