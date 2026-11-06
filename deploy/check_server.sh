#!/usr/bin/env bash
# ============================================================================
# PicNest - Проверка готовности сервера к деплою
# ============================================================================
# Запускается НА сервере (Ubuntu 22.04/24.04). Ничего не меняет, только читает.
#
# Использование:
#   bash check_server.sh              # человекочитаемый отчёт
#   bash check_server.sh --json       # машиночитаемый вывод
#
# Код возврата: 0 — всё критичное в порядке, 1 — есть блокирующие проблемы.
# ============================================================================

set -uo pipefail

JSON=0
[[ "${1:-}" == "--json" ]] && JSON=1

PASS=0
WARN=0
FAIL=0

declare -a RESULTS=()

# --- helpers ---------------------------------------------------------------

log_result() {
    local status="$1" name="$2" detail="$3"
    case "$status" in
        PASS) PASS=$((PASS + 1)) ;;
        WARN) WARN=$((WARN + 1)) ;;
        FAIL) FAIL=$((FAIL + 1)) ;;
    esac
    RESULTS+=("${status}|${name}|${detail}")
    if [[ $JSON -eq 0 ]]; then
        case "$status" in
            PASS) printf '  \033[32m[ OK ]\033[0m %-28s %s\n' "$name" "$detail" ;;
            WARN) printf '  \033[33m[WARN]\033[0m %-28s %s\n' "$name" "$detail" ;;
            FAIL) printf '  \033[31m[FAIL]\033[0m %-28s %s\n' "$name" "$detail" ;;
        esac
    fi
}

section() {
    [[ $JSON -eq 0 ]] && printf '\n\033[1m%s\033[0m\n' "$1"
    return 0
}

# --- 1. ОС -----------------------------------------------------------------

section "1. Операционная система"

OS_ID=""; OS_VERSION=""; OS_PRETTY=""
if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_VERSION="${VERSION_ID:-unknown}"
    OS_PRETTY="${PRETTY_NAME:-unknown}"
fi
KERNEL="$(uname -r)"
ARCH="$(uname -m)"

if [[ "$OS_ID" == "ubuntu" && ( "$OS_VERSION" == "22.04" || "$OS_VERSION" == "24.04" ) ]]; then
    log_result PASS "Ubuntu" "$OS_PRETTY (kernel $KERNEL, $ARCH)"
elif [[ "$OS_ID" == "ubuntu" ]]; then
    log_result WARN "Ubuntu" "$OS_PRETTY — ожидалась 22.04 или 24.04"
else
    log_result FAIL "Ubuntu" "$OS_PRETTY — требуется Ubuntu 22.04/24.04"
fi

# --- 2. Ресурсы ------------------------------------------------------------

section "2. Ресурсы сервера"

MEM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)
if   (( MEM_MB >= 3500 )); then log_result PASS "RAM" "${MEM_MB} MB"
elif (( MEM_MB >= 1800 )); then log_result WARN "RAM" "${MEM_MB} MB — хватит для app+db+redis, но Grafana может вытеснять (нужно ~4 GB)"
else                            log_result FAIL "RAM" "${MEM_MB} MB — мало, нужно минимум 2 GB (лучше 4 GB)"
fi

CPU=$(nproc 2>/dev/null || echo 1)
if   (( CPU >= 2 )); then log_result PASS "CPU" "${CPU} vCPU"
else                      log_result WARN "CPU" "${CPU} vCPU — сборка образа будет медленной"
fi

SWAP_MB=$(awk '/SwapTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)
if (( SWAP_MB > 0 )); then log_result PASS "Swap" "${SWAP_MB} MB"
else                       log_result WARN "Swap" "не настроен — рекомендуется swap 2 GB на VPS"
fi

# --- 3. Диск ---------------------------------------------------------------

section "3. Дисковое пространство"

# Смотрим раздел, где будут жить образы и volumes (/var/lib/docker),
# а не /, который может быть отдельным маленьким разделом.
DISK_PATH="/var/lib/docker"
[[ -d "$DISK_PATH" ]] || DISK_PATH="/"
AVAIL_GB=$(df -Pk "$DISK_PATH" | awk 'NR==2 {printf "%d", $4/1024/1024}')
AVAIL_H=$(df -Ph "$DISK_PATH" | awk 'NR==2 {print $4}')
USE_PCT=$(df -P "$DISK_PATH" | awk 'NR==2 {print $5}')

if   (( AVAIL_GB >= 20 )); then log_result PASS "Свободно на $DISK_PATH" "$AVAIL_H (${USE_PCT} занято)"
elif (( AVAIL_GB >= 10 )); then log_result WARN "Свободно на $DISK_PATH" "$AVAIL_H — минимум есть, но образы + БД быстро съедят 10 GB"
else                            log_result FAIL "Свободно на $DISK_PATH" "$AVAIL_H — нужно минимум 10 GB"
fi

# --- 4. Docker -------------------------------------------------------------

section "4. Docker"

if command -v docker >/dev/null 2>&1; then
    DOCKER_VER="$(docker --version 2>/dev/null)"
    if docker info >/dev/null 2>&1; then
        log_result PASS "Docker" "$DOCKER_VER (daemon работает)"
        DOCKER_OK=1
    else
        log_result FAIL "Docker" "$DOCKER_VER установлен, но daemon не отвечает"
        DOCKER_OK=0
    fi
else
    log_result FAIL "Docker" "не установлен"
    DOCKER_OK=0
fi

# Compose v2 — именно плагин `docker compose`, а не старый docker-compose
if [[ $DOCKER_OK -eq 1 ]] && docker compose version >/dev/null 2>&1; then
    log_result PASS "Docker Compose v2" "$(docker compose version --short 2>/dev/null || docker compose version)"
elif [[ $DOCKER_OK -eq 1 ]]; then
    log_result FAIL "Docker Compose v2" "плагин не найден (нужен docker-compose-plugin)"
else
    log_result FAIL "Docker Compose v2" "не проверено — нет Docker"
fi

# Старый docker-compose v1 — не ошибка, но деплой-скрипт его не использует
if command -v docker-compose >/dev/null 2>&1; then
    log_result WARN "docker-compose v1" "$(docker-compose --version 2>/dev/null) — устарел, скрипт использует 'docker compose'"
fi

# --- 5. Порты --------------------------------------------------------------

section "5. Порты"

port_state() {
    local port="$1"
    # ss есть на Ubuntu 22.04+; -H без заголовка, -l listening, -n numeric
    if command -v ss >/dev/null 2>&1; then
        ss -H -lntu "sport = :${port}" 2>/dev/null | head -1
    else
        netstat -lntu 2>/dev/null | awk -v p=":${port}" '$4 ~ p"$" {print; exit}'
    fi
}

# 22 — должен слушать, иначе мы бы сюда не попали; проверяем что это sshd
if PORT22="$(port_state 22)" && [[ -n "$PORT22" ]]; then
    log_result PASS "Порт 22" "слушает: $(echo "$PORT22" | awk '{print $1"/"$5}')"
else
    log_result WARN "Порт 22" "ss не показал слушателя — возможно, порт изменён в sshd_config"
fi

for p in 80 443; do
    if LISTEN="$(port_state "$p")" && [[ -n "$LISTEN" ]]; then
        OWNER="$(echo "$LISTEN" | awk '{print $1, $5}')"
        log_result WARN "Порт $p" "уже занят ($OWNER) — проверьте, не запущен ли другой веб-сервер"
    else
        log_result PASS "Порт $p" "свободен"
    fi
done

# --- 6. Firewall / ufw -----------------------------------------------------

section "6. Файрвол"

if command -v ufw >/dev/null 2>&1; then
    UFW_STATE="$(ufw status 2>/dev/null | head -1)"
    if echo "$UFW_STATE" | grep -qi "inactive"; then
        log_result WARN "ufw" "выключен (${UFW_STATE})"
    else
        OPEN="$(ufw status 2>/dev/null | grep -E '^(80|443|22|OpenSSH)' | tr '\n' '; ')"
        log_result PASS "ufw" "${UFW_STATE}${OPEN:+ | $OPEN}"
    fi
else
    log_result WARN "ufw" "не установлен"
fi

if command -v iptables >/dev/null 2>&1; then
    NUM_RULES=$(iptables -S 2>/dev/null | wc -l | tr -d ' ')
    log_result PASS "iptables" "${NUM_RULES} правил (может управляться Docker/ufw)"
fi

# --- 7. Базовые утилиты и доступ -------------------------------------------

section "7. Утилиты и git"

for bin in git curl openssl; do
    if command -v "$bin" >/dev/null 2>&1; then
        log_result PASS "$bin" "$($bin --version 2>/dev/null | head -1)"
    else
        log_result WARN "$bin" "не установлен — deploy.py поставит его при необходимости"
    fi
done

if command -v nginx >/dev/null 2>&1; then
    log_result PASS "nginx" "$(nginx -v 2>&1)"
else
    log_result WARN "nginx" "не установлен — deploy.py установит"
fi

# --- 8. Доступность GitHub -------------------------------------------------

section "8. Сеть"

if curl -fsS --max-time 10 -o /dev/null https://github.com 2>/dev/null; then
    log_result PASS "github.com" "доступен"
else
    log_result FAIL "github.com" "недоступен — git clone не сработает"
fi

if curl -fsS --max-time 10 -o /dev/null https://download.docker.com 2>/dev/null; then
    log_result PASS "download.docker.com" "доступен"
else
    log_result WARN "download.docker.com" "недоступен — установка Docker может не пройти"
fi

# Проверка места в inode (на маленьких VPS бывает исчерпание)
INODE_PCT=$(df -Pi / | awk 'NR==2 {gsub("%","",$5); print $5}')
if (( INODE_PCT < 90 )); then
    log_result PASS "Inodes" "${INODE_PCT}% использовано"
else
    log_result WARN "Inodes" "${INODE_PCT}% использовано — риск исчерпания"
fi

# --- Итог ------------------------------------------------------------------

if [[ $JSON -eq 1 ]]; then
    printf '{"pass":%d,"warn":%d,"fail":%d,"results":[' "$PASS" "$WARN" "$FAIL"
    first=1
    for r in "${RESULTS[@]}"; do
        IFS='|' read -r s n d <<< "$r"
        [[ $first -eq 0 ]] && printf ','
        first=0
        printf '{"status":"%s","name":"%s","detail":"%s"}' \
            "$s" "${n//\"/\\\"}" "${d//\"/\\\"}"
    done
    printf ']}\n'
else
    printf '\n\033[1mИтого:\033[0m \033[32m%d OK\033[0m, \033[33m%d предупреждений\033[0m, \033[31m%d ошибок\033[0m\n' \
        "$PASS" "$WARN" "$FAIL"
fi

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
