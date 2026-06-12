#!/usr/bin/env bash
set -euo pipefail

echo "== FICinema: comprobación previa a entrega =="
python manage.py check
python manage.py test
python manage.py collectstatic --noinput
echo "Comprobación finalizada correctamente."
