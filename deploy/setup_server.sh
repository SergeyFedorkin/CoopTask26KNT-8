#!/usr/bin/env bash
# Первичная настройка РОССИЙСКОГО сервера (Ubuntu 22.04/24.04). Запуск от root:
#   bash setup_server.sh <ссылка-на-репозиторий> <IP-зарубежного-сервера>
# Пример: bash setup_server.sh https://github.com/user/diary_bot.git 203.0.113.10
set -euo pipefail

REPO_URL="${1:?Укажи ссылку на репозиторий}"
RELAY_IP="${2:?Укажи IP зарубежного сервера}"
APP_USER=diary
APP_DIR=/opt/diary_bot
SSH_DIR="/home/$APP_USER/.ssh"

main() {
    [[ $EUID -eq 0 ]] || { echo "Запусти от root"; exit 1; }

    echo "==> Пакеты"
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip git autossh curl >/dev/null

    echo "==> Пользователь $APP_USER"
    id "$APP_USER" &>/dev/null || useradd --create-home --shell /bin/bash "$APP_USER"
    usermod -aG systemd-journal "$APP_USER"
    install -d -m 700 -o "$APP_USER" -g "$APP_USER" "$SSH_DIR"

    gen_key tunnel_key "tunnel to relay"
    gen_key deploy_key "github actions deploy"
    gen_key github_key "read repo"

    # ключ для GitHub Actions: пускаем его в аккаунт diary
    touch "$SSH_DIR/authorized_keys"
    grep -qxFf "$SSH_DIR/deploy_key.pub" "$SSH_DIR/authorized_keys" || cat "$SSH_DIR/deploy_key.pub" >> "$SSH_DIR/authorized_keys"
    cat > "$SSH_DIR/config" <<EOF
Host github.com
    IdentityFile $SSH_DIR/github_key
    StrictHostKeyChecking accept-new
EOF
    chown -R "$APP_USER:$APP_USER" "$SSH_DIR"
    chmod 600 "$SSH_DIR/authorized_keys" "$SSH_DIR/config"

    echo "==> Код"
    if [[ ! -d "$APP_DIR/.git" ]]; then
        if [[ "$REPO_URL" == git@* ]]; then
            echo
            echo "Репозиторий приватный. Добавь этот ключ в GitHub: репозиторий → Settings → Deploy keys → Add (без галочки write):"
            echo
            cat "$SSH_DIR/github_key.pub"
            echo
            read -rp "Добавил? Нажми Enter... " _
        fi
        install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
        sudo -u "$APP_USER" git clone --quiet "$REPO_URL" "$APP_DIR"
    fi
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q --upgrade pip
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

    echo "==> .env"
    if [[ ! -f "$APP_DIR/.env" ]]; then
        read -rp "Токен прод-бота от @BotFather: " token
        cat > "$APP_DIR/.env" <<EOF
BOT_TOKEN=$token
ALLOWED_USERS=
TZ_NAME=Europe/Moscow
TG_PROXY=socks5://127.0.0.1:1080
EOF
        chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
        chmod 600 "$APP_DIR/.env"
    fi

    echo
    echo "================ ШАГ НА ЗАРУБЕЖНОМ СЕРВЕРЕ ================"
    echo "Выполни на $RELAY_IP (от root) — команда целиком, одной строкой:"
    echo
    echo "  bash setup_relay.sh '$(cat "$SSH_DIR/tunnel_key.pub")'"
    echo
    read -rp "Сделал? Нажми Enter... " _

    echo "==> systemd"
    sed "s/RELAY_IP/$RELAY_IP/" "$APP_DIR/deploy/tg-tunnel.service" > /etc/systemd/system/tg-tunnel.service
    cp "$APP_DIR/deploy/diary-bot.service" /etc/systemd/system/diary-bot.service
    cat > /etc/sudoers.d/diary-bot <<EOF
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart diary-bot, /usr/bin/systemctl restart tg-tunnel
EOF
    chmod 440 /etc/sudoers.d/diary-bot
    visudo -cq
    systemctl daemon-reload
    systemctl enable --now tg-tunnel
    sleep 5

    echo "==> Проверка туннеля до Telegram"
    if curl -s -m 15 --socks5-hostname 127.0.0.1:1080 -o /dev/null -w "%{http_code}" https://api.telegram.org | grep -qE "200|302"; then
        echo "OK: api.telegram.org доступен через туннель"
    else
        echo "ВНИМАНИЕ: туннель не работает. Смотри: journalctl -u tg-tunnel -n 30"
    fi

    echo "==> Проверка RUZ"
    if curl -s -m 15 "https://ruz.hse.ru/api/search?term=test&type=group" | head -c 1 | grep -q "\["; then
        echo "OK: RUZ отвечает"
    else
        echo "ВНИМАНИЕ: RUZ не ответил JSON — расписание будет только из кэша/ручное"
    fi

    systemctl enable --now diary-bot
    sleep 5
    systemctl --no-pager --lines=15 status diary-bot || true

    echo
    echo "================ СЕКРЕТЫ ДЛЯ GITHUB ACTIONS ================"
    echo "Репозиторий → Settings → Secrets and variables → Actions → New repository secret"
    echo
    echo "VPS_HOST = $(curl -s -m 5 https://api.ipify.org || hostname -I | awk '{print $1}')"
    echo "VPS_SSH_KEY = всё, что ниже, включая строки BEGIN/END:"
    cat "$SSH_DIR/deploy_key"
    echo
    echo "Готово. Логи бота: journalctl -u diary-bot -f"
}

gen_key() {
    local name=$1 comment=$2
    [[ -f "$SSH_DIR/$name" ]] || sudo -u "$APP_USER" ssh-keygen -q -t ed25519 -N "" -C "$comment" -f "$SSH_DIR/$name"
}

main "$@"
