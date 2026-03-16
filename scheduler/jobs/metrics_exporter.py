"""Metrics exporter scheduler job (HF-P14-006-ST01)."""

from __future__ import annotations

import logging
import threading
from typing import Any

from observability.exporters import (
    DatadogExporter,
    PrometheusPushGatewayExporter,
)
from observability.metrics import RuntimeMetrics

logger = logging.getLogger("hordeforge.metrics_exporter")


class MetricsExporterJob:
    """Periodic metrics export job."""

    def __init__(
        self,
        exporter_type: str,
        interval_seconds: int,
        metrics: RuntimeMetrics,
        **exporter_kwargs,
    ) -> None:
        self._exporter_type = exporter_type
        self._interval_seconds = interval_seconds
        self._metrics = metrics
        self._exporter_kwargs = exporter_kwargs
        self._exporter = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _create_exporter(self):
        """Create metrics exporter based on type."""
        if self._exporter_type == "prometheus_pushgateway":
            return PrometheusPushGatewayExporter(
                gateway_url=self._exporter_kwargs.get("gateway_url"),
            )
        elif self._exporter_type == "datadog":
            return DatadogExporter(
                api_key=self._exporter_kwargs.get("api_key"),
                app_key=self._exporter_kwargs.get("app_key"),
                site=self._exporter_kwargs.get("site", "datadoghq.com"),
            )
        return None

    def start(self) -> None:
        """Start the metrics export job."""
        if self._exporter is None:
            self._exporter = self._create_exporter()

        if self._exporter is None:
            logger.warning("No metrics exporter configured, skipping export job")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(
            "Metrics exporter job started: type=%s interval=%ds",
            self._exporter_type,
            self._interval_seconds,
        )

    def stop(self) -> None:
        """Stop the metrics export job."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._exporter:
            self._exporter.close()
        logger.info("Metrics exporter job stopped")

    def _run_loop(self) -> None:
        """Run the export loop."""
        while not self._stop_event.is_set():
            try:
                self._export_metrics()
            except Exception as e:  # noqa: BLE001
                logger.error("Metrics export failed: %s", e)

            # Wait for interval or stop event
            self._stop_event.wait(timeout=self._interval_seconds)

    def _export_metrics(self) -> bool:
        """Export metrics to external system."""
        if self._exporter is None:
            return False

        try:
            # Get metrics in Prometheus format
            metrics_text = self._metrics.render_prometheus()
            metrics_dict = self._parse_metrics(metrics_text)

            success = self._exporter.export(metrics_dict)
            if success:
                logger.debug("Metrics exported successfully")
            else:
                logger.warning("Metrics export returned failure")
            return success
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to export metrics: %s", e)
            return False

    def _parse_metrics(self, metrics_text: str) -> dict[str, Any]:
        """Parse Prometheus text format to dict."""
        metrics = {}
        for line in metrics_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if " " in line:
                parts = line.rsplit(" ", 1)
                if len(parts) == 2:
                    name = parts[0]
                    try:
                        value = float(parts[1])
                        metrics[name] = value
                    except ValueError:
                        pass
        return metrics

    def export_once(self) -> bool:
        """Export metrics once (for manual triggering)."""
        return self._export_metrics()


def create_metrics_exporter_job(config) -> MetricsExporterJob | None:
    """Create metrics exporter job from config."""
    if not config.metrics_exporter:
        logger.info("No metrics exporter configured")
        return None

    return MetricsExporterJob(
        exporter_type=config.metrics_exporter,
        interval_seconds=config.metrics_export_interval_seconds,
        metrics=RuntimeMetrics(),
        gateway_url=config.prometheus_pushgateway_url,
        api_key=config.datadog_api_key,
        app_key=config.datadog_app_key,
        site=config.datadog_site,
    )


# Module-level job instance
_metrics_exporter_job: MetricsExporterJob | None = None


def start_metrics_exporter(config) -> None:
    """Start the metrics exporter job."""
    global _metrics_exporter_job
    _metrics_exporter_job = create_metrics_exporter_job(config)
    if _metrics_exporter_job:
        _metrics_exporter_job.start()


def stop_metrics_exporter() -> None:
    """Stop the metrics exporter job."""
    global _metrics_exporter_job
    if _metrics_exporter_job:
        _metrics_exporter_job.stop()
        _metrics_exporter_job = None


def trigger_metrics_export() -> dict[str, Any]:
    """Trigger manual metrics export."""
    global _metrics_exporter_job
    if _metrics_exporter_job is None:
        return {"status": "error", "message": "Metrics exporter not initialized"}

    success = _metrics_exporter_job.export_once()
    return {"status": "ok" if success else "error", "exported": success}
