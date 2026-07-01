# HF-OC-001 / ST-01 — Provider Contract

## BDD

Feature: `horde-provider` contract

Scenario: Единый compatibility provider для OAuth path
Given текущий Qwen OAuth flow живет в HordeForge
When мы переносим его в OpenClaw
Then provider id должен быть единым `horde-provider`
And bundled `qwen` provider не должен модифицироваться
And отдельные credential sets не должны становиться отдельными provider ids

## TDD

Red:
- нет зафиксированного provider id
- нет разделения между provider namespace и auth profiles
- есть риск конфликтовать с `qwen/...`

Green:
- зафиксирован provider id `horde-provider`
- зафиксирован model namespace `horde-provider/...`
- auth profiles описаны как provider-scoped сущности

Refactor:
- убрать двусмысленность между `provider`, `profile`, `model alias`
- нормализовать naming для будущего plugin manifest

## Test Design

1. Проверка, что provider namespace не равен `qwen`.
2. Проверка, что модельный ref имеет вид `horde-provider/<model>`.
3. Проверка, что два набора credentials не требуют двух provider ids.

## Definition of Done

1. В roadmap зафиксирован provider id `horde-provider`.
2. Зафиксировано, что credential sets = auth profiles.
3. Зафиксировано, что canonical bundled `qwen` не меняется.
