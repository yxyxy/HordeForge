# HF-OC-001 / ST-03 — Model Namespace and Failover

## BDD

Feature: Model registration and auth profile rotation

Scenario: Несколько credential sets внутри одного provider
Given в `horde-provider` импортировано несколько auth profiles
When один profile временно недоступен или исчерпан
Then система должна переключиться на другой auth profile того же provider
And model refs должны оставаться в namespace `horde-provider/...`
And только после исчерпания provider-level вариантов допускается model fallback policy

## TDD

Red:
- нет описания auth profile rotation
- нет разделения между profile rotation и model fallback
- не зафиксирован модельный namespace

Green:
- auth profile rotation описан как первая линия failover
- model fallback описан как следующая линия
- model refs нормализованы к `horde-provider/...`

Refactor:
- убрать смешение понятий `provider unavailable` и `profile unavailable`
- отделить credential rotation policy от broader runtime fallback policy

## Test Design

1. Rotation между двумя auth profiles одного provider.
2. Cooldown для профиля после auth failure.
3. Сохранение того же model ref при переключении профиля.
4. Переход к model fallback только после исчерпания provider-level auth options.

## Definition of Done

1. Зафиксирован namespace `horde-provider/...`.
2. Зафиксирован порядок: profile rotation -> model fallback.
3. Зафиксирован минимальный failover policy для первой реализации.
