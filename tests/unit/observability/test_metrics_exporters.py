from __future__ import annotations

import pytest

from observability.exporters import (
    DatadogExporter,
    PrometheusPushGatewayExporter,
    get_metrics_exporter,
)


def test_get_metrics_exporter_none_when_empty():
    """Test factory returns None when no exporter type specified."""
    exporter = get_metrics_exporter(None)
    assert exporter is None


def test_get_metrics_exporter_unknown():
    """Test factory rejects unknown exporter."""
    with pytest.raises(ValueError, match="Unknown metrics exporter"):
        get_metrics_exporter("unknown_exporter")


def test_prometheus_pushgateway_exporter_no_url():
    """Test Prometheus Pushgateway exporter with no URL."""
    exporter = PrometheusPushGatewayExporter(gateway_url="")
    # Should not raise, just return False on export
    result = exporter.export({"test_metric": 1.0})
    assert result is False


def test_datadog_exporter_no_api_key():
    """Test Datadog exporter with no API key."""
    exporter = DatadogExporter(api_key="")
    result = exporter.export({"test_metric": 1.0})
    assert result is False


def test_get_metrics_exporter_prometheus():
    """Test factory creates Prometheus exporter."""
    exporter = get_metrics_exporter("prometheus_pushgateway")
    assert isinstance(exporter, PrometheusPushGatewayExporter)


def test_get_metrics_exporter_datadog():
    """Test factory creates Datadog exporter."""
    exporter = get_metrics_exporter("datadog", api_key="test-key")
    assert isinstance(exporter, DatadogExporter)
