# Use Cases

�������� ��������� ������� �������� � ������� ������� ����������.

## UC-01: ������������� �������

- Actor: Tech Lead / Developer
- Trigger: ������ `init` ����� CLI/API
- Priority: P0
- Current status: **partial**

### �������� �����

1. ������������ �������� `repo_url` � �����.
2. ������� ��������� `init_pipeline`.
3. ����������� ���� ������������ ������� � ���������� ���������.
4. ����������� ����� � ���������� � feature/ci pipeline.

### ����������

- `pipelines/init_pipeline.yaml` � ������ pipeline � 6 ������
- ������: `repo_connector`, `rag_initializer`, `memory_agent`, `architecture_evaluator`, `test_analyzer`, `pipeline_initializer`
- CLI: `python cli.py init --repo-url <URL> --token <TOKEN>`

### �����������

- RAG � vector DB ������� �� ������� ��������� (`qdrant_client`, `sentence_transformers`).

## UC-02: ��������� feature issue

- Actor: Product Manager / Developer
- Trigger: issue � ������ `feature`
- Priority: P0
- Current status: **partial**

### �������� ����� (�������)

1. `dod_extractor` ��������� DoD.
2. `architecture_planner` ������ ����������� ����.
3. `specification_writer` ��������� ������������.
4. `task_decomposer` ������������� �� ���������.
5. `bdd_generator` ���������� BDD ��������.
6. `test_generator` ������� �����.
7. `code_generator` ��������� �������.
8. `test_runner` ��������� �����.
9. `fix_agent` ��������� ������� ������.
10. `review_agent` ��������� ���������.
11. `pr_merge_agent` ��������� ����������.
12. `ci_failure_analyzer` ��������� CI ����� �����.

### ����������

- `pipelines/feature_pipeline.yaml` � ������ pipeline � 12 ������ + loops
- LLM-enchancement: `llm_wrapper.py` (OpenAI, Anthropic, Google GenAI)
- GitHub integration: `live_review.py`, `live_merge.py` ��� real-time operations
- Fix loop: �� 5 �������� � retry policy

### �����������

- ����� ������� ���������� ����������������� fallback-����������.
- ��������� ���������� ��� YAML placeholders ������� �������������� ��������� (��. registry-����).

### ������������

- ���� ��������� ������������ -> `BLOCKED` � human action
- ���� fix loop ��������� ����� -> `FAILED/BLOCKED` � issue-������������

## UC-03: CI self-healing

- Actor: Scheduler / QA
- Trigger: ������� CI
- Priority: P1
- Current status: **partial**

### �������� ����� (�������)

1. `ci_failure_analyzer` �������������� ��� �������.
2. `fix_agent` ���������� �����������.
3. `test_runner` ��������� �����.
4. ��� ������ ���������/����������� PR.
5. `ci_verification` �������� ��������� ������ CI suite.
6. `issue_closer` ��������� issue ���� ��� ����� ��������.

### ����������

- `pipelines/ci_fix_pipeline.yaml` � 8 ����� + loops
- ���������� � GitHub Actions ��� real-time test execution
- Convergence detection ��� ����������� ����� ���������� fix loop
- Cron job `ci_monitor` ��� ������������� ��������

### �����������

- � ��������� ���� YAML ����, �� �������� loader-�� (��������, step-level `loops`).

## UC-04: ������ ���������� pipeline

- Actor: Maintainer
- Trigger: ������� ��������� (`stop/retry/resume`)
- Priority: P1
- Current status: **done**

### ����

���������� �������������� ���������� � ���������� override �������������� ��������.

### ����������

- `POST /runs/{run_id}/override` endpoint
- �������������� actions: `stop`, `retry`, `resume`, `explain`
- Permission checks: `X-Operator-Key`, `X-Operator-Role`, `X-Command-Source`
- Audit logging ���� override ��������
- State machine enforcement (stop ������ ��� RUNNING, retry ��� FAILED/BLOCKED)

### RBAC

| ����    | ���������� |
|---------|------------|
| `admin` | ��� �������� |
| `operator` | pipeline:run, override:execute, cron:trigger, queue:drain, runs:read, metrics:read |
| `viewer` | pipeline:read, cron:read, queue:read, runs:read, metrics:read |

## UC-05: ������������� backlog scan

- Actor: Scheduler
- Trigger: cron
- Priority: P2
- Current status: **done**

### ����

�������� ������� � ������ issue � ������������� �������������� �� � ���������� feature pipeline.

### ����������

- Cron job `issue_scanner` � `scheduler/jobs/issue_scanner.py`
- `scheduler/schedule_registry.py` � cron expressions ��� �����
- `scheduler/cron_dispatcher.py` � interval-based dispatch
- `POST /cron/run-due` � manual trigger ��� due jobs
- `POST /cron/jobs/{job_name}/trigger` � trigger ���������� ������
- JWT/RBAC ������ cron endpoints

### Cron Jobs

| Job | Interval | Purpose |
|-----|----------|---------|
| issue_scanner | configurable | Scan for ready issues |
| ci_monitor | configurable | Monitor CI failures |
| dependency_checker | configurable | Check for outdated dependencies |

## UC-06: CI monitoring

- Actor: Scheduler / DevOps Engineer
- Trigger: cron ��� webhook
- Priority: P1
- Current status: **done**

### ����

���������� ������� CI/CD ���������, �������������� �����, ��������� ������� � �����������.

### ����������

- `agents/ci_monitor_agent/` � ������ ����� ��� ����������� CI
- `scheduler/jobs/ci_monitor.py` � cron job ��� �������������� �����������
- ��������� ��������� ����������� CI (GitHub Actions, Jenkins, GitLab CI)
- ���������� � `pipelines/ci_monitoring_pipeline.yaml`
- �������������� �������� ����� ��� ����������� �������
- ��������� � ������ ����� CI/CD ���������

## UC-07: Dependency checking

- Actor: Scheduler / Security Team
- Trigger: cron ��� ������ ������
- Priority: P1
- Current status: **done**

### ����

�������� ������������ ������� �� ������� ����������� � ���������� �����������.

### ����������

- `agents/dependency_checker_agent/` � ����� ��� ������� ������������
- `scheduler/jobs/dependency_checker.py` � cron job ��� ������������� ��������
- ������������ ��������� �������� ������ ������������ (package.json, requirements.txt, � ��.)
- �������� ������� ����������� � ������������ (CVE, security advisories)
- ���������� � ������ ������ ����������� (NVD, Snyk, OWASP � ��.)
- ��������� ������� � ��������� ������������
- �������� ����� ��� ���������� ����������� ������������

## UC-08: �������������� � �����������

- Actor: System / API Consumer
- Trigger: ����� API ������
- Priority: P0
- Current status: **done**

### ����

�������� ����������� ��������� � ������� JWT ������� � RBAC.

### ����������

- JWT validation middleware � `scheduler/auth/middleware.py`
- JWT validator � `scheduler/auth/jwt_validator.py`
- RBAC � `scheduler/auth/rbac.py` � ������ admin/operator/viewer
- ������������ ����� `hordeforge_config.py`:
  - `HORDEFORGE_AUTH_ENABLED`
  - `HORDEFORGE_JWT_SECRET_KEY`
  - `HORDEFORGE_JWT_ALGORITHM`
  - `HORDEFORGE_SESSION_TTL_SECONDS`

### ���������� endpoints

- `/queue/drain` � ������� `queue:drain` permission
- `/cron/run-due` � ������� `cron:trigger` permission
- `/cron/jobs/{job_name}/trigger` � ������� `cron:trigger` permission
- `/runs/{run_id}/override` � ������� `override:execute` permission
- `/metrics/export` � ������� `metrics:read` permission

## UC-09: Observability � �������

- Actor: DevOps / SRE
- Trigger: periodic ��� manual
- Priority: P1
- Current status: **done**

### ����

�������������� ������� � �����-���� �� ������� ������� �����������.

### ����������

- Metrics exporter � `scheduler/jobs/metrics_exporter.py`
- ��������� Prometheus Pushgateway � Datadog
- ������������:
  - `HORDEFORGE_METRICS_EXPORTER=prometheus_pushgateway|datadog`
  - `HORDEFORGE_METRICS_EXPORT_INTERVAL_SECONDS`
  - `HORDEFORGE_PROMETHEUS_PUSHGATEWAY_URL`
  - `HORDEFORGE_DATADOG_API_KEY`
- Audit logger � `observability/audit_logger.py`
- Data retention � `scheduler/jobs/data_retention.py`
- Trace correlation: `run_id`, `correlation_id`, `trace_id` � summary

### Endpoints

- `GET /metrics` � Prometheus metrics (���������)
- `POST /metrics/export` � ������ ������� ������

## UC-10: Queue management

- Actor: Operator / Scheduler
- Trigger: ������ ��� ��������������
- Priority: P1
- Current status: **done**

### ����

���������� ������������ �������� ����� queue backend.

### ����������

- Task queue � `scheduler/task_queue.py`
- Queue backends: memory (�� ���������), Redis
- `POST /run-pipeline?async_mode=true` � ���������� � �������
- `GET /queue/tasks/{task_id}` � ��������� ������� ������
- `POST /queue/drain` � ��������� �������

## Definition of Ready ��� ������� UC � ����

�������� ����������� � production, ����:

1. ���� runtime-���������� ���� ����� use case
2. ���� �������� �������� (happy path + failure path)
3. ���� ����������� � �������� ������
4. ���� rollback/override �������� (��� P0/P1)
