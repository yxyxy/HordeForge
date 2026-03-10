# Security Notes

Документ фиксирует текущие security-практики runtime слоя HordeForge (P4 scope).

## 1. Token handling

1. Секреты не сохраняются в persistent storage как открытый текст:
   - `run.inputs` санитизируются перед записью;
   - `run.result` санитизируется перед записью и перед API-ответом;
   - artifacts в API payload также возвращаются в санитизированном виде.
2. Redaction выполняется по:
   - чувствительным ключам (`token`, `secret`, `password`, `authorization`, `api_key`, ...);
   - строковым паттернам (GitHub token prefixes, `Bearer ...`).
3. Runtime inputs для override/retry/resume хранятся только in-memory (`RUN_RUNTIME_INPUTS`) и не пишутся в disk-backed repositories.
4. `GitHubClient` валидирует non-empty token и не хранит raw token в отдельном атрибуте.

## 2. Manual command permissions

Manual control-plane команды (`override` и manual cron endpoints) требуют:

1. `X-Operator-Key`
2. `X-Operator-Role`
3. `X-Command-Source`

Допустимые значения настраиваются через:

- `HORDEFORGE_OPERATOR_API_KEY`
- `HORDEFORGE_OPERATOR_ALLOWED_ROLES`
- `HORDEFORGE_MANUAL_COMMAND_ALLOWED_SOURCES`

Недостаточные права возвращают `403 FORBIDDEN` в стандартном error envelope.

## 3. Audit trail

Для manual команд пишутся audit events в `observability/audit_logger.py`:

- факт запроса;
- разрешен/запрещен запрос;
- role/source оператора;
- outcome (`denied`, `invalid_state`, `completed:*`, ...).

Audit events:
- `RUN_OVERRIDE`, `RUN_STOPPED`, `RUN_RETRY`, `RUN_RESUMED`
- `AUTH_SUCCESS`, `AUTH_FAILURE`, `PERMISSION_DENIED`
- `PIPELINE_STARTED`, `PIPELINE_COMPLETED`, `PIPELINE_FAILED`
- `TENANT_CREATED`, `TENANT_UPDATED`, `TENANT_DELETED`

Логи пишутся в JSONL формате с partition по дате:
- `HORDEFORGE_AUDIT_LOG_DIR` (default: `.hordeforge_data/audit`)

## 4. Circuit Breaker

Для fault tolerance используется circuit breaker pattern (`observability/circuit_breaker.py`):

- States: CLOSED → OPEN → HALF_OPEN
- Configurable: failure_threshold, success_threshold, timeout
- Registry для управления множественными circuit breakers

## 5. Recommendations for production

1. Использовать short-lived/fine-grained GitHub tokens.
2. Ограничить ingress override/admin endpoint-ов сетевыми ACL и API gateway policy.
3. Подключить внешний sink для security/audit логов (Datadog, Splunk).
4. Ввести регулярную ротацию operator key и webhook secret.
5. Настроить PostgreSQL backend для storage (`HORDEFORGE_STORAGE_BACKEND=postgres`).
6. Настроить Redis backend для queue (`HORDEFORGE_QUEUE_BACKEND=redis`).
7. Подключить external metrics export (Prometheus Pushgateway или Datadog).
8. Настроить alerting destinations (Slack/Email) и верифицировать доставку.
9. Определить retention политики для runs/logs/artifacts/audit и активировать scheduled cleanup.
