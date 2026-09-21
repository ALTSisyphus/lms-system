## Миграции

Для предыдущего задания была добавлена миграция владельцев курсов и уроков:

```text
materials/migrations/0002_course_owner_lesson_owner.py
```

В рамках задания 32.1 добавлена миграция модели подписки:

```text
materials/migrations/0003_subscription.py
```

Модель `Subscription` связывает пользователя и курс. Уникальность пары `user` + `course` гарантируется ограничением `UniqueConstraint` на уровне базы данных.

Проверить состояние миграций:

```bash
python manage.py makemigrations --check
python manage.py migrate
```

---

## Тестирование

Запуск тестов приложения `materials`:

```bash
python manage.py test materials
```

Запуск всех тестов проекта:

```bash
python manage.py test
```

Тестами проверяются:

* валидация ссылок в поле `video_url`;
* разрешение ссылок только на `youtube.com` и его поддомены;
* запрет ссылок на сторонние ресурсы;
* создание уроков;
* получение уроков;
* обновление уроков;
* удаление уроков;
* права владельца урока;
* ограничения для другого пользователя;
* права группы `Модераторы`;
* запрет доступа анонимным пользователям;
* создание подписки на обновления курса;
* удаление существующей подписки;
* обработка ошибок при работе с подписками;
* уникальность подписки пользователя на курс;
* признак `is_subscribed` в данных курса;
* независимость подписок разных пользователей;
* пагинация списка курсов;
* пагинация списка уроков;
* параметр `page_size`;
* ограничение `max_page_size`;
* функциональность и права доступа из предыдущих домашних заданий.

Для аутентификации пользователей в API-тестах используется:

```python
self.client.force_authenticate(user=user)
```

---

## Покрытие тестами

Для проверки покрытия используется пакет `coverage`.

Создание отчёта:

```bash
coverage erase
coverage run manage.py test
coverage report -m > coverage.txt
```

Отчёт сохраняется в:

```text
coverage.txt
```

Текущее покрытие проекта:

```text
TOTAL 99%
```

Файл `coverage.txt` включён в проект в соответствии с требованиями задания.

---

## Проверка проекта

Перед сдачей рекомендуется выполнить:

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py test
coverage erase
coverage run manage.py test
coverage report -m > coverage.txt
```

После выполнения тестов результат должен завершаться статусом:

```text
OK
```

Домашнее задание №32.1 **«Валидаторы, пагинация и тесты»** выполнено в отдельной ветке:

```text
32.1-validators-pagination-tests
```

## Задание 32.2 — документирование и безопасность

Рабочая ветка: `32.2-documentation-and-security`.

Документация доступна без авторизации:

* Swagger: `/api/docs/`
* ReDoc: `/api/redoc/`
* OpenAPI schema: `/api/schema/`

Для защищённых запросов получите JWT через `POST /api/token/` (email и password),
затем передайте access token через кнопку **Authorize** в Swagger или заголовок
`Authorization: Bearer <access_token>`. Обновление токена: `POST /api/token/refresh/`.
Схема описывает регистрацию, пользователей, курсы, уроки, подписки и платежи,
включая реальные параметры фильтрации, сортировки и пагинации.

### Настройка Stripe

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
```

`.env` автоматически загружается из корня проекта через `python-dotenv`.
Уже установленные переменные окружения имеют приоритет.

* `STRIPE_SECRET_KEY` — секретный ключ Stripe **test mode** из собственного аккаунта.
  Значение в `.env.example` — заглушка, которую нужно заменить локально.
* `STRIPE_CURRENCY` — валюта, по умолчанию `rub`; цены проекта хранятся в рублях.
  Для этого задания оставьте `rub`, автоматической конвертации валют нет.
* `STRIPE_SUCCESS_URL` — полный URL возврата после Checkout.
* `STRIPE_CANCEL_URL` — полный URL возврата при отмене Checkout.

В примере оба URL ведут на существующую страницу документации. Замените их
своими страницами возврата при интеграции. Отдельных success/cancel endpoints нет.
Переход по success URL сам по себе не подтверждает оплату: статус запрашивается у Stripe.

Настоящие secret keys запрещено хранить в Git, README или тестах.
Файл `.env` остаётся в `.gitignore`. Без ключа приложение, документация и тесты
работают; попытка обращения к Stripe возвращает контролируемый ответ 502.
Для ручной проверки используйте только тестовый режим Stripe и его тестовые данные.

### Создание платежа

Установите положительную цену курса через существующий API курсов, например
`"price": "1500.00"`. Для существующих курсов миграция задаёт цену `0`.

```http
POST /api/payments/
Authorization: Bearer <access_token>
Content-Type: application/json

{"course": 1}
```

Сервер создаёт Product с названием курса, Price с `unit_amount=150000`
(копейки, расчёт через Decimal), затем Checkout Session с **Price ID**.
Только после успешного Checkout сохраняется Payment: текущий пользователь,
курс, цена, способ `stripe`, Product/Price/Session IDs, URL и статус Stripe.
Ответ 201 содержит данные платежа и `payment_url` для перехода к оплате.
Переданные клиентом сумма, пользователь, Stripe IDs и статус не влияют на платёж.
Ошибки: 400 — некорректный ID или неположительная цена, 401 — нет авторизации,
404 — курс отсутствует, 502 — ошибка Stripe или отсутствующий ключ.

### Проверка статуса

```http
GET /api/payments/10/status/
Authorization: Bearer <access_token>
```

Endpoint доступен только владельцу платежа. Сервер вызывает Checkout Session
Retrieve с сохранённым Session ID, обновляет `payment_status` в БД и возвращает
данные платежа. Чужой/несуществующий платёж — 404, отсутствие авторизации — 401,
отсутствующий Session ID (например, наличный платёж) — 400, ошибка Stripe — 502.
Webhook в этом задании не реализован: статус обновляется этим GET-запросом.

`GET /api/payments/` сохраняет существующую область видимости списка, фильтры
`paid_course`, `paid_lesson`, `payment_method` и сортировку `ordering=payment_date`
или `ordering=-payment_date`. Новый фильтр `payment_method=stripe` также доступен.
Старые платежи за курсы/уроки, способы cash/transfer и история в профиле сохранены.

Новые миграции:

* `materials/migrations/0004_course_price.py`
* `users/migrations/0005_payment_payment_status_payment_payment_url_and_more.py`

### Проверки

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py spectacular --file /tmp/lms-schema.yaml --validate
python manage.py test
coverage erase
coverage run manage.py test
coverage report -m > coverage.txt
```

Stripe SDK полностью замокан в тестах. Проверяются параметры Product, Price и
Checkout, запись платежа, серверные поля, ошибки каждого шага, права на статус,
обновление из Stripe и доступность/контракты документации.

При реализации использованы официальные справочники
[Stripe Checkout](https://docs.stripe.com/api/checkout/sessions/create?lang=python)
и [drf-spectacular](https://drf-spectacular.readthedocs.io/en/latest/customization.html).

Результат проверки задания 32.2: 56 тестов успешно, покрытие 99%;
OpenAPI проходит валидацию без ошибок и предупреждений.
