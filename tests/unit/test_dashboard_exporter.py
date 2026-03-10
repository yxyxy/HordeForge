from __future__ import annotations

import json
import os
import tempfile

import pytest

from observability.dashboard_exporter import (
    DEFAULT_DASHBOARD_CONFIGS,
    DashboardExporter,
    export_default_dashboard,
)


def test_datadog_dashboard_generation():
    """Test Datadog dashboard JSON generation."""
    metrics = {"total_cost_usd": 100.0, "budget": 1000.0}
    dashboard = DashboardExporter.to_datadog_dashboard(metrics, "Test Dashboard")

    assert dashboard["title"] == "Test Dashboard"
    assert "widgets" in dashboard
    assert len(dashboard["widgets"]) > 0
    assert dashboard["layout_type"] == "ordered"


def test_datadog_dashboard_has_cost_widget():
    """Test Datadog dashboard has cost widget."""
    dashboard = DashboardExporter.to_datadog_dashboard({})

    cost_widget = None
    for widget in dashboard["widgets"]:
        if "Total Cost" in widget.get("definition", {}).get("title", ""):
            cost_widget = widget
            break

    assert cost_widget is not None


def test_datadog_dashboard_has_tenant_widget():
    """Test Datadog dashboard has tenant breakdown widget."""
    dashboard = DashboardExporter.to_datadog_dashboard({})

    tenant_widget = None
    for widget in dashboard["widgets"]:
        if "Cost by Tenant" in widget.get("definition", {}).get("title", ""):
            tenant_widget = widget
            break

    assert tenant_widget is not None


def test_grafana_dashboard_generation():
    """Test Grafana dashboard JSON generation."""
    metrics = {"total_cost_usd": 100.0}
    dashboard = DashboardExporter.to_grafana_dashboard(metrics, "Test Dashboard")

    assert dashboard["dashboard"]["title"] == "Test Dashboard"
    assert "panels" in dashboard["dashboard"]
    assert len(dashboard["dashboard"]["panels"]) > 0


def test_grafana_dashboard_has_templating():
    """Test Grafana dashboard has tenant templating."""
    dashboard = DashboardExporter.to_grafana_dashboard({})

    templating = dashboard["dashboard"].get("templating", {})
    assert "list" in templating
    assert any(t.get("name") == "tenant_id" for t in templating["list"])


def test_export_to_json_file():
    """Test exporting dashboard to JSON file."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = os.path.join(tmp_dir, "dashboard.json")
        DashboardExporter.to_json_file({}, output_path, "datadog")

        assert os.path.exists(output_path)

        with open(output_path, encoding="utf-8") as f:
            content = json.load(f)
            assert "title" in content


def test_export_default_dashboard():
    """Test exporting default dashboard."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = export_default_dashboard("datadog", tmp_dir)

        assert os.path.exists(output_path)
        assert "hordeforge_cost_datadog.json" in output_path


def test_export_default_dashboard_unknown_format():
    """Test exporting with unknown format raises error."""
    with pytest.raises(ValueError, match="Unknown format"):
        DashboardExporter.to_json_file({}, "/tmp/test.json", "unknown")


def test_default_dashboard_configs_exist():
    """Test default dashboard configs are defined."""
    assert "datadog" in DEFAULT_DASHBOARD_CONFIGS
    assert "grafana" in DEFAULT_DASHBOARD_CONFIGS


def test_default_datadog_config():
    """Test default Datadog config structure."""
    config = DEFAULT_DASHBOARD_CONFIGS["datadog"]
    assert config["title"] == "HordeForge Cost Overview"
    assert "widgets" in config
    assert len(config["widgets"]) > 0


def test_default_grafana_config():
    """Test default Grafana config structure."""
    config = DEFAULT_DASHBOARD_CONFIGS["grafana"]
    assert config["title"] == "HordeForge Cost Overview"
    assert "panels" in config
    assert len(config["panels"]) > 0
