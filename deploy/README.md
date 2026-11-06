# PicNest — деплой на VPS

Инструкция по развёртыванию FastAPI-приложения на Ubuntu 22.04/24.04.

## Состав

| Файл | Назначение |
|---|---|
| `deploy.py` | Скрипт деплоя по SSH (основной инструмент) |
| `docker-compose.prod.yml` | Production-стек: app, db, redis, prometheus, grafana, migrate |
| `.env.production.example` | Шаблон переменных окружения |
| `deploy/nginx.conf` | Конфиг сайта nginx (хост) |
| `deploy/nginx-proxy.conf` | Общие настройки проксирования (snippet) |
| `deploy/check_server.sh` | Проверка готовности сервера (без изменений) |
| `alembic/`, `alembic.ini` | Миграции схемы БД |
| `requirements-deploy.txt` | Зависимости самого скрипта деплоя |

## Установка зависимостей

Скрипту нужен только `paramiko`:

```bash
python -m venv .venv-deploy
source .venv-deploy/bin/activate      # Windows: .venv-deploy\Scripts\activate
pip install -r requirements-deploy.txt
```

## Первый деплой

```bash
# с ключом (рекомендуется)
python deploy.py --host 83.141.67.249 --user root --key ~/.ssh/id_ed25519

# если ключа на сервере ещё нет — по паролю из переменной окружения
export PICNEST_SSH_PASSWORD='...'
python deploy.py --host 83.141.67.249 --user root --password-from-env PICNEST_SSH_PASSWORD
```

Пароль передаётся **только** через переменную окружения: аргумент командной строки
виден в `ps` и попадает в историю shell.

Полезные флаги:

```bash
--domain api.picnest.ru   # пропишет домен в CORS и server_name
--dir /opt/picnest        # каталог на сервере
--swap-mb 2048            # размер swap (0 — не трогать)
--skip-nginx              # не настраивать nginx
--skip-build              # перезапуск без пересборки образа
--source local            # залить рабочую копию вместо git clone
--dry-run                 # показать команды, ничего не выполняя
```

`--source local` нужен, когда правки ещё не запушены в GitHub: скрипт заливает
текущий каталог по SFTP и собирает образ из него. Для обычной работы
используйте `--source git` (по умолчанию) — сервер сам обновится из репозитория.

### Что делает скрипт

1. Проверяет ОС, диск (минимум 6 GB), память, Docker и Compose v2.
2. Ставит Docker, если его нет.
3. Настраивает swap (по умолчанию 2 GB) — на VPS с 4 GB RAM без swap сборка
   может упасть по OOM.
4. Клонирует или обновляет репозиторий.
5. Создаёт `.env.production` со случайными паролями — **только если файла нет**.
6. Устанавливает nginx, раскладывает конфиг и snippet, проверяет `nginx -t`.
7. Собирает и поднимает стек; отдельный one-shot контейнер `migrate` накатывает
   `alembic upgrade head` до старта приложения.
8. Ждёт `/health` (через nginx, то есть проверяет весь путь), печатает статус
   контейнеров и чистит docker-кеш.

## Проверка

```bash
# на сервере
curl -s http://127.0.0.1/health
curl -s http://127.0.0.1/docs -o /dev/null -w '%{http_code}\n'

# снаружи
curl -s http://83.141.67.249/health

# состояние контейнеров
ssh root@83.141.67.249 'cd /opt/picnest && docker compose -f docker-compose.prod.yml ps'

# логи
ssh root@83.141.67.249 'cd /opt/picnest && docker compose -f docker-compose.prod.yml logs -f app'
```

Ожидаемый ответ `/health`:

```json
{"status":"healthy","version":"1.0.0","timestamp":"...","database_status":"connected"}
```

Если `database_status` не `connected` — приложение живо, но потеряло БД.

## Обновление проекта

```bash
# после git push в main
python deploy.py --host 83.141.67.249 --user root --key ~/.ssh/id_ed25519

# если менялись только переменные окружения — без пересборки
python deploy.py --host 83.141.67.249 --user root --key ~/.ssh/id_ed25519 --skip-build
```

Скрипт идемпотентен: секреты в `.env.production` сохраняются, повторные
`apt install` и настройка swap не дублируются.

### Новая миграция БД

Локально:

```bash
alembic revision --autogenerate -m "add something"
alembic upgrade head        # проверить на локальной БД
git add alembic/versions/ && git commit && git push
```

На сервере миграции применяются автоматически при следующем деплое.
Вручную:

```bash
ssh root@83.141.67.249 'cd /opt/picnest && docker compose -f docker-compose.prod.yml run --rm migrate'
```

## Доступ к Grafana

Порт наружу не публикуется. Используйте SSH-туннель:

```bash
ssh -L 3000:127.0.0.1:3000 root@83.141.67.249
```

Затем откройте Grafana на сервере — см. `GF_SERVER_ROOT_URL` в
`docker-compose.prod.yml`. Логин `admin`, пароль — `GRAFANA_ADMIN_PASSWORD`
из `/opt/picnest/.env.production`.

## SSL через certbot

Домен должен уже указывать A-записью на IP сервера — иначе проверка не пройдёт.

```bash
ssh root@83.141.67.249
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d api.picnest.ru -d www.api.picnest.ru
```

Certbot сам добавит в конфиг `listen 443 ssl`, пути к сертификатам и редирект
с 80 на 443. Проверка автопродления:

```bash
certbot renew --dry-run
```

После получения HTTPS обновите CORS — иначе браузер заблокирует запросы с
фронтенда. В `/opt/picnest/.env.production`:

```
CORS_ALLOWED_ORIGINS=https://picnest.ru,https://www.picnest.ru
```

и перезапустите приложение:

```bash
cd /opt/picnest && docker compose -f docker-compose.prod.yml up -d app
```

## Безопасность

- `.env.production` создаётся с правами `600` и не попадает в git.
- Порт приложения опубликован только на `127.0.0.1` — снаружи виден лишь nginx.
- `db`, `redis`, `prometheus` доступны исключительно внутри docker-сети.
- nginx закрывает `/metrics`, скрытые файлы и служебные расширения, ограничивает
  частоту запросов (общую и отдельно на login/register).

После настройки входа по ключу отключите парольный доступ:

```bash
# ~/.ssh/authorized_keys должен содержать ваш ключ, затем:
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh
```

## Диагностика

```bash
# проверить сервер перед деплоем
bash deploy/check_server.sh

# контейнер не стартует
cd /opt/picnest && docker compose -f docker-compose.prod.yml logs --tail 50 app

# миграции не применились
cd /opt/picnest && docker compose -f docker-compose.prod.yml logs migrate

# 502 от nginx — приложение не слушает 8000
curl -sv http://127.0.0.1:8000/health

# свободное место
df -h / && docker system df
```

На сервере с диском 10 GB место заканчивается быстро. `deploy.py` чистит
build cache после каждой сборки, но при регулярных деплоях стоит расширить
диск у провайдера.
