# Production setup — nginx-периметр и клиентский IP

Документ фиксирует контракт периметра прод-VM, от которого зависит корректность и безопасность режима `CLIENT_IP_SOURCE=x-real-ip`: топологию доверия, референсную копию боевого nginx-конфига и ручные шаги, которые нельзя вывести из репозитория автоматически.

## Топология и инвариант доверия

Единственный ingress в систему — nginx, слушающий `:443` на прод-VM. Порты самого приложения и SIEM-сервиса опубликованы только на loopback (`docker-compose.yml`):

```yaml
127.0.0.1:${APP_PORT:-8000}:8000
127.0.0.1:${SIEM_PORT:-8001}:8001
```

Это значит, что снаружи VM подключиться к приложению или к SIEM-сервису напрямую, минуя nginx, нельзя — сокет слушает только `127.0.0.1`, а не `0.0.0.0`.

На этом факте держится вся модель доверия к клиентскому IP. Приложение в режиме `CLIENT_IP_SOURCE=x-real-ip` безоговорочно доверяет заголовку `X-Real-IP`, потому что единственный, кто может его выставить, — nginx на том же хосте (`proxy_set_header X-Real-IP $remote_addr`, см. референс ниже). Если у запроса появляется путь до приложения в обход nginx, это доверие ломается: клиент присылает `X-Real-IP` сам, и приложение принимает подделанное значение как источник истины — rate limiting по IP (`register:{ip}`, `refresh:{ip}`) и `ip` в security-событиях обходятся тривиально.

**Что конкретно ломает инвариант** (любое из перечисленного достаточно):

- проброшенный наружу порт контейнера (`0.0.0.0:8000:8000` вместо `127.0.0.1:8000:8000`);
- прямой доступ к приложению по IP-адресу VM, минуя доменное имя и nginx;
- ещё один контейнер в той же docker-сети, у которого нет причин ходить через nginx, но есть сетевой доступ к `app:8000`.

**Edge — фильтр, а не замок.** Nginx защищает только тот трафик, который реально через него прошёл; он не создаёт границу сам по себе — границу создаёт то, что альтернативных путей до приложения не существует. Публикация портов на loopback — механизм, которым эта граница сегодня обеспечена; при её проверке смотреть не только на nginx-конфиг, но и на фактическую публикацию портов (`docker compose ps`, `docker-compose.yml`).

```mermaid
flowchart LR
    CL(["клиент, интернет"])
    NG["nginx :443<br/>единственный ingress"]
    APP["app :8000<br/>127.0.0.1 only"]
    SIEM["siem-service :8001<br/>127.0.0.1 only"]

    CL -->|"HTTPS"| NG
    NG -->|"X-Real-IP := $remote_addr"| APP
    NG -->|"/siem/ → :8001/"| SIEM

    CL -.->|"запрещено: нет сетевого пути"| APP

    style NG stroke:#39c5cf
    style APP stroke:#3fb950
    style SIEM stroke:#3fb950
    style CL stroke:#8b949e
```

## Референс nginx-конфига

Ниже — санитизированная копия боевого файла `/etc/nginx/sites-enabled/learnflow` (обычный файл, не симлинк). Плейсхолдеры — вместо `server_name` и путей к TLS-сертификатам; содержимое ключей не переносится и никогда не переносилось. Это копия as-is, снятая read-only с одобрения архитектора, а не желаемое состояние — фактические расхождения с контрактом фиксируются пометками рядом, без предложений «как исправить».

```nginx
server {
    listen 80;
    server_name <SERVER_NAME>;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name <SERVER_NAME>;

    ssl_certificate     <PATH_TO_CERT>;
    ssl_certificate_key <PATH_TO_KEY>;

    location = /health {
        proxy_pass http://127.0.0.1:8000/health;
    }

    location /siem/ {
          proxy_pass http://127.0.0.1:8001/;
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
          proxy_set_header X-Forwarded-Proto $scheme;
      }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
    }
}
```

Элементы контракта, на которые опирается приложение:

- **`proxy_set_header X-Real-IP $remote_addr`** в `location /` — это **замена** заголовка целиком, не дописывание. Присланный клиентом `X-Real-IP` уничтожается nginx до того, как запрос дойдёт до приложения; в значении, которое видит `get_client_ip()`, нет ни одного байта, подконтрольного клиенту.
- **`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`** — nginx дописывает `$remote_addr` в конец существующего значения. Заголовок остаётся в конфиге для форензики и ручной отладки, но кодом приложения не читается ни в одном режиме, кроме явного `CLIENT_IP_SOURCE=x-forwarded-for` (см. ниже).
- **`location = /health` не ставит ни одного `proxy_set_header`.** Health-запросы, прошедшие через nginx, приходят без `X-Real-IP` и без `X-Forwarded-For` — факт, а не недосмотр: `get_client_ip()` для health-пути IP не резолвит и WARNING не пишет вообще (см. `app.infra.client_ip.is_health_path`), поэтому отсутствие заголовков здесь безопасно.
- **`location /siem/` срезает префикс**: `proxy_pass http://127.0.0.1:8001/` с завершающим слэшем переписывает `/siem/<путь>` в `/<путь>` на upstream. Факт с VM: при выключенном SIEM-сервисе (`COMPOSE_PROFILES` без `siem`, upstream не поднят) этот location отдаёт `502 Bad Gateway` — фиксируется здесь как наблюдаемое поведение, без рекомендации, что с этим делать.

**Дрейф `sites-available` vs `sites-enabled`.** На прод-VM `/etc/nginx/sites-available/learnflow` расходится с боевым `sites-enabled/learnflow` — в `available` лежит устаревшая топология (фронтенд на `:3000`, префикс `/api/`, `location /api/health`). Это повторный дрейф: та же пара файлов уже расходилась и была синхронизирована вручную ранее (зафиксировано в `doc/tasks/iterations/production/chore-001-ci-cd/summary.md`, находка 5), и `sites-enabled/learnflow` уже тогда оказался обычным файлом, а не симлинком на `sites-available`. Поскольку симлинк не восстановлен, конфиги продолжают жить независимо и снова разошлись. Ручной шаг по приведению в порядок — в runbook ниже.

## Режимы `CLIENT_IP_SOURCE` в эксплуатации

`CLIENT_IP_SOURCE` называет источник клиентского IP явно, а не переключает булев «доверяем прокси». Единственная точка чтения — `app.infra.client_ip.get_client_ip()`; подробности реализации и fallback-поведения — в `doc/tech/conventions.md` § Logging Conventions → Security Event Logging.

- **`socket` (дефолт).** `request.client.host` — адрес TCP-соединения, каким его видит приложение. Дефолт безопасен именно потому, что не доверяет ни одному заголовку: там, где прокси нет (`make dev`, тесты), это настоящий IP клиента; там, где прокси есть, а `CLIENT_IP_SOURCE` не выставлен, — это адрес nginx-контейнера (или docker-gateway), и все клиенты схлопываются в один rate-limit-бакет. Отказ в таком виде шумный и заметен сразу, а не тихая дыра — поэтому дефолт остался безопасным даже для развёртывания без явной настройки.
- **`x-real-ip` (прод).** Значение заголовка `X-Real-IP` целиком, без парсинга списка. Безопасность режима держится **только** на инварианте выше: единственный, кто пишет этот заголовок, — nginx на loopback-адресе. Если заголовка нет или он пуст, `get_client_ip()` откатывается на `socket` и пишет WARNING — это сигнал дрейфа nginx-конфига (например, кто-то убрал `proxy_set_header X-Real-IP` из `location /`), а не штатный путь.
- **`x-forwarded-for`.** Берёт `CLIENT_IP_XFF_HOPS`-й элемент справа (при `hops=1` — последний, дописанный ближайшим прокси). Известное ограничение: фиксированный отступ справа корректен только тогда, когда **весь** трафик идёт одним путём с одинаковым числом дописывающих прокси. При смешанных точках входа — например, часть трафика приходит через CDN или балансировщик, а часть напрямую на nginx, — запросы короткого пути содержат меньше настоящих элементов, и отступ `N` попадает внутрь части заголовка, подконтрольной клиенту: дыра открывается заново и молча. У этой топологии смешанность уже есть в мелком виде — `location = /health` вообще не проставляет `X-Forwarded-For`. Общего решения «всегда верно при любых точках входа» не существует: переход на этот режим требует либо единственной точки входа для всего трафика, либо явного списка доверенных прокси-адресов (которых в текущей топологии нет — в docker источником оказался бы плавающий gateway bridge-сети).

## Runbook ручных шагов на прод-VM

Оба раздела ниже привязаны к моменту **до merge PR в `main`**: `.github/workflows/deploy.yml` реагирует на push в `main` и сразу выполняет `git pull && docker compose build && docker compose up -d` без паузы на ручную подготовку. Окно между merge и подготовленной VM означает прод, поднятый с дефолтами репозитория, — в части клиентского IP это `CLIENT_IP_SOURCE=socket`, то есть все клиенты схлопываются в один rate-limit-бакет.

Раздел разбит по подсистемам периметра; шаги новых подсистем добавляются как отдельные подзаголовки, не переписывая существующие.

### Клиентский IP

Выполнить на прод-VM до merge PR, вводящего `CLIENT_IP_SOURCE`, в `main`:

1. Открыть боевой `.env` в `~/learnflow-ai/` (файл вне git, правится руками) и добавить строку `CLIENT_IP_SOURCE=x-real-ip`. `CLIENT_IP_XFF_HOPS` не трогать — режим `x-real-ip` его не читает.
2. Сверить в `/etc/nginx/sites-enabled/learnflow`, что `location /` содержит `proxy_set_header X-Real-IP $remote_addr` без изменений (см. референс выше). Если строки нет или заголовок не заменяется, а дописывается, — режим `x-real-ip` небезопасен, включать его нельзя до исправления nginx-конфига.
3. Привести пару `sites-available` / `sites-enabled` в порядок, не потеряв боевой конфиг. Источник истины — `/etc/nginx/sites-enabled/learnflow` (обычный файл, содержимое которого нигде больше не хранится: в репозитории его нет, в `sites-available` лежит устаревшая версия). Поэтому сначала снимается резервная копия и содержимое переносится в `sites-available`, и только потом файл в `sites-enabled` заменяется симлинком:

   ```bash
   cp /etc/nginx/sites-enabled/learnflow /root/learnflow.nginx.bak
   cp /etc/nginx/sites-enabled/learnflow /etc/nginx/sites-available/learnflow
   rm /etc/nginx/sites-enabled/learnflow
   ln -s ../sites-available/learnflow /etc/nginx/sites-enabled/learnflow
   ```

   Второй `cp` перезаписывает устаревшее содержимое `sites-available` боевым — это и есть синхронизация; симлинк после неё указывает на файл с тем же содержимым, что работало до правки. Выбранную дисциплину синхронизации (единственный файл в `sites-available` + симлинк из `sites-enabled`) зафиксировать здесь же при следующей правке этого документа.
4. Проверить и применить конфиг — обязательный завершающий шаг после **любой** правки nginx на VM, включая шаг 3:

   ```bash
   nginx -t && systemctl reload nginx
   ```

   `nginx -t` разбирает конфиг и не даёт применить сломанный (при ошибке `reload` не выполнится из-за `&&`, а nginx продолжит работать на старом конфиге). Именно `reload`, а не `restart`: reload поднимает новые worker'ы и даёт старым дожить свои соединения, restart рвёт живые запросы, включая открытые SSE-стримы. Если `nginx -t` ругается — восстановить конфиг из резервной копии (`cp /root/learnflow.nginx.bak /etc/nginx/sites-available/learnflow`) и разобраться до применения.
5. После деплоя (`docker compose up -d` из `deploy.yml`) проверить, что переменная действительно попала в контейнер: `docker compose exec app env | grep CLIENT_IP_SOURCE` должен показать `x-real-ip`.

## Related docs

- [tech/conventions.md](../conventions.md) § Logging Conventions → Security Event Logging — правило единственной точки чтения клиентского IP.
- [tech/security-events.md](../security-events.md) — поле `ip` в каталоге security-событий.
- [tech/setup/codex-cloud.md](codex-cloud.md) — соседний setup-мануал, cloud-окружение.
