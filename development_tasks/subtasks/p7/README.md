# Subtasks Index — Phase P7

| Task ID | Title | Priority | Status |
|---------|-------|----------|--------|
| HF-P7-001 | API Rate Limiting | P0 | ✅ DONE |
| HF-P7-002 | OAuth/OIDC Authentication | P1 | ✅ DONE |
| HF-P7-003 | Kubernetes Deployment | P1 | ✅ DONE |
| HF-P7-004 | Database Migrations | P1 | 🟡 IN PROGRESS |
| HF-P7-005 | Backup/Recovery System | P1 | 📋 BACKLOG |
| HF-P7-006 | Alerting Integration | P2 | 📋 BACKLOG |
| HF-P7-007 | Data Retention Policies | P2 | 📋 BACKLOG |
| HF-P7-008 | Phase Closeout and Documentation | P0 | 📋 BACKLOG |

## Dependencies Graph

```
P6 Complete
    │
    ├── HF-P7-001 (P0, 2d) ───┐
    │                          ├── HF-P7-002 (P1, 3d) ───┤
    │                          │                          ├── HF-P7-008 (P0, 0.5d)
    │                          │
    ├── HF-P7-003 (P1, 3d) ───┤
    │                          ├── HF-P7-004 (P1, 2d) ───┤
    │                          │
    ├── HF-P7-005 (P1, 2d) ───┤
    │                          ├── HF-P7-006 (P2, 1d) ───┤
    │                          │
    └── HF-P7-007 (P2, 1d) ───┘
```

## Progress

0/8 completed (0%)
Total estimate: 17d

## Completion Target

2026-03-XX

## Overview

Phase P7 закрывает критические компоненты для production-ready запуска:
- **P0 (1):** API Rate Limiting
- **P1 (4):** OAuth, K8s, Migrations, Backup
- **P2 (2):** Alerting, Retention
- **P0 (1):** Phase closeout
