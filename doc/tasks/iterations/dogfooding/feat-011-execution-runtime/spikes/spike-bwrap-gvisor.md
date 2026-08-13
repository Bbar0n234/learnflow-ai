# Спайк: bubblewrap внутри gVisor (runsc) — feat-011 execution runtime

Дата: 2026-08-11. Вопрос спайка: работает ли bwrap-префикс для изоляции джоб внутри gVisor-песочницы (runsc), и держит ли он фактическую изоляцию mount-ns и сети.

**Вердикт: зелёный, с одной жёлтой оговоркой.** bwrap под runsc работает: mount-ns, pivot_root, userns (включая вложенный, non-root), pid-ns — всё живо, изоляция ФС держит фактически. Оговорка: `--unshare-net` самого bwrap под gVisor **сломан** (фатально падает на настройке loopback), но полноценно заменяется внешним префиксом `unshare -n` (root) / `unshare -U --map-current-user -n` (non-root) — пустой netns под gVisor создаётся и сеть режет наглухо.

## Окружение

| Компонент | Версия |
|---|---|
| Хост | Fedora 43, kernel 7.1.3-100.fc43.x86_64, x86_64, SELinux enforcing |
| bubblewrap | 0.11.0 (bubblewrap-0.11.0-2.fc43, **без setuid**: `-rwxr-xr-x root root`) |
| runsc | release-20260803.0 (spec 1.2.1), статический бинарь из storage.googleapis.com/gvisor/releases/release/latest |
| util-linux (unshare, setpriv) | 2.41.5 |
| Режим gVisor | `runsc --rootless --network={none,host} do ...` — без docker, поверх хостовой ФС; внутри эмулируемое ядро `4.19.0-gvisor`, uid=0 |
| Bash-sandbox агента | все ключевые прогоны выполнены с отключённым sandbox (`dangerouslyDisableSandbox`), чтобы исключить вложенные артефакты среды |

Тестовые данные: `/tmp/wsA` (workspace джобы, marker.txt), `/tmp/wsB` (чужой workspace, secret.txt), `/tmp/skills-ro` (эмуляция /skills). Скрипты: `run-bwrap.sh` (bwrap-префикс), `job-probe.sh` (пробы изоляции изнутри джобы), `nonroot-inner.sh` (минимальная проба записи) — лежат рядом в этой директории.

## Матрица проверок

Семантика PASS: изоляция ведёт себя так, как должен ожидать executor.

| # | Слой | Команда (суть) | Результат |
|---|---|---|---|
| C1 | Голый хост (контроль) | `run-bwrap.sh` (bwrap: unshare-user/pid/ipc/uts, ro-bind /usr, tmpfs /tmp, bind wsA→/workspace, ro-bind /skills) | Все PASS: wsA rw, wsB отсутствует (ENOENT на чтение и запись), /skills ro (EROFS), сеть наружу открыта (ожидаемо без --unshare-net) |
| C2 | Голый хост (контроль) | то же + `--unshare-net` | Все PASS, сеть закрыта: `OSError: [Errno 101] Network is unreachable` |
| G0 | runsc smoke | `runsc --rootless --network=none do echo ...`; `do sh -c 'id; uname; bwrap --version'` | Работает: uid=0, ядро 4.19.0-gvisor, bwrap виден с хостовой ФС |
| G1 | runsc + bwrap | `runsc --rootless --network=none do -volume /tmp/wsA run-bwrap.sh` | **Все PASS.** bwrap стартует, mount-изоляция полная (wsB — ENOENT, /skills — EROFS), pid-ns работает (pid=2), python3 исполняется |
| G2 | runsc + bwrap --unshare-net | то же + `--unshare-net` (network=none) | **FAIL (фатально): `bwrap: loopback: Failed RTM_NEWADDR: No child processes`**, bwrap exit=1, джоба не стартует |
| G2' | runsc(net=host) + bwrap --unshare-net | `runsc --network=host do sh -c 'bwrap --unshare-user --unshare-net ... true'` | **FAIL: `bwrap: loopback: Failed to look up lo: No such device`**, exit=1. В свежем netns gVisor нет интерфейса lo вовсе |
| G3 | runsc(net=host) + raw `unshare -n` | `do sh -c 'unshare -n sh -c "..."'` | **PASS**: netns создаётся, интерфейсов ноль (даже lo), сокет не открывается: `OSError: [Errno 97] Address family not supported by protocol` |
| G4 | runsc(net=host) + `unshare -n` + bwrap (root) | `do -volume /tmp/wsA sh -c "unshare -n run-bwrap.sh"` | **Все PASS**, включая сеть: localhost и 1.1.1.1 — EAFNOSUPPORT. Рабочая замена --unshare-net |
| G5 | runsc + bwrap от non-root | `do sh -c 'setpriv --reuid 1000 ... bwrap --unshare-user --unshare-pid ... id'` | **PASS**: несетуидный bwrap создаёт userns от uid=1000 внутри gVisor, exit=0 |
| G6 | runsc + полная non-root цепочка | `setpriv 1000 → unshare -U --map-current-user -n → bwrap --unshare-user ...` (вложенный userns 2 уровня) | Изоляция и сеть PASS; **запись в /workspace — FAIL: `OSError: [Errno 22] Invalid argument`**, каталог виден как `65534:65534` (владелец не замаплен) |
| G7 | Гипотеза владельца (root-цепочка с unshare -U, владелец замаплен) | `do -force-overlay=false sh -c 'unshare -U --map-current-user -n bwrap ...'` | **PASS**: WRITE-OK, PY-WRITE-OK → EINVAL из G6 вызван именно незамапленным владельцем каталога |
| C3 | Голый хост (контроль к G6) | та же вложенная цепочка, workspace = каталог с незамапленным владельцем (`/dev/shm`, 65534 в ns) | **PASS**: запись работает → EINVAL — специфика gVisor (gofer), на реальном ядре такой проблемы нет |
| G8 | Write-through на хост | `do -force-overlay=false` + bwrap bind wsA→/workspace | **PASS**: `job-output.txt` появился на хостовой ФС с корректным содержимым |

Дословные ошибки (полные строки):

```
bwrap: loopback: Failed RTM_NEWADDR: No child processes        # runsc --network=none
bwrap: loopback: Failed to look up lo: No such device          # runsc --network=host
OSError: [Errno 22] Invalid argument: '/workspace/nonroot-py.txt'  # создание файла в каталоге с незамапленным владельцем (только под gVisor)
OSError: [Errno 97] Address family not supported by protocol   # пустой netns gVisor: сокет не создаётся вовсе
```

## Разбор находок

**1. bwrap под gVisor работает.** Историческая проблема mount namespaces (gvisor#221) в актуальном релизе не воспроизводится: `--unshare-user --unshare-pid --unshare-ipc --unshare-uts`, ro/rw-бинды, `--tmpfs`, `--proc`, `--dev`, `--symlink`, `--chdir`, `--new-session`, `--die-with-parent`, `--clearenv` — всё отработало. setuid-bwrap не нужен: и root-, и non-root-путь идут через userns, gVisor их поддерживает, включая вложенность (userns → userns) минимум в два уровня.

**2. Изоляция держит фактически, не декоративно.** Из-под bwrap чужой `/tmp/wsB` не просто «нельзя прочитать» — его **не существует** в mount-ns (ENOENT и на чтение, и на запись; в `/proc/self/mounts` его нет). Свой workspace — rw с write-through на хостовую ФС. `/skills` — честный EROFS.

**3. `--unshare-net` bwrap'а под gVisor сломан, замена работает.** bwrap после создания netns безусловно настраивает loopback через netlink и при неудаче умирает (флага «пропустить настройку lo» у bwrap нет). В gVisor свежий netns не имеет lo (`No such device` при host-net) либо не принимает RTM_NEWADDR (странный `ECHILD` при net=none) — в обоих режимах фатально. Обход: netns создаёт **не bwrap**, а внешний `unshare -n` (от root) или `unshare -U --map-current-user -n` (от non-root); внутри netns пустой настолько, что сокет не создаётся (EAFNOSUPPORT) — «закрыть видимость app:8000» это перекрывает с запасом.

**4. Ловушка владельца workspace (только gVisor).** Если каталог workspace принадлежит uid, который не замаплен в userns джобы, создание файлов в нём падает с EINVAL — даже при mode 777 и даже там, где реальное ядро Linux это разрешает (контроль C3). Требование к executor: **workspace-каталог должен принадлежать uid, под которым исполняется джоба** (executor и так его создаёт — просто chown/владелец должен совпадать с job uid).

**5. Побочное о поведении джоб без сети.** В пустом netns gVisor нет даже lo, т.е. джобе недоступен и 127.0.0.1 внутри самой себя (поднять локальный сервис и подключиться к нему нельзя). На реальном ядре lo в новом netns есть, но лежит down — итог для джобы тот же. Если джобам когда-то понадобится внутренний localhost, вариант «без сети» это исключает.

## Рекомендованный bwrap-префикс для executor

Вариант A — джоба **без сети** (закрывает и app:8000, и egress), executor-процесс non-root:

```sh
unshare -U --map-current-user -n \
bwrap \
  --unshare-user --unshare-pid --unshare-ipc --unshare-uts \
  --die-with-parent --new-session \
  --clearenv \
  --setenv PATH /usr/local/bin:/usr/bin:/bin \
  --setenv HOME /workspace \
  --setenv LANG C.UTF-8 \
  --ro-bind /usr /usr \
  --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib64 /lib64 --symlink usr/sbin /sbin \
  --ro-bind /etc /etc \
  --proc /proc --dev /dev --tmpfs /tmp \
  --bind "$JOB_WORKSPACE" /workspace \
  --ro-bind /skills /skills \
  --chdir /workspace \
  -- "$@"
```

Вариант B — джобе **нужна сеть** (egress разрешён политикой): убрать внешний `unshare ...` целиком и не добавлять `--unshare-net` (он под gVisor фатален). Сетевую политику в этом варианте держит контейнерный уровень (network=none / internal network / firewall), не bwrap.

Примечания к префиксу:
- `--ro-bind /etc /etc` — упрощение спайка; в боевом образе сузить до необходимого (`ld.so.cache`, `resolv.conf`, `ssl/certs`, `passwd` при надобности). Симлинки `/bin→usr/bin` и т.п. соответствуют merged-usr раскладке (Fedora/Debian/Ubuntu).
- `$JOB_WORKSPACE` обязан принадлежать uid executor-процесса (см. находку 4).
- setuid-bwrap не требуется; `--unshare-user` обязателен для non-root (без него непривилегированному bwrap не из чего собрать mount-ns).
- Префикс проверен целиком под runsc: root-цепочка (G4) и non-root-цепочка с вложенным userns (G6+G7).

## Ограничения переноса вывода (rootless Fedora → docker+runsc Ubuntu prod)

Спайк гонялся в режиме `runsc --rootless do` — это тестовый режим с существенными отличиями от прод-топологии (docker + runtime runsc). Что именно может отличаться и что перепроверить на прод-VM:

1. **uid-маппинг.** В rootless всё схлопнуто в одного хостового пользователя: хостовый uid 1000 → root внутри, все прочие uid → 65534. В docker+runsc маппинг честный. Из-за этого G6 (EINVAL) на проде может не воспроизводиться при других раскладах владельцев — но правило «workspace принадлежит job uid» надо соблюсти и перепроверить именно записью файла из-под полного префикса.
2. **Seccomp/AppArmor docker.** Дефолтный seccomp-профиль docker исторически режет `unshare`/`clone(CLONE_NEWUSER)` для непривилегированных контейнеров; применяет ли его runsc к своему Sentry — вопрос конфигурации. Ubuntu 24.04 вдобавок ограничивает unprivileged userns через AppArmor на хосте (внутри gVisor это решает эмулируемое ядро, хост-политика не должна видеть внутренний unshare — но это надо подтвердить). **Первая проверка на проде: `docker run --runtime=runsc <образ> bwrap --unshare-user ... true` от non-root пользователя образа.**
3. **Overlay-артефакты `do`-режима.** `runsc do` по умолчанию накрывает всю ФС tmpfs-overlay (write-through в volume не работает — проверено, это артефакт режима, а не gVisor). В docker+runsc волюмы обычные; write-through перепроверить (тривиально).
4. **`--network=none` vs netstack.** В rootless доступен только host-network или none; прод, вероятно, пойдёт через netstack gVisor (мостовая сеть docker). Поведение `--unshare-net` bwrap'а (падение на lo) воспроизведено в обоих доступных режимах и почти наверняка сохранится под netstack, но G2 стоит повторить в прод-конфигурации — вдруг netstack-netns отдаёт lo.
5. **Версии.** Прод-образ принесёт свой bwrap (Debian/Ubuntu: 0.8–0.10 против 0.11 здесь) и, возможно, другой релиз runsc. Логика loopback в bwrap старая и стабильная — но матрицу G1/G2/G4/G6 стоит прогнать на прод-версиях как smoke (скрипты переносимы as-is).
6. **SELinux vs AppArmor.** Здесь SELinux enforcing помех не создал; на Ubuntu действует AppArmor — см. п. 2.

## Файлы спайка

- `run-bwrap.sh` — bwrap-префикс с пробами (принимает доп. флаги bwrap аргументами)
- `job-probe.sh` — пробы изоляции, исполняются внутри bwrap
- `nonroot-inner.sh` — минимальная проба записи для non-root цепочки
- `runsc` (+ `runsc.sha512`) — статический бинарь gVisor release-20260803.0, checksum проверен
