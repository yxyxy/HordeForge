from __future__ import annotations

import json
import os
from typing import Any


class DashboardExporter:
    """Export cost metrics to dashboard platforms."""

    @staticmethod
    def to_datadog_dashboard(
        metrics: dict[str, Any],
        title: str = "HordeForge Cost Dashboard",
    ) -> dict[str, Any]:
        """Generate Datadog dashboard JSON configuration."""
        widgets = []

        # Total cost widget
        widgets.append(
            {
                "definition": {
                    "type": "timeseries",
                    "requests": [
                        {
                            "q": "sum:hordeforge.total_cost_usd{*}",
                            "style": {"line_width": "normal", "palette": "dog_classic"},
                        }
                    ],
                    "title": "Total Cost (USD)",
                },
                "layout": {"x": 0, "y": 0, "width": 12, "height": 8},
            }
        )

        # Cost by tenant widget
        widgets.append(
            {
                "definition": {
                    "type": "timeseries",
                    "requests": [
                        {
                            "q": "sum:hordeforge.total_cost_usd by {tenant_id}",
                            "style": {"line_width": "normal", "palette": "cool"},
                        }
                    ],
                    "title": "Cost by Tenant",
                },
                "layout": {"x": 0, "y": 8, "width": 12, "height": 8},
            }
        )

        # Token usage
        widgets.append(
            {
                "definition": {
                    "type": "query_table",
                    "requests": [
                        {
                            "q": "sum:hordeforge.total_input_tokens by {tenant_id}",
                            "style": {"line_width": "normal", "palette": "dog_classic"},
                        }
                    ],
                    "title": "Input Tokens by Tenant",
                },
                "layout": {"x": 0, "y": 16, "width": 6, "height": 8},
            }
        )

        widgets.append(
            {
                "definition": {
                    "type": "query_table",
                    "requests": [
                        {
                            "q": "sum:hordeforge.total_output_tokens by {tenant_id}",
                            "style": {"line_width": "normal", "palette": "dog_classic"},
                        }
                    ],
                    "title": "Output Tokens by Tenant",
                },
                "layout": {"x": 6, "y": 16, "width": 6, "height": 8},
            }
        )

        # Cost alerts status
        if "budget" in metrics:
            widgets.append(
                {
                    "definition": {
                        "type": "alert_value",
                        "requests": [
                            {
                                "q": "sum:hordeforge.budget_used_percent{tenant_id:*}",
                            }
                        ],
                        "title": "Budget Used %",
                        "alert_id": "hordeforge.budget_warning",
                    },
                    "layout": {"x": 0, "y": 24, "width": 4, "height": 4},
                }
            )

        return {
            "title": title,
            "widgets": widgets,
            "template_variables": [{"name": "tenant_id", "prefix": "tenant_id", "default": "*"}],
            "layout_type": "ordered",
        }

    @staticmethod
    def to_grafana_dashboard(
        metrics: dict[str, Any],
        title: str = "HordeForge Cost Dashboard",
    ) -> dict[str, Any]:
        """Generate Grafana dashboard JSON configuration."""
        panels = []

        # Total cost panel
        panels.append(
            {
                "id": 1,
                "title": "Total Cost (USD)",
                "type": "timeseries",
                "targets": [
                    {
                        "expr": 'sum(hordeforge_total_cost_usd{tenant_id=~"$tenant_id"})',
                        "legendFormat": "Total Cost",
                    }
                ],
                "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
            }
        )

        # Cost by tenant panel
        panels.append(
            {
                "id": 2,
                "title": "Cost by Tenant",
                "type": "timeseries",
                "targets": [
                    {
                        "expr": 'sum by (tenant_id) (hordeforge_total_cost_usd{tenant_id=~"$tenant_id"})',
                        "legendFormat": "{{tenant_id}}",
                    }
                ],
                "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
            }
        )

        # Input tokens panel
        panels.append(
            {
                "id": 3,
                "title": "Input Tokens",
                "type": "stat",
                "targets": [
                    {
                        "expr": 'sum(hordeforge_total_input_tokens{tenant_id=~"$tenant_id"})',
                    }
                ],
                "gridPos": {"x": 0, "y": 16, "w": 6, "h": 4},
            }
        )

        # Output tokens panel
        panels.append(
            {
                "id": 4,
                "title": "Output Tokens",
                "type": "stat",
                "targets": [
                    {
                        "expr": 'sum(hordeforge_total_output_tokens{tenant_id=~"$tenant_id"})',
                    }
                ],
                "gridPos": {"x": 6, "y": 16, "w": 6, "h": 4},
            }
        )

        return {
            "dashboard": {
                "title": title,
                "panels": panels,
                "templating": {
                    "list": [
                        {
                            "name": "tenant_id",
                            "type": "query",
                            "query": "group by(tenant_id) (hordeforge_total_cost_usd)",
                            "refresh": 1,
                        }
                    ]
                },
                "tags": ["hordeforge", "cost"],
                "timezone": "browser",
                "schemaVersion": 38,
                "version": 1,
            }
        }

    @staticmethod
    def to_json_file(
        metrics: dict[str, Any],
        output_path: str,
        format: str = "datadog",
    ) -> None:
        """Export dashboard to JSON file."""
        if format == "datadog":
            dashboard = DashboardExporter.to_datadog_dashboard(metrics)
        elif format == "grafana":
            dashboard = DashboardExporter.to_grafana_dashboard(metrics)
        else:
            raise ValueError(f"Unknown format: {format}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dashboard, f, indent=2)


# Default dashboard configurations
DEFAULT_DASHBOARD_CONFIGS = {
    "datadog": {
        "title": "HordeForge Cost Overview",
        "description": "Cost monitoring dashboard for HordeForge multi-tenant pipeline orchestration",
        "widgets": [
            {"type": "timeseries", "metric": "hordeforge.total_cost_usd", "title": "Total Cost"},
            {
                "type": "timeseries",
                "metric": "hordeforge.total_input_tokens",
                "title": "Input Tokens",
            },
            {
                "type": "timeseries",
                "metric": "hordeforge.total_output_tokens",
                "title": "Output Tokens",
            },
            {
                "type": "alert_value",
                "metric": "hordeforge.budget_used_percent",
                "title": "Budget Used %",
            },
        ],
    },
    "grafana": {
        "title": "HordeForge Cost Overview",
        "description": "Cost monitoring dashboard for HordeForge",
        "panels": [
            {"type": "timeseries", "metric": "hordeforge_total_cost_usd", "title": "Total Cost"},
            {"type": "stat", "metric": "hordeforge_total_input_tokens", "title": "Input Tokens"},
            {"type": "stat", "metric": "hordeforge_total_output_tokens", "title": "Output Tokens"},
        ],
    },
}


def export_default_dashboard(
    format: str = "datadog",
    output_dir: str = "dashboards",
) -> str:
    """Export default dashboard configuration."""
    config = DEFAULT_DASHBOARD_CONFIGS.get(format)
    if not config:
        raise ValueError(f"Unknown format: {format}")

    output_path = os.path.join(output_dir, f"hordeforge_cost_{format}.json")
    DashboardExporter.to_json_file({}, output_path, format)
    return output_path
