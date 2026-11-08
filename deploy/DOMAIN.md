# Подключение домена к PicNest

Инструкция для текущей конфигурации: фронтенд и API на одном сервере
(`176.124.223.199`), nginx на хосте, приложение в Docker.

Схема после настройки:

```
пользователь → https://picnest.ru  → nginx :443 → статика SPA
                                              → /api/ → FastAPI :8000
```

Фронтенд и API остаются на одном origin, поэтому CORS не нужен.

---

## 1. Выбрать имена

| Что | Пример | Куда смотрит |
|---|---|---|
| Основной сайт | `picnest.ru`, `www.picnest.ru` | A-запись на IP сервера |
| API (опционально) | `api.picnest.ru` | A-запись на тот же IP |

**Рекомендую начать с одного домена** `picnest.ru` + `www`: API доступен по
`https://picnest.ru/api/v1/...`, отдельный поддомен не нужен. Меньше
сертификатов, не нужен CORS, проще отладка.

Отдельный `api.picnest.ru` имеет смысл, если позже появится мобильное
приложение или второй фронтенд.

---

## 2. Настроить DNS у регистратора

В панели управления доменом создайте записи:

```
A     @                176.124.223.199
A     www              176.124.223.199
```

Если нужен поддомен для API:

```
A     api              176.124.223.199
```

Если провайдер поддерживает IPv6 — добавьте `AAAA` с IPv6 сервера.

**Проверка (подождите 5–30 минут, иногда до нескольких часов):**

```bash
dig +short picnest.ru
dig +short www.picnest.ru
```

Должен вернуться `176.124.223.199`. Пока DNS не обновился, certbot
работать не будет — он проверяет домен по HTTP.

Проверить распространение по миру: https://dnschecker.org

---

## 3. Указать домен в nginx

Сейчас в конфиге стоит `server_name _;` — это заглушка, которая ловит
любой запрос по IP. Меняем на реальное имя.

Файл на сервере: `/etc/nginx/sites-available/picnest`

```nginx
server {
    listen 80;
    listen [::]:80;

    server_name picnest.ru www.picnest.ru;   # ← вместо _

    root /var/www/picnest-front;
    ...
}
```

**Важно:** в репозитории этот же файл лежит в
`PicNest/deploy/nginx-front.conf`. Чтобы правка не потерялась при
следующем деплое, обновите его там же — иначе `deploy.py` перезапишет
серверный конфиг (он не трогает файл только если тот управляется
certbot, см. п. 5).

Применить:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Проверка без HTTPS:

```bash
curl -H "Host: picnest.ru" http://127.0.0.1/ -o /dev/null -w '%{http_code}\n'
```

Ожидается `200`.

---

## 4. Обновить CORS и переменные окружения

Так как фронтенд и API на одном origin, CORS для браузера не нужен. Но
он пригодится, если появится отдельный клиент (мобильное приложение,
второй домен).

Файл на сервере: `/opt/picnest/.env.production`

```bash
CORS_ALLOWED_ORIGINS=https://picnest.ru,https://www.picnest.ru
```

Если добавляли поддомен API — перечислите оба:

```bash
CORS_ALLOWED_ORIGINS=https://picnest.ru,https://www.picnest.ru,https://api.picnest.ru
```

Правила, которые стоит помнить:

- **Не используйте `*`** — вместе с `allow_credentials` это открывает
  CORS полностью.
- **Без пробелов после запятой.** Код теперь обрезает пробелы, но
  лучше не полагаться на это.
- **Только `https://`**, если включите HSTS — иначе браузер заблокирует
  HTTP-запросы.

Применить:

```bash
cd /opt/picnest
docker compose -f docker-compose.prod.yml --env-file .env.production up -d app
```

---

## 5. Получить сертификат Let's Encrypt

**certbot на сервере ещё не установлен.** Ставим и запускаем:

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx

sudo certbot --nginx -d picnest.ru -d www.picnest.ru
```

Флаги, которые спросит мастер:

| Вопрос | Что выбрать |
|---|---|
| Email | рабочий адрес — на него придут уведомления об истечении |
| Согласие с условиями | `A` (Agree) |
| Рассылка | по желанию |
| Redirect HTTP → HTTPS | **`2` (Redirect)** — весь HTTP-трафик уйдёт на HTTPS |

Certbot сам:

- добавит `listen 443 ssl` и пути к сертификатам;
- вставит блок `managed by Certbot` — по нему `deploy.py` понимает,
  что конфиг трогать нельзя;
- добавит редирект с 80 на 443.

Если нужен поддомен API:

```bash
sudo certbot --nginx -d api.picnest.ru
```

**Проверка:**

```bash
curl -I https://picnest.ru
curl https://picnest.ru/health
```

Ожидается `200` и `{"status":"healthy",...}`.

---

## 6. Проверить автопродление

Сертификат Let's Encrypt живёт 90 дней. Certbot ставит таймер, который
продлевает его автоматически, но проверить стоит:

```bash
sudo certbot renew --dry-run
sudo systemctl list-timers | grep certbot
```

Если таймера нет — добавьте cron:

```bash
echo "0 3 * * * certbot renew --quiet --deploy-hook 'systemctl reload nginx'" \
  | sudo tee /etc/cron.d/certbot-renew
```

`--deploy-hook` обязателен: без перезагрузки nginx продолжит отдавать
старый сертификат до ручного рестарта.

---

## 7. Включить HSTS (после того как HTTPS заработал)

**Только когда убедились, что HTTPS работает и автопродление настроено.**
HSTS заставляет браузер обращаться к сайту только по HTTPS в течение
указанного срока — отменить это досрочно нельзя.

В `/etc/nginx/sites-available/picnest`, внутри `server` с `listen 443`:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

Начните с короткого срока, чтобы можно было откатиться:

```nginx
add_header Strict-Transport-Security "max-age=300" always;
```

Через несколько дней без проблем увеличьте до года.

⚠️ `includeSubDomains` примен��тся ко **всем** поддоменам. Если какой-то
из них работает по HTTP — сначала переведите его на HTTPS.

---

## 8. Обновить фронтенд

`VITE_API_BASE_URL` вшивается в бандл **на этапе сборки**. Сейчас там
относительный путь `/api/v1` — он работает при любом домене, менять
ничего не нужно:

```bash
cd picnest_front
cat .env.production
# VITE_API_BASE_URL=/api/v1
```

Если бы там был абсолютный URL (`https://api.picnest.ru/api/v1`),
потребовалась бы пересборка и повторный деплой.

---

## 9. Закрыть доступ по IP (опционально)

После переключения на домен сервер продолжает отвечать по IP. Можно
запретить:

```nginx
server {
    listen 80 default_server;
    server_name _;
    return 444;   # закрыть соединение без ответа
}
```

Или ограничить API-эндпоинты только доменом. Не обязательно, но
уменьшает поверхность атаки и убирает дубли страниц для поисковиков.

---

## 10. Чек-лист

```
[ ] A-записи созданы, dig возвращает IP сервера
[ ] server_name изменён в nginx и в deploy/nginx-front.conf
[ ] nginx -t проходит, конфиг перезагружен
[ ] CORS_ALLOWED_ORIGINS обновлён, приложение перезапущено
[ ] certbot --nginx отработал, сертификат получен
[ ] https://домен открывается, редирект с HTTP работает
[ ] https://домен/health отвечает healthy
[ ] https://домен/api/v1/orders отвечает 401 (значит API доступен)
[ ] /docs открывается и Swagger грузится
[ ] certbot renew --dry-run проходит
[ ] HSTS включён (с коротким max-age)
[ ] фронтенд работает: вход, список заказов
```

---

## Типичные проблемы

**`certbot` падает: «Could not verify domain»**
DNS ещё не обновился, или A-запись указывает на другой IP. Проверьте
`dig +short домен`. Также убедитесь, что порт 80 открыт и nginx
отвечает на этот домен.

**`certbot` падает: «challenge failed»**
Другой сервер отвечает на порт 80, или в nginx есть `location`,
перехватывающий `/.well-known/acme-challenge/`. Проверьте:
`curl -I http://домен/.well-known/acme-challenge/test`

**После HTTPS фронтенд не грузит API, в консоли CORS-ошибка**
В `.env.production` остался `http://` вместо `https://`, либо домен не
добавлен в `CORS_ALLOWED_ORIGINS`. Перезапустите `app` после правки.

**`Mixed Content: blocked`**
В бандле зашит `http://` URL. Пересоберите фронтенд с относительным
путём: `VITE_API_BASE_URL=/api/v1`.

**После повторного деплоя пропал HTTPS**
`deploy.py` перезаписал конфиг nginx. Он пропускает файл, только если
находит в нём `managed by Certbot`. Проверьте:
`grep certbot /etc/nginx/sites-available/picnest`

**`502 Bad Gateway`**
Контейнер `app` не запущен или упал. Проверьте:
```bash
cd /opt/picnest
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail 50 app
```
