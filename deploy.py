#!/usr/bin/env python3
"""PicNest — деплой на VPS по SSH.

Что делает скрипт (по порядку):
  1. подключается к серверу (ключ или пароль);
  2. проверяет ОС, диск, память, Docker и Compose v2;
  3. ставит Docker, если его нет;
  4. настраивает swap (если нет);
  5. клонирует/обновляет репозиторий в /opt/picnest;
  6. генерирует .env.production с случайными секретами (если файла нет);
  7. устанавливает nginx и раскладывает конфиг + snippet;
  8. собирает и поднимает стек (docker compose -f docker-compose.prod.yml);
  9. ждёт /health и печатает статус контейнеров.

Идемпотентность: повторный запуск не пересоздаёт секреты, не дублирует
ssl-конфиги и не переустанавливает уже стоящие пакеты.

Примеры:
  python deploy.py --host 83.141.67.249 --user root --key ~/.ssh/id_ed25519
  python deploy.py --host 83.141.67.249 --user root --password-from-env PICNEST_SSH_PASSWORD
  python deploy.py --host 83.141.67.249 --user root --dry-run
"""

from __future__ import annotations

import argparse
import os
import posixpath
import secrets
import shlex
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import paramiko
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "paramiko не установлен.\n"
        "Установите: pip install -r requirements-deploy.txt\n"
    )
    raise SystemExit(2)

# ============================================================================
# Логирование
# ============================================================================

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


if not _supports_color():
    for _attr in ("RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE", "CYAN"):
        setattr(C, _attr, "")


class Log:
    """Печать шагов и накопление их для итогового отчёта."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.steps: list[tuple[str, str]] = []  # (status, message)
        self.started = time.time()

    def step(self, num: str, title: str) -> None:
        print(f"\n{C.BOLD}{C.BLUE}[{num}]{C.RESET} {C.BOLD}{title}{C.RESET}")

    def info(self, msg: str) -> None:
        print(f"    {msg}")

    def ok(self, msg: str) -> None:
        print(f"    {C.GREEN}✓{C.RESET} {msg}")
        self.steps.append(("ok", msg))

    def warn(self, msg: str) -> None:
        print(f"    {C.YELLOW}!{C.RESET} {msg}")
        self.steps.append(("warn", msg))

    def fail(self, msg: str) -> None:
        print(f"    {C.RED}✗{C.RESET} {msg}")
        self.steps.append(("fail", msg))

    def cmd(self, cmd: str) -> None:
        """Печать выполняемой команды (в dry-run — единственный вывод)."""
        first = cmd.strip().splitlines()[0]
        if len(cmd.strip().splitlines()) > 1:
            first += " …"
        prefix = f"{C.CYAN}[dry-run]{C.RESET} " if self.dry_run else f"{C.DIM}$ {C.RESET}"
        print(f"    {prefix}{first}")

    def elapsed(self) -> str:
        total = int(time.time() - self.started)
        return f"{total // 60}м {total % 60}с"


# ============================================================================
# SSH-раннер
# ============================================================================

class RemoteError(RuntimeError):
    """Команда на сервере завершилась с ненулевым кодом."""


@dataclass
class Remote:
    host: str
    user: str
    port: int = 22
    key_path: Optional[Path] = None
    password: Optional[str] = None
    dry_run: bool = False
    log: Log = field(default_factory=Log)
    client: Optional[paramiko.SSHClient] = None
    _sftp: Optional[paramiko.SFTPClient] = None

    # -- соединение ---------------------------------------------------------

    def connect(self) -> None:
        if self.dry_run:
            self.log.info(f"dry-run: подключение к {self.user}@{self.host}:{self.port} пропущено")
            return

        self.client = paramiko.SSHClient()
        # TODO(безопасность): заменить на RejectPolicy + known_hosts после
        # первой проверки отпечатка ключа сервера.
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs: dict = dict(
            hostname=self.host,
            port=self.port,
            username=self.user,
            timeout=25,
            banner_timeout=30,
            auth_timeout=30,
        )
        if self.key_path:
            kwargs.update(
                key_filename=str(self.key_path),
                look_for_keys=False,
                allow_agent=False,
            )
        else:
            kwargs.update(password=self.password, look_for_keys=False, allow_agent=False)

        self.client.connect(**kwargs)
        self._sftp = self.client.open_sftp()

    def close(self) -> None:
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
        if self.client:
            self.client.close()

    # -- выполнение ---------------------------------------------------------

    def run(
        self,
        cmd: str,
        *,
        check: bool = True,
        sudo: bool = False,
        timeout: int = 300,
        quiet: bool = False,
    ) -> tuple[int, str, str]:
        """Выполнить команду. Возвращает (rc, stdout, stderr)."""
        full = f"sudo -n bash -lc {shlex.quote(cmd)}" if sudo else f"bash -lc {shlex.quote(cmd)}"

        if not quiet:
            self.log.cmd(cmd.strip())

        if self.dry_run:
            return 0, "", ""

        assert self.client is not None
        # get_pty не используем: без TTY вывод чище, а apt всё равно в режиме -y
        stdin, stdout, stderr = self.client.exec_command(full, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()

        if rc != 0 and check:
            raise RemoteError(
                f"Команда завершилась с кодом {rc}:\n    {cmd.strip()}\n"
                f"  stderr: {err.strip()[:2000] or '(пусто)'}"
            )
        return rc, out, err

    def read(self, cmd: str) -> str:
        rc, out, _ = self.run(cmd, check=False, quiet=True)
        return out.strip()

    def exists(self, path: str) -> bool:
        if self.dry_run:
            return False
        rc, _, _ = self.run(f"test -e {shlex.quote(path)}", check=False, quiet=True)
        return rc == 0

    def put(self, remote_path: str, content: str, mode: int = 0o644) -> None:
        """Записать файл на сервер атомарно (через временный файл)."""
        if self.dry_run:
            self.log.info(f"dry-run: запись {remote_path} ({len(content)} байт)")
            return
        assert self._sftp is not None
        tmp = f"{remote_path}.tmp-{secrets.token_hex(4)}"
        parent = posixpath.dirname(remote_path)
        self.run(f"mkdir -p {shlex.quote(parent)}", quiet=True)
        with self._sftp.open(tmp, "w") as fh:
            fh.write(content)
        self._sftp.chmod(tmp, mode)
        self.run(f"mv -f {shlex.quote(tmp)} {shlex.quote(remote_path)}", quiet=True)

    def upload(self, local: Path, remote_path: str, mode: int = 0o644) -> None:
        if self.dry_run:
            self.log.info(f"dry-run: загрузка {local} → {remote_path}")
            return
        assert self._sftp is not None
        parent = posixpath.dirname(remote_path)
        self.run(f"mkdir -p {shlex.quote(parent)}", quiet=True)
        tmp = f"{remote_path}.tmp-{secrets.token_hex(4)}"
        self._sftp.put(str(local), tmp)
        self._sftp.chmod(tmp, mode)
        self.run(f"mv -f {shlex.quote(tmp)} {shlex.quote(remote_path)}", quiet=True)


# ============================================================================
# Конфигурация деплоя
# ============================================================================

@dataclass
class DeployConfig:
    host: str
    user: str
    port: int
    key_path: Optional[Path]
    password: Optional[str]
    remote_dir: str
    repo_url: str
    branch: str
    domain: str
    dry_run: bool
    skip_nginx: bool
    skip_build: bool
    swap_mb: int
    source: str = "git"  # "git" — клон с GitHub, "local" — залить рабочую копию
    has_docker: bool = False
    min_disk_gb: int = 6  # ниже этого порога сборка образа может упасть


def generate_secret(length: int = 48) -> str:
    """URL-safe секрет без символов, ломающих .env и compose-подстановку."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def render_env_production(cfg: DeployConfig) -> str:
    """Сгенерировать .env.production со случайными секретами."""
    db_password = generate_secret(32)
    secret_key = generate_secret(64)
    grafana_password = generate_secret(24)

    cors = "http://localhost:3000,http://localhost:8080"
    if cfg.domain:
        cors = f"https://{cfg.domain},https://www.{cfg.domain}"

    return textwrap.dedent(
        f"""\
        # Сгенерировано deploy.py. Не коммитить в git.
        ENVIRONMENT=production
        DEBUG=false
        APP_VERSION=1.0.0

        POSTGRES_USER=picnest
        POSTGRES_PASSWORD={db_password}
        POSTGRES_DB=picnest
        DATABASE_URL=postgresql+asyncpg://picnest:{db_password}@db:5432/picnest

        REDIS_URL=redis://redis:6379/0
        USE_REDIS_FOR_RATE_LIMITING=true

        SECRET_KEY={secret_key}
        ALGORITHM=HS256
        ACCESS_TOKEN_EXPIRE_MINUTES=30
        REFRESH_TOKEN_EXPIRE_DAYS=7

        CORS_ALLOWED_ORIGINS={cors}
        CORS_ALLOW_CREDENTIALS=true
        CORS_ALLOW_METHODS=GET,POST,PUT,DELETE,PATCH,OPTIONS
        CORS_ALLOW_HEADERS=Authorization,Content-Type,X-Requested-With,Accept

        HSTS_MAX_AGE=31536000
        CSP_DEFAULT_SRC=self
        CSP_SCRIPT_SRC=self unsafe-inline unsafe-eval
        CSP_STYLE_SRC=self unsafe-inline
        CSP_IMG_SRC=self data: https:

        SENTRY_DSN=
        SENTRY_TRACES_SAMPLE_RATE=0.1
        SENTRY_RELEASE_VERSION=1.0.0

        PROMETHEUS_ENABLED=true
        PROMETHEUS_EXPORTER_HOST=0.0.0.0
        PROMETHEUS_EXPORTER_PORT=8000

        LOG_LEVEL=INFO
        LOG_FORMAT=json
        LOG_FILE=/app/logs/app.log

        GRAFANA_ADMIN_USER=admin
        GRAFANA_ADMIN_PASSWORD={grafana_password}

        RATE_LIMIT_ENABLED=true
        DEFAULT_RATE_LIMIT=100/hour
        LOGIN_MAX_ATTEMPTS_PER_MINUTE=5
        REGISTER_MAX_PER_MINUTE=3

        SQL_LOGGING=false
        SHOW_SQL_QUERIES=false
        SEED_DATA=false
        """
    )


# ============================================================================
# Шаги деплоя
# ============================================================================

def step_preflight(r: Remote, cfg: DeployConfig) -> None:
    r.log.step("1/8", "Проверка сервера")

    if r.dry_run:
        r.log.info("dry-run: реальные значения не читаются, проверки пропущены")
        r.log.ok("проверка ОС, диска и памяти — будет выполнена на сервере")
        cfg.has_docker = True
        return

    rc, out, _ = r.run(
        'test -r /etc/os-release && . /etc/os-release && echo "$ID $VERSION_ID"',
        check=False,
        quiet=True,
    )
    os_name, _, os_ver = (out.strip() or "unknown 0").partition(" ")
    r.log.info(f"ОС: {os_name} {os_ver}")

    # Диск: /var/lib/docker, если он уже есть, иначе корень.
    # Порог зависит от режима: полная пересборка образа требует ~6 GB
    # (слои + build cache + временные файлы), перезапуск готового образа —
    # почти ничего. Жёсткий порог здесь блокировал бы деплой на маленьких
    # VPS, где образ уже собран.
    disk_path = "/var/lib/docker" if r.exists("/var/lib/docker") else "/"
    avail_gb = int(r.read(f"df -Pk {disk_path} | awk 'NR==2 {{printf \"%d\", $4/1024/1024}}'") or 0)
    min_gb = cfg.min_disk_gb
    if avail_gb >= min_gb + 4:
        r.log.ok(f"Свободно {avail_gb} GB на {disk_path}")
    elif avail_gb >= min_gb:
        r.log.warn(f"Свободно {avail_gb} GB — впритык, после сборки сделаем prune")
    else:
        r.log.fail(
            f"Свободно {avail_gb} GB — нужно минимум {min_gb} GB "
            f"(снизить можно через --min-disk-gb, но сборка может упасть)"
        )
        raise RemoteError("Недостаточно места на диске")

    mem_mb = int(r.read("awk '/MemTotal/ {printf \"%d\", $2/1024}' /proc/meminfo") or 0)
    r.log.info(f"RAM: {mem_mb} MB, CPU: {r.read('nproc')}")

    rc, _, _ = r.run("command -v docker >/dev/null 2>&1", check=False, quiet=True)
    docker_present = rc == 0
    if docker_present:
        r.log.ok(f"Docker: {r.read('docker --version')}")
        rc2, _, _ = r.run("docker compose version >/dev/null 2>&1", check=False, quiet=True)
        if rc2 != 0:
            raise RemoteError("Docker есть, но плагин `docker compose` (v2) не установлен")
        r.log.ok(f"Compose: {r.read('docker compose version --short')}")
    else:
        r.log.warn("Docker не установлен — установим на следующем шаге")

    cfg.has_docker = docker_present


def step_install_docker(r: Remote, cfg: DeployConfig) -> None:
    if getattr(cfg, "has_docker", False):
        r.log.step("2/8", "Docker уже установлен — пропуск")
        return

    r.log.step("2/8", "Установка Docker")

    r.run("apt-get update -qq", timeout=600)
    r.run(
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
        "ca-certificates curl gnupg git",
        timeout=600,
    )
    r.run(
        "install -m 0755 -d /etc/apt/keyrings && "
        "curl -fsSL https://download.docker.com/linux/ubuntu/gpg "
        "-o /etc/apt/keyrings/docker.asc && "
        "chmod a+r /etc/apt/keyrings/docker.asc",
        timeout=300,
    )
    r.run(
        'echo "deb [arch=$(dpkg --print-architecture) '
        'signed-by=/etc/apt/keyrings/docker.asc] '
        'https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" '
        "> /etc/apt/sources.list.d/docker.list",
        timeout=120,
    )
    r.run("apt-get update -qq", timeout=600)
    r.run(
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
        "docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
        timeout=900,
    )
    r.run("systemctl enable --now docker", timeout=120)
    r.log.ok("Docker и Compose v2 установлены")


def step_docker_mirror(r: Remote, cfg: DeployConfig) -> None:
    """Проверить доступность Docker Hub и при необходимости включить зеркало.

    Часть хостеров не маршрутизирует IPv4 до Cloudflare-адресов Docker Hub:
    curl проходит (он выбирает IPv6), а dockerd, работая только по IPv4,
    получает i/o timeout и образы не скачиваются.
    """
    r.log.step("2b/8", "Доступность Docker Hub")

    rc, _, _ = r.run(
        "timeout 15 curl -4 -fsS -o /dev/null https://auth.docker.io/token",
        check=False,
        quiet=True,
    )
    if rc == 0:
        r.log.ok("Docker Hub доступен напрямую")
        return

    r.log.warn("Docker Hub недоступен по IPv4 — включаем зеркало mirror.gcr.io")

    r.run(
        "python3 - <<'PY'\n"
        "import json, os\n"
        "p = '/etc/docker/daemon.json'\n"
        "cfg = {}\n"
        "if os.path.exists(p):\n"
        "    with open(p) as f:\n"
        "        try:\n"
        "            cfg = json.load(f)\n"
        "        except ValueError:\n"
        "            cfg = {}\n"
        "mirrors = cfg.setdefault('registry-mirrors', [])\n"
        "if 'https://mirror.gcr.io' not in mirrors:\n"
        "    mirrors.insert(0, 'https://mirror.gcr.io')\n"
        "with open(p, 'w') as f:\n"
        "    json.dump(cfg, f, indent=2)\n"
        "PY",
        timeout=120,
    )
    r.run("systemctl restart docker", timeout=180)
    r.log.ok("Зеркало включено, docker перезапущен")


def step_swap(r: Remote, cfg: DeployConfig) -> None:
    r.log.step("3/8", f"Swap ({cfg.swap_mb} MB)")

    current = int(r.read("awk '/SwapTotal/ {printf \"%d\", $2/1024}' /proc/meminfo") or "0")
    if current >= cfg.swap_mb * 0.9:
        r.log.ok(f"Swap уже есть: {current} MB")
        return

    # Свободное место: swap-файл занимает диск наравне с образами, а на VPS
    # с 10 GB он может съесть запас, нужный для сборки.
    free_mb = int(r.read("df -Pk / | awk 'NR==2 {printf \"%d\", $4/1024}'") or "0")
    needed_mb = cfg.swap_mb + 2048  # swap + запас на образы и build cache
    if free_mb < needed_mb:
        r.log.warn(
            f"Swap {cfg.swap_mb} MB не создаём: свободно {free_mb} MB, "
            f"нужно {needed_mb} MB (swap + запас на сборку). "
            f"Оставляем текущие {current} MB."
        )
        return

    if current > 0:
        r.log.info(f"Swap есть ({current} MB), но меньше {cfg.swap_mb} MB — пересоздаём")
    else:
        r.log.info("swap не настроен — создаём")

    # swapoff перед пересозданием: mkswap на активном файле не сработает.
    # fallocate быстрее dd, но на некоторых ФС (zfs, старые ext4) не работает —
    # поэтому fallback на dd.
    r.run(
        f"set -e; "
        f"swapoff /swapfile 2>/dev/null || true; "
        f"rm -f /swapfile; "
        f"fallocate -l {cfg.swap_mb}M /swapfile 2>/dev/null || "
        f"dd if=/dev/zero of=/swapfile bs=1M count={cfg.swap_mb} status=none; "
        f"chmod 600 /swapfile; "
        f"mkswap /swapfile >/dev/null; "
        f"swapon /swapfile",
        timeout=300,
    )

    # fstab — только если записи ещё нет (идемпотентность)
    r.run(
        "grep -q '^/swapfile' /etc/fstab || "
        "echo '/swapfile none swap sw 0 0' >> /etc/fstab",
        timeout=60,
    )
    # swappiness=10: swap — страховка от OOM, а не основной механизм
    r.run(
        "grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf; "
        "sysctl -q vm.swappiness=10",
        timeout=60,
    )
    r.log.ok(f"Swap {cfg.swap_mb} MB включён, прописан в /etc/fstab")


def step_clone(r: Remote, cfg: DeployConfig) -> None:
    r.log.step("4/8", f"Репозиторий в {cfg.remote_dir}")

    if cfg.source == "local":
        r.log.info("Режим local: заливаем рабочую копию, git на сервере не нужен")
        _upload_tree(r, Path(__file__).resolve().parent, cfg.remote_dir)
        r.log.ok("Файлы проекта загружены")
        files = int(r.read(f"find {shlex.quote(cfg.remote_dir)} -type f | wc -l") or 0)
        r.log.info(f"Файлов на сервере: {files}")
        return

    if r.exists(posixpath.join(cfg.remote_dir, ".git")):
        r.log.info("Репозиторий найден — обновляем")
        r.run(f"cd {shlex.quote(cfg.remote_dir)} && git fetch --prune origin", timeout=300)
        # reset --hard: состояние сервера приводится к origin, локальных
        # правок на сервере быть не должно (всё живёт в git)
        r.run(
            f"cd {shlex.quote(cfg.remote_dir)} && "
            f"git checkout -q {shlex.quote(cfg.branch)} && "
            f"git reset --hard -q origin/{shlex.quote(cfg.branch)}",
            timeout=300,
        )
        r.log.ok(f"Обновлено до origin/{cfg.branch}")
    else:
        r.log.info("Клонируем")
        r.run(f"mkdir -p {shlex.quote(posixpath.dirname(cfg.remote_dir))}", timeout=60)
        r.run(
            f"git clone --branch {shlex.quote(cfg.branch)} --depth 1 "
            f"{shlex.quote(cfg.repo_url)} {shlex.quote(cfg.remote_dir)}",
            timeout=600,
        )
        r.log.ok("Склонировано")

    commit = r.read(f"cd {shlex.quote(cfg.remote_dir)} && git log -1 --format='%h %s'")
    r.log.info(f"Коммит: {commit}")


# Что не отправляем на сервер в режиме local: кеши, venv, локальные данные
_LOCAL_EXCLUDE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "htmlcov", ".idea", ".vscode",
    "node_modules", "logs", "data",
}
_LOCAL_EXCLUDE_FILES = {".DS_Store", ".env", ".env.production"}


def _upload_tree(r: Remote, local_root: Path, remote_root: str) -> None:
    """Рекурсивно залить проект по SFTP, сохраняя структуру каталогов."""
    if r.dry_run:
        r.log.info(f"dry-run: загрузка {local_root} → {remote_root}")
        return

    assert r._sftp is not None
    r.run(f"mkdir -p {shlex.quote(remote_root)}", quiet=True)

    dirs: list[str] = []
    count = 0
    for path in sorted(local_root.rglob("*")):
        rel = path.relative_to(local_root)
        if any(part in _LOCAL_EXCLUDE_DIRS for part in rel.parts):
            continue
        if path.name in _LOCAL_EXCLUDE_FILES:
            continue

        remote_path = posixpath.join(remote_root, rel.as_posix())
        if path.is_dir():
            r.run(f"mkdir -p {shlex.quote(remote_path)}", quiet=True)
            dirs.append(remote_path)
        elif path.is_file():
            r.run(f"mkdir -p {shlex.quote(posixpath.dirname(remote_path))}", quiet=True)
            r._sftp.put(str(path), remote_path)
            count += 1

    r.log.info(f"Загружено файлов: {count}")


def step_configs(r: Remote, cfg: DeployConfig) -> None:
    r.log.step("5/8", "Конфигурация")

    env_path = posixpath.join(cfg.remote_dir, ".env.production")
    if r.exists(env_path):
        r.log.ok(".env.production уже существует — секреты сохранены")
    else:
        r.put(env_path, render_env_production(cfg), mode=0o600)
        r.log.ok(".env.production создан (секреты сгенерированы)")

    # Локальные версии конфигов могут быть новее, чем в последнем коммите —
    # заливаем их, чтобы деплой не зависел от пуша.
    local_root = Path(__file__).resolve().parent
    uploads = [
        ("docker-compose.prod.yml", "docker-compose.prod.yml"),
        ("prometheus.prod.yml", "prometheus.prod.yml"),
    ]
    for local_rel, remote_rel in uploads:
        local = local_root / local_rel
        if local.exists():
            r.upload(local, posixpath.join(cfg.remote_dir, remote_rel))
    r.log.ok("compose и prometheus-конфиг обновлены")

    for required in ("docker-compose.prod.yml", "Dockerfile", "alembic.ini"):
        local_file = local_root / required
        if not local_file.exists():
            raise RemoteError(f"В локальной копии проекта нет {required}")
    r.log.ok("Обязательные файлы на месте")


def step_nginx(r: Remote, cfg: DeployConfig) -> None:
    if cfg.skip_nginx:
        r.log.step("6/8", "nginx — пропущено (--skip-nginx)")
        return

    r.log.step("6/8", "nginx")

    rc, _, _ = r.run("command -v nginx >/dev/null 2>&1", check=False, quiet=True)
    if rc == 0:
        r.log.ok(f"nginx установлен: {r.read('nginx -v 2>&1')}")
    else:
        r.run("apt-get update -qq", timeout=600)
        r.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx",
            timeout=600,
        )
        r.log.ok("nginx установлен")

    local_root = Path(__file__).resolve().parent
    site_src = local_root / "deploy" / "nginx.conf"
    proxy_src = local_root / "deploy" / "nginx-proxy.conf"
    if not site_src.exists() or not proxy_src.exists():
        raise RemoteError("Не найдены deploy/nginx.conf или deploy/nginx-proxy.conf")

    r.run("mkdir -p /etc/nginx/snippets", timeout=60)
    r.upload(proxy_src, "/etc/nginx/snippets/picnest-proxy.conf", mode=0o644)

    # Конфиг сайта не перезаписываем, если его уже правил certbot: иначе
    # повторный деплой сотрёт listen 443 и пути к сертификатам.
    site_path = "/etc/nginx/sites-available/picnest"
    certbot_managed = False
    if r.exists(site_path):
        rc, _, _ = r.run(
            f"grep -q 'managed by Certbot' {shlex.quote(site_path)}",
            check=False,
            quiet=True,
        )
        certbot_managed = rc == 0

    if certbot_managed:
        r.log.ok("Конфиг nginx управляется certbot — не трогаем")
    else:
        r.upload(site_src, site_path, mode=0o644)

    r.run(
        "ln -sfn /etc/nginx/sites-available/picnest /etc/nginx/sites-enabled/picnest",
        timeout=60,
    )
    # default-сайт перехватывает запросы по IP через server_name _
    if r.exists("/etc/nginx/sites-enabled/default"):
        r.run("rm -f /etc/nginx/sites-enabled/default", timeout=60)
        r.log.info("Отключён sites-enabled/default")

    rc, out, err = r.run("nginx -t", check=False, timeout=120)
    if rc != 0:
        raise RemoteError(f"nginx -t провалился:\n{err or out}")
    r.log.ok("Конфигурация валидна")

    r.run("systemctl enable --now nginx", timeout=120)
    r.run("systemctl reload nginx", timeout=120)
    r.log.ok("nginx запущен и перезагружен")


def step_deploy(r: Remote, cfg: DeployConfig) -> None:
    r.log.step("7/8", "Сборка и запуск стека")

    project = f"cd {shlex.quote(cfg.remote_dir)} && "

    if cfg.skip_build:
        r.run(project + "docker compose -f docker-compose.prod.yml --env-file .env.production up -d", timeout=1200)
        r.log.ok("Контейнеры подняты без пересборки")
        return

    # --build: пересобрать образ из текущего кода
    r.run(
        project
        + "docker compose -f docker-compose.prod.yml --env-file .env.production "
        "up -d --build --remove-orphans",
        timeout=3600,  # 1 vCPU: сборка python-образа может идти 10+ минут
    )
    r.log.ok("Стек собран и запущен")


def step_health(r: Remote, cfg: DeployConfig) -> None:
    r.log.step("8/8", "Проверка работоспособности")

    project = f"cd {shlex.quote(cfg.remote_dir)} && "

    # Ждём /health через nginx (то есть проверяем весь путь, а не только app)
    healthy = False
    for attempt in range(1, 21):
        rc, out, _ = r.run(
            "curl -fsS --max-time 5 http://127.0.0.1/health",
            check=False,
            quiet=True,
        )
        if rc == 0:
            healthy = True
            r.log.ok(f"/health отвечает: {out.strip()[:200]}")
            break
        r.log.info(f"попытка {attempt}/20 — ещё не готово")
        if not cfg.dry_run:
            time.sleep(6)

    if not healthy:
        r.log.fail("/health не ответил за 2 минуты")
        for svc in ("app", "migrate", "db", "redis"):
            _, logs, _ = r.run(
                project
                + f"docker compose -f docker-compose.prod.yml --env-file .env.production "
                  f"logs --tail 25 {svc}",
                check=False,
                quiet=True,
            )
            if logs.strip():
                r.log.info(f"--- последние строки {svc} ---")
                print(textwrap.indent(logs.strip()[-3000:], "      "))
        # ps тоже требует --env-file: без него compose падает на интерполяции
        # ${POSTGRES_PASSWORD} и вместо статуса печатает ошибку.
        _, ps, _ = r.run(
            project + "docker compose -f docker-compose.prod.yml --env-file .env.production ps",
            check=False,
            quiet=True,
        )
        if ps.strip():
            r.log.info("--- статус контейнеров ---")
            print(textwrap.indent(ps.rstrip(), "      "))
        raise RemoteError("Приложение не прошло health check")

    # Статус контейнеров
    _, ps, _ = r.run(
        project + "docker compose -f docker-compose.prod.yml --env-file .env.production ps",
        check=False,
        quiet=True,
    )
    print()
    print(textwrap.indent(ps.rstrip(), "    "))

    # Освобождаем место: на 10 GB диске build cache быстро копится
    r.run("docker image prune -f >/dev/null 2>&1 || true", check=False, quiet=True)
    r.run("docker builder prune -f --filter until=24h >/dev/null 2>&1 || true", check=False, quiet=True)
    avail = r.read("df -Pk / | awk 'NR==2 {printf \"%d\", $4/1024/1024}'")
    r.log.info(f"Свободно после сборки: {avail} GB")


# ============================================================================
# CLI
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Деплой PicNest на VPS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            примеры:
              %(prog)s --host 83.141.67.249 --user root --key ~/.ssh/id_ed25519
              %(prog)s --host 1.2.3.4 --user deploy --key ~/.ssh/id_ed25519 --domain api.picnest.ru
              %(prog)s --host 1.2.3.4 --user root --dry-run
            """
        ),
    )
    p.add_argument("--host", required=True, help="IP или домен сервера")
    p.add_argument("--user", default="root", help="пользователь SSH (по умолчанию root)")
    p.add_argument("--port", type=int, default=22, help="порт SSH (по умолчанию 22)")
    auth = p.add_mutually_exclusive_group()
    auth.add_argument("--key", help="путь к приватному ключу (например ~/.ssh/id_ed25519)")
    auth.add_argument(
        "--password-from-env",
        metavar="VAR",
        help="взять пароль SSH из переменной окружения VAR (не передавайте пароль аргументом — "
        "он попадёт в историю shell и в list процессов)",
    )
    p.add_argument("--dir", default="/opt/picnest", help="каталог на сервере")
    p.add_argument("--repo", default="https://github.com/EgorLiutov22/PicNest.git")
    p.add_argument("--branch", default="main")
    p.add_argument(
        "--source",
        choices=["git", "local"],
        default="git",
        help="git — клонировать/обновлять из репозитория; "
        "local — залить текущую рабочую копию (для деплоя незакоммиченных правок)",
    )
    p.add_argument("--domain", default="", help="домен для CORS и server_name (например api.picnest.ru)")
    p.add_argument("--swap-mb", type=int, default=2048, help="размер swap в MB (0 — не трогать)")
    p.add_argument(
        "--min-disk-gb",
        type=int,
        default=6,
        help="минимальный запас на диске в GB; для перезапуска готового образа "
        "(--skip-build) можно снизить до 2",
    )
    p.add_argument("--skip-nginx", action="store_true", help="не трогать nginx")
    p.add_argument("--skip-build", action="store_true", help="не пересобирать образ, только перезапуск")
    p.add_argument("--dry-run", action="store_true", help="показать команды, ничего не выполняя")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    key_path: Optional[Path] = None
    if args.key:
        key_path = Path(args.key).expanduser()
        if not key_path.exists():
            sys.stderr.write(f"Ключ не найден: {key_path}\n")
            return 2

    password = None
    if args.password_from_env:
        password = os.environ.get(args.password_from_env)
        if not password:
            sys.stderr.write(f"Переменная {args.password_from_env} пуста или не задана\n")
            return 2

    if not key_path and not password:
        # По умолчанию — стандартный ключ, если он есть
        default_key = Path.home() / ".ssh" / "id_ed25519"
        if default_key.exists():
            key_path = default_key
            print(f"{C.DIM}Ключ не указан, используем {default_key}{C.RESET}")
        else:
            sys.stderr.write(
                "Не указан способ аутентификации: --key или --password-from-env\n"
            )
            return 2

    cfg = DeployConfig(
        host=args.host,
        user=args.user,
        port=args.port,
        key_path=key_path,
        password=password,
        remote_dir=args.dir,
        repo_url=args.repo,
        branch=args.branch,
        domain=args.domain,
        dry_run=args.dry_run,
        skip_nginx=args.skip_nginx,
        skip_build=args.skip_build,
        swap_mb=args.swap_mb,
        source=args.source,
        min_disk_gb=args.min_disk_gb,
    )

    log = Log(dry_run=cfg.dry_run)
    r = Remote(
        host=cfg.host,
        user=cfg.user,
        port=cfg.port,
        key_path=cfg.key_path,
        password=cfg.password,
        dry_run=cfg.dry_run,
        log=log,
    )

    print(f"{C.BOLD}PicNest deploy{C.RESET} → {cfg.user}@{cfg.host}:{cfg.port} {cfg.remote_dir}")
    if cfg.dry_run:
        print(f"{C.YELLOW}Режим dry-run: команды только печатаются{C.RESET}")

    try:
        r.connect()
        log.ok("SSH-соединение установлено")

        step_preflight(r, cfg)
        step_install_docker(r, cfg)
        step_docker_mirror(r, cfg)
        if cfg.swap_mb > 0:
            step_swap(r, cfg)
        step_clone(r, cfg)
        step_configs(r, cfg)
        step_nginx(r, cfg)
        step_deploy(r, cfg)
        step_health(r, cfg)

    except paramiko.AuthenticationException:
        print(f"\n{C.RED}Ошибка аутентификации.{C.RESET} Проверьте ключ/пароль и пользователя.")
        return 3
    except paramiko.SSHException as e:
        print(f"\n{C.RED}Ошибка SSH: {e}{C.RESET}")
        return 4
    except RemoteError as e:
        print(f"\n{C.RED}Деплой остановлен:{C.RESET}\n  {e}")
        return 1
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}Прервано пользователем.{C.RESET}")
        return 130
    finally:
        r.close()

    # Итог
    ok = sum(1 for s, _ in log.steps if s == "ok")
    warn = sum(1 for s, _ in log.steps if s == "warn")
    fail = sum(1 for s, _ in log.steps if s == "fail")

    print()
    print(f"{C.BOLD}Готово за {log.elapsed()}{C.RESET}  "
          f"{C.GREEN}{ok} OK{C.RESET}, {C.YELLOW}{warn} предупреждений{C.RESET}, "
          f"{C.RED}{fail} ошибок{C.RESET}")

    if warn:
        print("\nПредупреждения:")
        for status, msg in log.steps:
            if status == "warn":
                print(f"  {C.YELLOW}!{C.RESET} {msg}")

    if not cfg.dry_run and fail == 0:
        print(f"\nПроверить изнутри сервера:  curl -s http://127.0.0.1/health")
        print(f"Проверить снаружи:          curl -s http://{cfg.host}/health")
        print(f"Документация API:           http://{cfg.host}/docs")
        print(f"Логи:                       cd {cfg.remote_dir} && "
              f"docker compose -f docker-compose.prod.yml logs -f app")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
