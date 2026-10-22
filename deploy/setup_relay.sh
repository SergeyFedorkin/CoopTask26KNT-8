#!/usr/bin/env bash
# Настройка ЗАРУБЕЖНОГО сервера-релея. Запуск от root:
#   bash setup_relay.sh 'ssh-ed25519 AAAA... tunnel to relay'
# Создаёт пользователя tunnel: без консоли, умеет только пробрасывать соединения.
set -euo pipefail

PUBKEY="${1:?Передай публичный ключ, который напечатал setup_server.sh}"

main() {
    [[ $EUID -eq 0 ]] || { echo "Запусти от root"; exit 1; }
    id tunnel &>/dev/null || useradd --create-home --shell /usr/sbin/nologin tunnel
    install -d -m 700 -o tunnel -g tunnel /home/tunnel/.ssh
    echo "restrict,port-forwarding $PUBKEY" > /home/tunnel/.ssh/authorized_keys
    chown tunnel:tunnel /home/tunnel/.ssh/authorized_keys
    chmod 600 /home/tunnel/.ssh/authorized_keys

    # проброс портов должен быть разрешён в sshd (в Ubuntu по умолчанию да)
    if grep -qiE "^\s*AllowTcpForwarding\s+no" /etc/ssh/sshd_config; then
        sed -i -E "s/^\s*AllowTcpForwarding\s+no/AllowTcpForwarding yes/I" /etc/ssh/sshd_config
        systemctl reload ssh || systemctl reload sshd
    fi

    if curl -s -m 10 -o /dev/null -w "%{http_code}" https://api.telegram.org | grep -qE "200|302"; then
        echo "OK: отсюда api.telegram.org доступен"
    else
        echo "ВНИМАНИЕ: с этого сервера api.telegram.org недоступен — нужен другой"
    fi
    echo "Готово. Возвращайся к setup_server.sh и жми Enter."
}

main "$@"
