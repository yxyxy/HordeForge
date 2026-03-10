from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any


class MetricsExporter(ABC):
    """Abstract metrics exporter interface."""

    @abstractmethod
    def export(self, metrics: dict[str, Any]) -> bool:
        """Export metrics to external system."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close any open connections."""
        raise NotImplementedError


class PrometheusPushGatewayExporter(MetricsExporter):
    """Push metrics to Prometheus Pushgateway."""

    def __init__(
        self,
        *,
        gateway_url: str | None = None,
        job: str = "hordeforge",
        grouping_key: dict[str, str] | None = None,
    ) -> None:
        self._gateway_url = gateway_url or os.getenv(
            "HORDEFORGE_PROMETHEUS_PUSHGATEWAY_URL",
            "http://localhost:9091",
        )
        self._job = job
        self._grouping_key = grouping_key or {}
        self._session = None

    def _get_session(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
        return self._session

    def export(self, metrics: dict[str, Any]) -> bool:
        """Push metrics to Pushgateway."""
        try:
            session = self._get_session()
            url = f"{self._gateway_url}/metrics/job/{self._job}"
            for key, value in self._grouping_key.items():
                url += f"/{key}/{value}"

            # Convert metrics to Prometheus format
            lines = []
            for name, value in metrics.items():
                if isinstance(value, (int, float)):
                    lines.append(f"{name} {value}")
                elif isinstance(value, dict):
                    for sub_name, sub_value in value.items():
                        if isinstance(sub_value, (int, float)):
                            lines.append(f"{name}_{sub_name} {sub_value}")

            payload = "\n".join(lines) + "\n"
            response = session.post(url, data=payload, timeout=5)
            return response.status_code in (200, 202)
        except Exception:
            return False

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None


class DatadogExporter(MetricsExporter):
    """Export metrics to Datadog."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        app_key: str | None = None,
        site: str = "datadoghq.com",
    ) -> None:
        self._api_key = api_key or os.getenv("HORDEFORGE_DATADOG_API_KEY", "")
        self._app_key = app_key or os.getenv("HORDEFORGE_DATADOG_APP_KEY", "")
        self._site = site
        self._session = None

    def _get_session(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
        return self._session

    def export(self, metrics: dict[str, Any]) -> bool:
        """Send metrics to Datadog."""
        if not self._api_key:
            return False

        try:
            session = self._get_session()
            # Convert to Datadog format
            series = []
            for name, value in metrics.items():
                if isinstance(value, (int, float)):
                    series.append(
                        {
                            "metric": f"hordeforge.{name}",
                            "points": [[self._current_timestamp(), value]],
                            "type": "gauge",
                        }
                    )

            payload = {"series": series}
            url = f"https://api.{self._site}/api/v1/series"
            headers = {"DD-API-KEY": self._api_key}
            if self._app_key:
                headers["DD-APPLICATION-KEY"] = self._app_key

            response = session.post(
                url, json=payload, headers=headers, timeout=5
            )
            return response.status_code in (200, 202)
        except Exception:
            return False

    @staticmethod
    def _current_timestamp() -> int:
        import time

        return int(time.time())

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None


def get_metrics_exporter(
    exporter_type: str | None = None,
    **kwargs,
) -> MetricsExporter | None:
    """Factory function to get appropriate metrics exporter."""
    exporter_type = exporter_type or os.getenv("HORDEFORGE_METRICS_EXPORTER", "")

    if exporter_type == "prometheus_pushgateway":
        return PrometheusPushGatewayExporter(**kwargs)
    elif exporter_type == "datadog":
        return DatadogExporter(**kwargs)
    elif exporter_type:
        raise ValueError(f"Unknown metrics exporter: {exporter_type}")
    return None
