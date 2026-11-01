#!/usr/bin/env bash
# Запуск userbot'а из его папки, через виртуальное окружение.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
[ -x .venv/bin/python ] || { echo "Сначала выполните ./install.sh" >&2; exit 1; }
[ -f .env ] || { echo "Нет .env. Выполните ./install.sh или: cp .env.example .env" >&2; exit 1; }
exec .venv/bin/python owner_session.py "$@"
