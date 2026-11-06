#!/usr/bin/env bash
# Диагностика: место на диске и занятые порты. Только чтение.
set -uo pipefail

echo "=== df -h ==="
df -h

echo
echo "=== разметка диска ==="
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,TYPE 2>/dev/null

echo
echo "=== LVM (свободное место в VG) ==="
command -v vgs >/dev/null && vgs 2>/dev/null || echo "нет LVM"

echo
echo "=== крупнейшие каталоги в / (top-15) ==="
du -xhd1 / 2>/dev/null | sort -rh | head -15

echo
echo "=== /var/lib/docker ==="
du -sh /var/lib/docker 2>/dev/null
docker system df 2>/dev/null

echo
echo "=== /var/log ==="
du -xhd1 /var/log 2>/dev/null | sort -rh | head -10

echo
echo "=== /root и /opt ==="
du -xhd1 /root 2>/dev/null | sort -rh | head -10
du -xhd1 /opt 2>/dev/null | sort -rh | head -10

echo
echo "=== кто держит 443 (tcp+udp) ==="
ss -lntup 2>/dev/null | grep -E ':443\b' || echo "443 не слушает"
echo "--- процессы ---"
ss -lntup 2>/dev/null | grep ':443' | grep -oP 'users:\(\("\K[^"]+' | sort -u | while read -r p; do
    echo "--- $p ---"
    systemctl status "$p" --no-pager 2>/dev/null | head -5
    ps -o pid,cmd -p "$(pgrep -f "/usr/sbin/$p|/usr/bin/$p" | head -1)" 2>/dev/null
done

echo
echo "=== docker контейнеры ==="
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null

echo
echo "=== docker образы ==="
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' 2>/dev/null
