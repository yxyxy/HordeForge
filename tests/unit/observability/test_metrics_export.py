"""Unit tests for metrics export (HF-P14-006-ST01)."""

from unittest.mock import MagicMock, patch

from scheduler.jobs.metrics_exporter import (
    MetricsExporterJob,
    create_metrics_exporter_job,
    trigger_metrics_export,
)


class TestMetricsExporterJob:
    """Tests for MetricsExporterJob."""

    def test_create_prometheus_exporter(self):
        """Test creating Prometheus Pushgateway exporter."""
        with patch("scheduler.jobs.metrics_exporter.PrometheusPushGatewayExporter") as mock:
            mock_instance = MagicMock()
            mock_instance.export.return_value = True
            mock.return_value = mock_instance

            job = MetricsExporterJob(
                exporter_type="prometheus_pushgateway",
                interval_seconds=60,
                metrics=MagicMock(),
            )
            exporter = job._create_exporter()

            assert exporter is not None
            mock.assert_called_once()

    def test_create_datadog_exporter(self):
        """Test creating Datadog exporter."""
        with patch("scheduler.jobs.metrics_exporter.DatadogExporter") as mock:
            mock_instance = MagicMock()
            mock_instance.export.return_value = True
            mock.return_value = mock_instance

            job = MetricsExporterJob(
                exporter_type="datadog",
                interval_seconds=60,
                metrics=MagicMock(),
                api_key="test_key",
            )
            exporter = job._create_exporter()

            assert exporter is not None
            mock.assert_called_once()

    def test_export_metrics_success(self):
        """Test successful metrics export."""
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = True
        mock_metrics = MagicMock()
        mock_metrics.render_prometheus.return_value = "test_metric 1.0\n"

        with patch.object(
            MetricsExporterJob,
            "_create_exporter",
            return_value=mock_exporter,
        ):
            job = MetricsExporterJob(
                exporter_type="prometheus_pushgateway",
                interval_seconds=60,
                metrics=mock_metrics,
            )
            job._exporter = mock_exporter
            result = job._export_metrics()

            assert result is True
            mock_exporter.export.assert_called_once()

    def test_export_metrics_failure(self):
        """Test failed metrics export."""
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = False
        mock_metrics = MagicMock()
        mock_metrics.render_prometheus.return_value = "test_metric 1.0\n"

        with patch.object(
            MetricsExporterJob,
            "_create_exporter",
            return_value=mock_exporter,
        ):
            job = MetricsExporterJob(
                exporter_type="prometheus_pushgateway",
                interval_seconds=60,
                metrics=mock_metrics,
            )
            job._exporter = mock_exporter
            result = job._export_metrics()

            assert result is False

    def test_parse_metrics(self):
        """Test parsing Prometheus metrics text."""
        job = MetricsExporterJob(
            exporter_type="prometheus_pushgateway",
            interval_seconds=60,
            metrics=MagicMock(),
        )

        metrics_text = """
# HELP test_metric A test metric
# TYPE test_metric gauge
test_metric 1.0
another_metric 2.5
invalid_metric abc
"""
        result = job._parse_metrics(metrics_text)

        assert result["test_metric"] == 1.0
        assert result["another_metric"] == 2.5
        assert "invalid_metric" not in result

    def test_export_once(self):
        """Test single export call."""
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = True
        mock_metrics = MagicMock()
        mock_metrics.render_prometheus.return_value = "metric 1.0\n"

        job = MetricsExporterJob(
            exporter_type="prometheus_pushgateway",
            interval_seconds=60,
            metrics=mock_metrics,
        )
        job._exporter = mock_exporter

        result = job.export_once()
        assert result is True


class TestCreateMetricsExporterJob:
    """Tests for create_metrics_exporter_job factory."""

    def test_create_with_prometheus_config(self):
        """Test creating job with Prometheus config."""
        mock_config = MagicMock()
        mock_config.metrics_exporter = "prometheus_pushgateway"
        mock_config.metrics_export_interval_seconds = 60
        mock_config.prometheus_pushgateway_url = "http://localhost:9091"
        mock_config.datadog_api_key = ""
        mock_config.datadog_app_key = ""
        mock_config.datadog_site = "datadoghq.com"

        job = create_metrics_exporter_job(mock_config)
        assert job is not None
        assert job._exporter_type == "prometheus_pushgateway"

    def test_create_with_datadog_config(self):
        """Test creating job with Datadog config."""
        mock_config = MagicMock()
        mock_config.metrics_exporter = "datadog"
        mock_config.metrics_export_interval_seconds = 60
        mock_config.prometheus_pushgateway_url = "http://localhost:9091"
        mock_config.datadog_api_key = "test_api_key"
        mock_config.datadog_app_key = "test_app_key"
        mock_config.datadog_site = "datadoghq.com"

        job = create_metrics_exporter_job(mock_config)
        assert job is not None
        assert job._exporter_type == "datadog"

    def test_create_without_config(self):
        """Test creating job without exporter config."""
        mock_config = MagicMock()
        mock_config.metrics_exporter = ""

        job = create_metrics_exporter_job(mock_config)
        assert job is None


class TestTriggerMetricsExport:
    """Tests for manual metrics export trigger."""

    def test_trigger_without_exporter(self):
        """Test triggering export when exporter not initialized."""
        # Reset module-level variable
        import scheduler.jobs.metrics_exporter as me

        original = me._metrics_exporter_job
        me._metrics_exporter_job = None

        result = trigger_metrics_export()

        assert result["status"] == "error"
        assert "not initialized" in result["message"]

        # Restore
        me._metrics_exporter_job = original
