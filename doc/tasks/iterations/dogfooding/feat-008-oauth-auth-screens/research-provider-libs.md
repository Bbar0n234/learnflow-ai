# Ресёрч: библиотека OAuth-клиента + политики провайдеров (localhost, модерация)

Выжимка ресёрча при взятии итерации в работу (август 2026). Вход для design-brief: выбор между authlib / альтернативами / ручным провайдер-слоем и схема dev/prod-окружений. Провайдеры: Яндекс ID, VK ID, Google, GitHub (вертикаль сначала на Яндексе).

## Библиотека: authlib vs альтернативы vs руками

### Факты о кандидатах (проверено на август 2026)

**Authlib** — жив и активно развивается: 1.7.2 (май 2026), параллельная патч-ветка 1.6.x, Python 3.10–3.14. В 1.7.0 — миграция JOSE на `joserfc`, контрмера PKCE-downgrade. Штатная Starlette/FastAPI-интеграция (`authlib.integrations.starlette_client.OAuth`): кастомный провайдер конфигом (`authorize_url`, `access_token_url`, `userinfo_endpoint` / `server_metadata_url` для OIDC discovery), PKCE через `client_kwargs={"code_challenge_method": "S256"}` (только S256), id_token валидируется автоматически (JWKS + nonce). По исходникам: `authorize_access_token(request, **kwargs)` пробрасывает kwargs в тело token-запроса, но из callback читает только `code`/`state`/`error` — дополнительные query-параметры (`device_id` VK) извлекать самостоятельно. **Требует `SessionMiddleware`** (state/verifier — в cookie-сессии).

**httpx-oauth** — жив (0.17.0, май 2026, мейнтейнер François Voron), async-native поверх httpx. Встроенные провайдеры: Google, GitHub, Discord, Microsoft и др.; **Яндекса и VK нет**. PKCE не автоматизирован на уровне флоу. По сути тонкие клиенты, не фреймворк флоу.

**requests-oauthlib / oauthlib** — стагнация (2.0.0, март 2024), синхронный стек — не кандидат.

**Полностью руками на httpx.** Криптомеханики: (1) `state` — `secrets.token_urlsafe(32)` + хранение + сравнение; (2) PKCE — `secrets.token_urlsafe(64)` + `base64url(sha256(verifier))` — чистый stdlib; (3) обмен кода — один POST form-urlencoded; (4) JWKS/подпись id_token — **нужна только для валидации id_token Google**; если у всех четырёх брать профиль через userinfo-endpoint по access_token (все четыре позволяют), JWT-криптография не нужна вовсе. Оценка: базовый движок ~150–250 строк + ~30–60 строк конфига/адаптера на провайдера.

### Ложатся ли Яндекс и VK ID в абстракции

**Яндекс ID** — обычный OAuth 2.0 Authorization Code: `https://oauth.yandex.ru/authorize` + `POST https://oauth.yandex.ru/token`, PKCE (S256/plain) и state поддержаны. **Не OIDC**: id_token и discovery нет; профиль — `GET https://login.yandex.ru/info`, заголовок `Authorization: OAuth <token>` (поля `id`, `login`, `default_email`; есть `format=jwt`). Флоу стандартный, известных проблем нет.

**VK ID** — OAuth 2.1-подобный флоу на `id.vk.com`/`id.vk.ru` с четырьмя нестандартностями (официальная API-дока, зеркало id.vk.ru):
1. **PKCE обязателен** (S256), `state` обязателен и минимум 32 символа;
2. в redirect приходит **третий параметр `device_id`**, **обязательный** в теле обмена кода (`POST https://id.vk.ru/oauth2/auth`) и при refresh;
3. **`state` обязателен в теле token-запроса** (нет ни в одном стандартном клиенте);
4. вместо `client_secret` у confidential-приложений — `service_token`; ответ содержит `access_token`/`refresh_token`/`id_token`, но **OIDC discovery и публичного JWKS нет** (`/.well-known/openid-configuration` → 404) — id_token штатно не валидируется; профиль — `POST https://id.vk.ru/oauth2/user_info` (access_token + client_id в теле).

В authlib укладывается «с натяжкой»: PKCE и endpoint'ы конфигом, `device_id`/`state` — руками из query + kwargs, `token_endpoint_auth_method` переопределить. Прецедент: **django-allauth реализовал VK ID как тонкий адаптер (~30 строк переопределений)** над своим generic OAuth2-адаптером (починен в 65.12.1, октябрь 2025). Готовой python-библиотеки «VK ID под FastAPI» нет.

### Рекомендация

**Ручной провайдер-слой на httpx** — внутренняя абстракция `OAuthProvider` (authorize_url builder + token exchange + userinfo mapper). Обоснование:
- Из четырёх провайдеров **двое (Яндекс, VK) — не OIDC**, VK нестандартен в token-обмене. Главная ценность authlib (discovery/JWKS/id_token) сыграла бы только для Google — и там профиль доступен через userinfo без JWT-криптографии.
- «Опасная» криптомеханика (state, PKCE) — 10 строк stdlib; реальная сложность — хранение state/verifier между запросами, которое authlib решает навязыванием `SessionMiddleware` (cookie-сессия) — лишняя сущность для JWT-based SPA-бэкенда.
- httpx уже в зависимостях; ноль новых транзитивных зависимостей.

Fallback: **authlib для всех + ручные kwargs для VK ID** — рабочо; цена — SessionMiddleware, «протекающий» адаптер VK и криптостек ради одного Google. Дробить стек (authlib + полностью ручной VK-клиент) хуже, чем выбрать один подход.

**Решение архитектора: ручной провайдер-слой на httpx.**

## Провайдеры: политика localhost и модерация

| | Яндекс OAuth | VK ID | Google | GitHub OAuth App |
|---|---|---|---|---|
| **localhost в redirect** | Да, `http://localhost[:port]/...` (подтверждено практикой сообщества; доки не запрещают). Плюс «Подставить URL для разработки» → `https://oauth.yandex.ru/verification_code` | Да, но домен `localhost` регистрируется, а сервис должен слушать **порт 80 или 443** — произвольный dev-порт (5173/8000) не работает | Да, явное исключение: «Localhost URIs are exempt», любой порт | Да; рекомендован loopback `127.0.0.1` вместо `localhost`; для loopback **порт может не совпадать** с зарегистрированным |
| **HTTPS** | Прод — https; localhost — http допустим | Прод: https + зарегистрированный базовый домен. Туннели (ngrok и пр.) **блокируются как вредоносные домены** | Обязателен всюду, кроме localhost/loopback | Жёсткого требования в доке нет; прод — https |
| **Модерация / верификация** | Не обязательна: вход работает сразу. Без верификации: ≤5 приложений, предупреждение «непроверенный сервис». Верификация — через Госуслуги | Приложение работает сразу; с 2026 стандартное создание завязано на верификацию «бизнес»-профиля, но физлицо может подключить VK ID из личного кабинета (уверенность средняя — проверить при регистрации). Лимиты: 120k req/день (confidential) | Testing mode: ≤100 test users, предупреждение при входе, **refresh token умирает через 7 дней** (главная dev-ловушка). Production + non-sensitive scopes (`openid email profile`) — полная верификация не требуется | Модерации нет, работает мгновенно |
| **Подводные камни** | Не OIDC — профиль через `login.yandex.ru/info`; точное совпадение redirect_uri; код живёт 10 минут | `device_id` обязателен в token-обмене; `state` в теле token-запроса; `state` ≥32 символов; `service_token`; id_token без публичного JWKS; токены — только form-urlencoded body | 7-дневный refresh в testing; переключение testing→production сбрасывает согласия test users | **Один Authorization callback URL на приложение** — dev и prod в одно приложение не влезают; email может требовать отдельного `/user/emails` со scope `user:email` |

## Схема dev/prod-окружений

Отдельная пара client_id/secret на окружение — стандарт, фактически принуждаемый провайдерами (GitHub: один callback; Google: testing/production — статус приложения; VK: redirect привязан к домену). Итого **до 8 регистраций (4 провайдера × dev/prod)**:

```
                dev-приложение                          prod-приложение
Google      http://localhost:8000/api/auth/         https://learnflow.me/api/auth/
            oauth/google/callback                    oauth/google/callback
            (testing mode, себя в test users;       (production, non-sensitive
            помнить про 7-дневный refresh)           scopes — без верификации)

GitHub      http://127.0.0.1:8000/api/auth/         https://learnflow.me/api/auth/
            oauth/github/callback                    oauth/github/callback
            (loopback, порт свободный)

Яндекс      http://localhost:8000/api/auth/         https://learnflow.me/api/auth/
            oauth/yandex/callback                    oauth/yandex/callback
            (без верификации, ≤5 приложений)

VK ID       localhost НЕ работает на dev-портах →   домен learnflow.me,
            см. варианты ниже                        https-redirect
```

Redirect_uri во всех случаях ведёт на **backend** (callback-endpoint API), не на SPA: state/verifier живут на стороне бэкенда; фронт в dev (5173) ходит через прокси или получает финальный редирект от бэкенда.

**VK ID в dev** — единственный обходной манёвр (туннели VK блокирует):
1. *Рекомендуемый*: dev-поддомен `dev.learnflow.me` с A-записью на `127.0.0.1` + реальный сертификат Let's Encrypt (DNS-01) + локальный nginx на 443 → proxy на backend. Домен есть, работает и для будущих капризных провайдеров.
2. Альтернатива без DNS: `/etc/hosts` + mkcert + локальный nginx на 443.
3. Минимальный: dev-приложение VK с `localhost` и backend'ом (или nginx) на порту 80 по http.

Для Google/GitHub/Яндекса туннель не нужен вовсе.

**Порядок внедрения** «первым Яндекс» оптимален: самый простой для localhost-dev (обычный code flow, без модерации) — на нём обкатывается провайдер-абстракция; VK ID вторым, уже с готовой dev-инфраструктурой (поддомен/nginx).

## Отмеченные допущения (степень уверенности)

- localhost с произвольным портом у Яндекса подтверждён сообществом, а не документацией (низкий риск);
- «VK ID доступен физлицу без бизнес-верификации с 2026» — уверенность средняя, проверяется за 10 минут при регистрации dev-приложения;
- ограничение VK «порт 80/443 для localhost» — из официальной доки, процитированной в двух независимых источниках.

## Первоисточники

- Authlib: https://pypi.org/project/Authlib/ ; https://github.com/authlib/authlib/releases ; https://docs.authlib.org/en/latest/oauth2/client/web/ ; https://github.com/authlib/authlib/blob/main/authlib/integrations/starlette_client/apps.py
- httpx-oauth: https://pypi.org/project/httpx-oauth/ ; https://github.com/frankie567/httpx-oauth
- django-allauth VK ID (прецедент адаптера): https://github.com/pennersr/django-allauth/blob/main/allauth/socialaccount/providers/vk/views.py ; https://docs.allauth.org/en/latest/release-notes/recent.html
- Яндекс: https://yandex.ru/dev/id/doc/ru/codes/code-url ; https://yandex.ru/dev/id/doc/ru/register-client ; https://yandex.ru/dev/id/doc/ru/confirm-account ; https://yandex.ru/dev/id/doc/ru/user-information
- VK ID: https://id.vk.ru/about/business/go/docs/ru/vkid/latest/vk-id/connection/api-integration/api-description (зеркало id.vk.ru — id.vk.com режет автоматизированный fetch) ; https://id.vk.ru/about/faq/business/vkid/authorization/30011 ; https://habr.com/ru/articles/821683/ ; https://habr.com/ru/articles/995504/
- Google: https://developers.google.com/identity/protocols/oauth2/web-server ; https://support.google.com/cloud/answer/10311615 ; https://support.google.com/cloud/answer/15549945
- GitHub: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
