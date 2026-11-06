#!/usr/bin/env bash
# Состояние сервера после удаления Amnezia. Только чтение.
set -uo pipefail
echo "=== containers ==="; docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
echo; echo "=== ports 80/443 ==="; ss -lntup 2>/dev/null | grep -E ':(80|443)\b' || echo "80/443 свободны"
echo; echo "=== df ==="; df -h / /var/lib/docker 2>/dev/null | sort -u
echo; echo "=== docker df ==="; docker system df
echo; echo "=== swap ==="; swapon --show; free -m | head -3
echo; echo "=== /opt/picnest ==="; ls -la /opt/picnest 2>/dev/null
echo; echo "=== nginx ==="; command -v nginx && nginx -v 2>&1 || echo "нет nginx"
echo; echo "=== ufw ==="; ufw status 2>/dev/null | head -3
echo; echo "=== docker daemon json ==="; cat /etc/docker/daemon.json 2>/dev/null || echo "нет daemon.json"
