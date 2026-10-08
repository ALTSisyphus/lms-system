# 35.2 — CI/CD и GitHub Actions: развертывание LMS

## Архитектура

- Django 5.2 / DRF: **Gunicorn**, доступен только внутри Docker-сети на 8000.
- **Nginx**: reverse proxy, снаружи опубликован только HTTP-порт 80.
- PostgreSQL 16 и Redis 7: внутренние контейнеры, порты **5432/6379 не опубликованы**.
- Celery worker и Celery Beat: отдельные автоматически перезапускаемые контейнеры.
- Постоянные тома: `postgres_data`, `redis_data`, `static_data`, `media_data`.
- CI: каждый push и PR → Django tests → Ruff → Docker build. **Только push в `develop`** после успеха всех проверок → GHCR → SSH-деплой. В PR секреты не используются, деплоя нет.

> ВАЖНО. Готовая конфигурация Nginx обслуживает HTTP для проверки задания по IP. До использования личных данных, JWT и платежей подключите **HTTPS** (TLS-терминация на балансировщике или отдельно настроенном Nginx), откройте 443 и включите HTTPS-ориентированные настройки Django. Не используйте HTTP для реальных пользователей.

## 1. Подготовьте Ubuntu 26.04 LTS сервер

Подключитесь к серверу под обычным администратором с `sudo`. Обновите систему:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl ufw
```

Установите Docker Engine + Compose plugin **по официальной инструкции** для вашего релиза Ubuntu: https://docs.docker.com/engine/install/ubuntu/ (секция "Install using the apt repository"). После установки проверьте:

```bash
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

Создайте отдельного пользователя для деплоя:

```bash
sudo adduser --disabled-password --gecos '' deploy
sudo usermod -aG docker deploy
sudo install -d -m 755 -o deploy -g deploy /opt/lms-system
sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
```

> Членство в группе `docker` даёт практически root-доступ к серверу. Выделите для этого задания отдельный VPS/пользователя, не используйте личный рабочий сервер. После изменения группы повторно войдите под `deploy`.

Настройте SSH-порт и firewall, **не закрывая текущую SSH-сессию**, прежде чем подтвердите работу ключа:

```bash
sudo ufw allow 22/tcp        # если SSH слушает другой порт — разрешите его вместо 22
sudo ufw allow 80/tcp
# 443/tcp разрешить после настройки TLS
sudo ufw enable
sudo ufw status verbose
```

Если VPS-провайдер имеет дополнительный firewall/security group, там также разрешите TCP 22 (или ваш SSH-порт) и 80, закройте 5432, 6379, 8000. На продакшене в Docker эти три порта не публикуются.

## 2. Создайте отдельный SSH-ключ для GitHub Actions

На **своём компьютере** (VS Code Terminal, Ubuntu):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/lms_github_actions -C github-actions-lms -N ''
cat ~/.ssh/lms_github_actions.pub
```

Публичную часть **впишите на сервере** в `/home/deploy/.ssh/authorized_keys` (одна строка). Установите владельца и права:

```bash
sudo chown -R deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

Протестируйте новое подключение в новом терминале:

```bash
ssh -i ~/.ssh/lms_github_actions deploy@SERVER_IP
```

Закрывать парольный SSH-вход и root-вход можно **только после** проверки входа по ключу и сохранения резервного административного доступа.

Получите и независимо проверьте fingerprint SSH host key на сервере:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

С локальной машины получите строку `known_hosts` и **сверьте её fingerprint с сервером**; не доверяйте `ssh-keyscan` без проверки:

```bash
ssh-keyscan -t ed25519 SERVER_IP 2>/dev/null
```

Для нестандартного порта применяйте `ssh-keyscan -p PORT ...` и переменную `DEPLOY_SSH_PORT`.

## 3. Подготовьте server-only файл `.env`

Перед первым деплоем **вручную** положите шаблон `.env.template` в `/opt/lms-system` (например, с локального компьютера командой `scp .env.template deploy@SERVER_IP:/opt/lms-system/`). Файлы `docker-compose.prod.yml`, `nginx/default.conf` и `scripts/deploy_remote.sh` сам передаст GitHub Actions. Создайте `/opt/lms-system/.env` из **`.env.template`**:

```bash
cd /opt/lms-system
cp .env.template .env     # если шаблон предварительно скопирован на сервер
chmod 600 .env
```

Заполните все `CHANGE_ME`. Для секретного ключа Django сгенерируйте случайную строку, например **в локальном проекте с установленными Django-зависимостями**:

```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Значения `DB_NAME/DB_USER/DB_PASSWORD` должны соответствовать `POSTGRES_DB/POSTGRES_USER/POSTGRES_PASSWORD`. Поставьте `DEBUG=False`, `ALLOWED_HOSTS=SERVER_IP,localhost,127.0.0.1`, `CSRF_TRUSTED_ORIGINS=http://SERVER_IP`. В `STRIPE_*_URL` при необходимости тоже замените адрес. Реальный `STRIPE_SECRET_KEY` требуется только для действующей интеграции Stripe.

Значения секретов с `$`, `#` или пробелами заключайте в одинарные кавычки в `.env`, чтобы Compose не интерполировал их и не обрезал комментарии.

Все секреты приложения хранятся **только на сервере** в `.env`; в Docker-образе, Git и GitHub Actions они отсутствуют. `.env.template` — не секрет, а пример.

## 4. Настройте GHCR для приватного контейнерного пакета

Workflow публикует образ `ghcr.io/OWNER/REPO:<commit SHA>` с использованием встроенного **`GITHUB_TOKEN`** (разрешение `packages: write`, дополнительный PAT для сборки не нужен).

Если GHCR-пакет приватный, пользователю `deploy` на сервере требуется один раз войти в registry с **classic PAT с минимальным scope `read:packages`**, которому доступен нужный пакет:

```bash
sudo -iu deploy
read -rsp 'GHCR PAT (read:packages): ' GHCR_PAT; echo
printf '%s' "$GHCR_PAT" | docker login ghcr.io -u GITHUB_USERNAME --password-stdin
unset GHCR_PAT
chmod 600 ~/.docker/config.json
exit
```

Не вставляйте PAT в текст GitHub Actions, `.env`, shell history или проект. Для публичного GHCR-пакета Docker login обычно не требуется.

## 5. Настройте GitHub Secrets и Variables

На GitHub: **Repository → Settings → Secrets and variables → Actions**. Заполните:

| Тип | Имя | Значение |
| --- | --- | --- |
| Secret | `DEPLOY_HOST` | Публичный IP / hostname сервера |
| Secret | `DEPLOY_USER` | `deploy` |
| Secret | `DEPLOY_SSH_KEY` | Содержимое `~/.ssh/lms_github_actions` **включая BEGIN/END** |
| Secret | `DEPLOY_KNOWN_HOSTS` | Проверенная строка публичного SSH host key сервера в формате `known_hosts` |
| Variable (опционально) | `DEPLOY_SSH_PORT` | `22`, если не задано |

При использовании environment `production` можно требовать ручного одобрения деплоя через правила защиты среды. Если хотите хранить секреты именно в environment, переместите их туда с теми же именами — job `deploy` уже использует `environment: production`.

Важно: в `DEPLOY_KNOWN_HOSTS` должна быть **не строка fingerprint**, а полная проверенная запись `ssh-keyscan` (`host ssh-ed25519 AAA...`), для нестандартного порта — `[host]:port ssh-ed25519 ...`.

## 6. Первый деплой и проверка

1. Отправьте ветку с workflow и создайте PR к `develop` (тесты, линт, сборка с `push: false`; **без деплоя**).
2. После зелёных проверок **слейте** PR в `develop`. Push в `develop` запускает публикацию образа и деплой. При другой главной ветке замените `refs/heads/develop` в `.github/workflows/ci-cd.yml` на её имя.
3. На сервере `scripts/deploy_remote.sh` скачает образ, запустит PostgreSQL/Redis, выполнит `migrate` и `collectstatic`, запустит Nginx/Gunicorn/Celery, дождётся healthcheck.
4. Action проверяет `http://SERVER_IP/health/` после деплоя; ручные проверки:

```bash
curl -f http://SERVER_IP/health/
curl -I http://SERVER_IP/api/docs/
ssh deploy@SERVER_IP
cd /opt/lms-system
docker compose --env-file .env --env-file .image.env -f docker-compose.prod.yml ps
docker compose --env-file .env --env-file .image.env -f docker-compose.prod.yml logs --tail=100 backend nginx celery
```

Ожидаемый `GET /health/`: `{"status": "ok"}`, статус 200. Корневой `/` у API может вернуть 404 — это нормально.

## 7. Автоперезапуск, откат, диагностика

- `restart: unless-stopped` включает перезапуск сервисов Docker после сбоя и перезагрузки хоста (если Docker daemon включён через systemd).
- Статус unhealthy сам по себе не перезапускает контейнер. Критичные зависимости имеют healthcheck; `docker compose up --wait` останавливает deploy job при проблемах.
- Для отката укажите в `/opt/lms-system/.image.env` **предыдущий проверенный SHA-образ** и выполните:

```bash
docker compose --env-file .env --env-file .image.env -f docker-compose.prod.yml pull
docker compose --env-file .env --env-file .image.env -f docker-compose.prod.yml up -d --wait
```

- Откат контейнера **не откатывает миграции БД**. Перед несовместимыми миграциями сделайте резервную копию PostgreSQL и проверьте совместимость схемы.
- Повторное развёртывание того же SHA идемпотентно. База и пользовательские загрузки переживают замену образа благодаря volumes. Делайте резервные копии томов.
- На сервере должны быть доступны ресурсы для 6 контейнеров: backend, nginx, postgres, redis, celery, celery_beat.

## 8. Проверка критериев перед сдачей

- [ ] Python/Django tests проходят (`python manage.py test`), Ruff возвращает код 0.
- [ ] Push в рабочую ветку и PR запускают тесты → линт → сборку, но **не деплой**.
- [ ] После merge/push в `develop` выполняется публикация GHCR и деплой.
- [ ] По IP открывается `/api/docs/`, `/health/` даёт 200.
- [ ] После аварийного завершения процесса Gunicorn контейнер перезапускается; ручной `docker stop` отключает автоматический перезапуск до следующего запуска.
- [ ] `docker compose ps` показывает рабочие backend, nginx, postgres, redis, celery, celery_beat.
- [ ] UFW/security group не публикуют 5432/6379/8000; нет доступных секретов в Git.
- [ ] `.env.template`, `.gitignore`, GitHub Secrets, SSH и инструкция проверены.
- [ ] PR содержит описание изменений, ссылку на доступный IP/домен и ссылку на зелёный workflow.

Никакой скрипт в репозитории не может создать VPS, выдать DNS, приватный SSH-ключ или секреты сам по себе: эти пункты должен заполнить владелец сервера.
