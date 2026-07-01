# HF-OC-001 / ST-02 — Credentials Storage and Refresh

## BDD

Feature: OAuth credentials lifecycle

Scenario: Импорт и refresh пользовательских credentials
Given пользователь передает `oauth_creds.json`
When credentials импортируются в OpenClaw-compatible слой
Then создается auth profile внутри `horde-provider`
And credentials сохраняются через native secret surface или совместимый bridge
And access token автоматически обновляется до истечения `expiry_date`
And refreshed credentials persistятся обратно

## TDD

Red:
- нет зафиксированного import flow
- нет target storage model
- нет refresh lifecycle для OpenClaw integration

Green:
- описан import flow `json -> auth profile`
- описан storage split между secret payload и runtime state
- описан on-demand refresh с persisted write-back

Refactor:
- отделить temporary compatibility bridge от target storage model
- минимизировать зависимость от старого `cli/repo_store.py`

## Test Design

1. Импорт валидного JSON с `refresh_token`.
2. Rejection невалидного JSON без `refresh_token`.
3. Refresh при near-expiry токене.
4. Persist обновленных credentials после refresh.
5. Guard от параллельного refresh одного и того же profile.

## Definition of Done

1. Описан import flow credentials.
2. Описан storage contract.
3. Описан refresh lifecycle.
4. Описан migration bridge от старого secret/profile storage.
