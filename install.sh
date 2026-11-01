#!/usr/bin/env bash
# Установка tg-gift-business-bot одной командой.
#
#   Из склонированного репозитория:   ./install.sh
#   Без клонирования:                 curl -fsSL https://raw.githubusercontent.com/gytfel/Tg-ref/main/install.sh | bash
#   Плюс автозапуск (systemd, Linux): ./install.sh --service
#
# Переменные окружения:
#   INSTALL_DIR  куда клонировать, если скрипт запущен не из репозитория (по умолчанию ~/tg-gift-bot)
#   REPO_URL     откуда клонировать (по умолчанию https://github.com/gytfel/Tg-ref.git)
#   BRANCH       ветка (по умолчанию main)
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/gytfel/Tg-ref.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/tg-gift-bot}"
WANT_SERVICE=0

for arg in "$@"; do
  case "$arg" in
    --service) WANT_SERVICE=1 ;;
    -h|--help) sed -n '2,13p' "$0" 2>/dev/null || true; exit 0 ;;
    *) echo "Неизвестный аргумент: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mОшибка:\033[0m %s\n' "$*" >&2; exit 1; }

# Ввод читаем из терминала, чтобы работало и при `curl ... | bash`.
TTY=/dev/tty
have_tty() { [ -r "$TTY" ] && [ -w "$TTY" ] && { : <"$TTY"; } 2>/dev/null; }
ask() {  # ask <prompt> <default> -> echo answer
  local prompt="$1" def="${2:-}" ans=""
  if have_tty; then
    if [ -n "$def" ]; then printf '%s [%s]: ' "$prompt" "$def" >"$TTY"; else printf '%s: ' "$prompt" >"$TTY"; fi
    IFS= read -r ans <"$TTY" || true
  fi
  printf '%s' "${ans:-$def}"
}

# 1. Найти или скачать проект.
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/owner_session.py" ]; then
  APP_DIR="$SCRIPT_DIR"
else
  command -v git >/dev/null || die "нужен git: sudo apt install git (или brew install git)"
  if [ -d "$INSTALL_DIR/.git" ]; then
    say "Обновляю $INSTALL_DIR"
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
  else
    say "Клонирую $REPO_URL в $INSTALL_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  fi
  APP_DIR="$INSTALL_DIR"
fi
cd "$APP_DIR"
say "Папка проекта: $APP_DIR"

# 2. Python 3.10+ с venv.
PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$(command -v "$cand")"; break
  fi
done
[ -n "$PY" ] || die "нужен Python 3.10 или новее: sudo apt install python3 python3-venv (или brew install python)"
say "Python: $("$PY" --version 2>&1)"

if [ ! -x .venv/bin/python ]; then
  say "Создаю виртуальное окружение .venv"
  if ! "$PY" -m venv .venv 2>/dev/null; then
    rm -rf .venv
    die "не удалось создать venv. На Debian/Ubuntu: sudo apt install python3-venv"
  fi
fi

say "Ставлю зависимости"
.venv/bin/python -m pip install --upgrade --quiet pip
.venv/bin/python -m pip install --quiet -r requirements.txt

say "Проверяю тестами"
test_log="$(mktemp)"
if ! .venv/bin/python -m unittest tests.test_logic tests.test_owner_session >"$test_log" 2>&1; then
  cat "$test_log" >&2; rm -f "$test_log"; die "тесты не прошли"
fi
rm -f "$test_log"

# 3. Настройка .env.
set_env() {  # set_env KEY VALUE  — заменить строку KEY=... в .env
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  awk -v k="$key" -v v="$val" 'BEGIN{done=0} $0 ~ "^"k"=" {print k"="v; done=1; next} {print} END{if(!done) print k"="v}' .env >"$tmp"
  mv "$tmp" .env
}

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  if have_tty; then
    say "Заполним .env (Enter — оставить значение по умолчанию)"
    echo "api_id и api_hash берутся на https://my.telegram.org -> API development tools" >"$TTY"
    api_id=""
    while ! [[ "$api_id" =~ ^[0-9]+$ ]]; do api_id="$(ask 'TG_API_ID (число)' '')"; done
    api_hash=""
    while [ -z "$api_hash" ]; do api_hash="$(ask 'TG_API_HASH' '')"; done
    set_env TG_API_ID "$api_id"
    set_env TG_API_HASH "$api_hash"
    set_env OFFER_CODEWORD "$(ask 'Кодовое слово для команды оффера (пусто = выключено)' '')"
    set_env OFFER_MAX_STARS "$(ask 'Максимум звёзд за один оффер' '1000')"
    set_env OFFER_DURATION_HOURS "$(ask 'Срок оффера в часах (6/12/24/36/48/72)' '6')"
    set_env OFFER_ACCEPT_MIN_STARS "$(ask 'Автопринимать входящие от (пусто = никогда)' '')"
    set_env OFFER_DECLINE_BELOW_STARS "$(ask 'Автоотклонять входящие ниже (пусто = никогда)' '')"
  else
    warn "Нет терминала для ввода. Заполните $APP_DIR/.env вручную."
  fi
else
  say ".env уже есть, не трогаю"
fi

chmod +x run.sh 2>/dev/null || true

# 4. Опционально: systemd-сервис.
if [ "$WANT_SERVICE" = 1 ]; then
  command -v systemctl >/dev/null || die "systemd не найден, --service работает только на Linux с systemd"
  session_name="$(grep -E '^TG_SESSION=' .env | cut -d= -f2- || true)"
  if [ ! -f "${session_name:-owner}.session" ]; then
    warn "Сессии ещё нет. Сначала один раз запустите ./run.sh и войдите в Telegram, потом снова ./install.sh --service"
    exit 1
  fi
  unit_dir="$HOME/.config/systemd/user"
  mkdir -p "$unit_dir"
  cat >"$unit_dir/tg-gift-bot.service" <<EOF
[Unit]
Description=tg-gift-business-bot (userbot)
After=network-online.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/owner_session.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now tg-gift-bot.service
  loginctl enable-linger "$USER" 2>/dev/null || warn "не удалось включить linger: сервис может остановиться после выхода из системы"
  say "Сервис запущен. Логи: journalctl --user -u tg-gift-bot -f"
  exit 0
fi

cat <<EOF

Готово. Дальше:
  cd "$APP_DIR"
  ./run.sh

При первом запуске введите номер телефона, код из Telegram и пароль 2FA.
Чтобы работало в фоне (Linux):  ./install.sh --service
EOF
