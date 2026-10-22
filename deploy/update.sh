#!/usr/bin/env bash
# Выкатка новой версии. Его запускает GitHub Actions по SSH от пользователя diary.
# Всё внутри main(): bash дочитает файл целиком до того, как git его обновит.
set -euo pipefail

main() {
    cd /opt/diary_bot
    git fetch --quiet origin main
    git reset --quiet --hard origin/main      # .env и diary.db не в git — их не трогает
    venv/bin/pip install -q -r requirements.txt
    sudo /usr/bin/systemctl restart diary-bot
    sleep 6
    if systemctl is-active --quiet diary-bot; then
        echo "OK: бот перезапущен на $(git log -1 --format='%h %s')"
    else
        journalctl -u diary-bot -n 40 --no-pager
        exit 1
    fi
}

main "$@"
