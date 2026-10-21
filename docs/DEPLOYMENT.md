# PicNest Marketplace API - Deployment Guide

## Обзор

Этот документ описывает процесс развертывания PicNest Marketplace API в production среде.

**Дата обновления:** 2026-10-21  
**Версия документа:** 1.0

---

## Требования к серверу

### Минимальные требования:
- **CPU:** 2 vCPUs
- **RAM:** 4 GB
- **Disk:** 20 GB SSD
- **OS:** Ubuntu 20.04+ или Debian 11+

### Рекомендуемые требования:
- **CPU:** 4 vCPUs
- **RAM:** 8 GB
- **Disk:** 50 GB NVMe SSD
- **OS:** Ubuntu 22.04 LTS

---

## Установка зависимостей на сервер

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker и Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Установка Git
sudo apt install git -y

# Перезагрузка для применения изменений
reboot
```

---

## Настройка переменных окружения

### 1. Создание .env файла

```bash
cd /var/www/picnest-api
cp .env.example .env.production
vim .env.production
```

**Ключевые настройки:**

```bash
# Окружение
ENVIRONMENT=production
DEBUG=false

# База данных
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/picnest_db

# Секретный ключ (ОБЯЗАТЕЛЬНО замените на случайную строку!)
SECRET_KEY=$(openssl rand -base64 64)

# JWT настройки
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
CORS_ALLOWED_ORIGINS=https://picnest.com,https://www.picnest.com

# Sentry (для отслеживания ошибок)
SENTRY_DSN=https://xxx@sentry.io/yyy

# Redis для rate limiting
REDIS_URL=redis://localhost:6379/0

# Prometheus метрики
PROMETHEUS_ENABLED=true
```

### 2. Генерация SECRET_KEY

```bash
# Сгенерируйте случайный секретный ключ
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Или используйте OpenSSL
openssl rand -base64 64
```

---

## Первый деплой

### 1. Клонирование репозитория

```bash
cd /var/www
git clone git@github.com:picnest/picnest.git picnest-api
cd picnest-api
git checkout main
```

### 2. Настройка окружения

```bash
# Создание .env файла
cp .env.example .env.production

# Редактирование переменных окружения
vim .env.production

# Установка прав на файлы
chmod 600 .env.production
```

### 3. Сборка Docker образов

```bash
# Сборка production образа
docker-compose build --no-cache app db redis

# Проверка сборки
docker images | grep picnest
```

### 4. Запуск сервисов

```bash
# Старт всех сервисов
docker-compose -f docker-compose.prod.yml up -d

# Проверка статуса
docker-compose ps
```

### 5. Проверка здоровья

```bash
# Health check endpoint
curl http://localhost:8000/health

# Ожидаемый ответ:
{
    "status": "healthy",
    "version": "1.0.0",
    "timestamp": "2026-10-21T15:30:00Z"
}
```

---

## Обновление приложения

### 1. Pull latest changes

```bash
cd /var/www/picnest-api
git pull origin main
```

### 2. Сборка новых образов

```bash
# Сборка только измененных образов (быстрее)
docker-compose build --no-cache app

# Или полная пересборка
docker-compose build --no-cache
```

### 3. Обновление контейнеров

```bash
# Остановка и удаление старых контейнеров
docker-compose down

# Запуск новых контейнеров
docker-compose up -d

# Проверка логов
docker-compose logs -f app
```

### 4. Rollback (при необходимости)

```bash
# Откат к предыдущей версии
git checkout previous-commit-hash
make docker-build
make docker-up
```

---

## Мониторинг и логи

### Просмотр логов

```bash
# Логи приложения
docker-compose logs -f app

# Логи базы данных
docker-compose logs -f db

# Логи Redis
docker-compose logs -f redis

# Логи всех сервисов
docker-compose logs -f --tail=100
```

### Prometheus метрики

```bash
# Доступ к Prometheus UI
http://localhost:9090

# Query API
curl http://localhost:9090/api/v1/query?query=http_requests_total

# Экспорт метрик приложения
curl http://localhost:8000/metrics
```

### Grafana дашборды

```bash
# Доступ к Grafana UI
http://localhost:3000

# Логин: admin / admin (или из .env)
```

---

## Backup и восстановление

### 1. Создание бэкапа PostgreSQL

```bash
# Полный бэкап базы данных
docker exec picnest-db pg_dump -U picnest_user picnest_db > backup_$(date +%Y%m%d).sql

# Бэкап с сжатием
docker exec picnest-db pg_dump -U picnest_user picnest_db | gzip > backup_$(date +%Y%m%d).sql.gz

# Сохранение бэкапа на удаленный сервер
rsync -avz backup_*.sql.gz user@backup-server:/backups/
```

### 2. Восстановление из бэкапа

```bash
# Остановка приложения
docker-compose down

# Загрузка бэкапа
scp user@backup-server:/backups/backup_20261021.sql.gz .

# Декомпрессия
gunzip backup_*.sql.gz

# Восстановление базы данных
docker exec -i picnest-db psql -U picnest_user picnest_db < backup_20261021.sql

# Запуск приложения
docker-compose up -d
```

### 3. Автоматизация бэкапов (cron)

```bash
# Добавление cron job для ежедневных бэкапов
crontab -e

# Добавить строку:
0 2 * * * cd /var/www/picnest-api && docker exec picnest-db pg_dump -U picnest_user picnest_db | gzip > /backups/backup_$(date +\%Y\%m\%d).sql.gz
```

---

## Security hardening

### 1. Настройка firewall (ufw)

```bash
# Установка ufw
sudo apt install ufw -y

# Разрешение SSH
sudo ufw allow OpenSSH

# Разрешение HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Включение firewall
sudo ufw enable
```

### 2. SSL/TLS сертификаты (Let's Encrypt)

```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx -y

# Получение сертификата
sudo certbot --nginx -d picnest.com -d www.picnest.com

# Автоматическое обновление
sudo certbot renew --dry-run
```

### 3. Настройка Nginx reverse proxy

```nginx
server {
    listen 80;
    server_name picnest.com www.picnest.com;

    # Redirect to HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name picnest.com www.picnest.com;

    ssl_certificate /etc/letsencrypt/live/picnest.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/picnest.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Troubleshooting

### Приложение не запускается

```bash
# Проверка логов
docker-compose logs app

# Проверка health check status
docker inspect picnest-api --format='{{json .State.Health}}' | jq

# Пересборка образа
docker-compose build --no-cache app
```

### База данных недоступна

```bash
# Проверка статуса PostgreSQL
docker exec picnest-db pg_isready -U picnest_user

# Просмотр логов БД
docker-compose logs db

# Перезапуск базы данных
docker-compose restart db
```

### Rate limiting блокирует все запросы

```bash
# Проверка Redis
docker exec picnest-redis redis-cli ping

# Сброс rate limiting для конкретного IP
docker exec -it picnest-redis redis-cli DEL "rate_limit:*"

# Временное отключение rate limiting
docker-compose stop redis
docker-compose up -d app
```

### Высокая нагрузка на CPU/RAM

```bash
# Просмотр использования ресурсов
docker stats

# Ограничение ресурсов в docker-compose.yml:
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 1G
```

---

## Checklist перед деплоем

### Security
- [ ] SECRET_KEY заменен на случайную строку
- [ ] DATABASE_URL содержит надежные учетные данные
- [ ] SENTRY_DSN настроен (для отслеживания ошибок)
- [ ] CORS_ALLOWED_ORIGINS ограничен продакшен доменами
- [ ] DEBUG=false
- [ ] ENVIRONMENT=production
- [ ] SSL/TLS сертификаты установлены
- [ ] Firewall настроен правильно

### Database
- [ ] PostgreSQL установлен и запущен
- [ ] База данных создана
- [ ] Миграции применены
- [ ] Backup стратегия настроена

### Monitoring
- [ ] Prometheus запущен
- [ ] Grafana настроен
- [ ] Alert rules настроены
- [ ] Email/Slack уведомления настроены

### Deployment
- [ ] Docker images собраны и проверены
- [ ] .env.production настроен
- [ ] Nginx reverse proxy настроен
- [ ] Health check endpoints работают
- [ ] Backup script создан и протестирован

---

## Дополнительные ресурсы

- [Docker Documentation](https://docs.docker.com/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Prometheus Getting Started](https://prometheus.io/docs/introduction/overview/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)

---

## Контакты и поддержка

При возникновении проблем с деплоем:
1. Проверьте логи через `docker-compose logs -f`
2. Проконсультируйтесь с разделом Troubleshooting выше
3. Обратитесь в команду поддержки PicNest Backend Team

**Email:** support@picnest.com  
**Slack:** #deployment-support
