"""Kubernetes client utilities (HF-P7-003)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import kubernetes library, provide graceful fallback
try:
    from kubernetes.client.rest import ApiException

    from kubernetes import client, config

    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False
    client = None
    config = None
    ApiException = None


class K8sClient:
    """Kubernetes client wrapper."""

    def __init__(self, in_cluster: bool = False, config_file: str | None = None):
        """Initialize Kubernetes client.

        Args:
            in_cluster: Whether to load in-cluster config
            config_file: Path to kubeconfig file
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        if in_cluster:
            config.load_incluster_config()
        elif config_file:
            config.load_kube_config(config_file=config_file)
        else:
            try:
                config.load_kube_config()
            except Exception:
                logger.warning("Failed to load kubeconfig, running in offline mode")
                return

        self._apps_v1 = client.AppsV1Api()
        self._core_v1 = client.CoreV1Api()
        self._networking_v1 = client.NetworkingV1Api()

    def create_deployment(self, namespace: str, manifest: dict[str, Any]) -> dict[str, Any]:
        """Create a deployment.

        Args:
            namespace: Kubernetes namespace
            manifest: Deployment manifest

        Returns:
            Created deployment
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        try:
            return self._apps_v1.create_namespaced_deployment(
                namespace=namespace,
                body=manifest,
            )
        except ApiException as e:
            logger.error("Failed to create deployment: %s", e)
            raise

    def get_deployment(self, name: str, namespace: str = "default") -> dict[str, Any] | None:
        """Get a deployment.

        Args:
            name: Deployment name
            namespace: Kubernetes namespace

        Returns:
            Deployment or None if not found
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        try:
            return self._apps_v1.read_namespaced_deployment(name, namespace)
        except ApiException as e:
            if e.status == 404:
                return None
            logger.error("Failed to get deployment: %s", e)
            raise

    def update_deployment(self, name: str, namespace: str, manifest: dict[str, Any]) -> dict[str, Any]:
        """Update a deployment.

        Args:
            name: Deployment name
            namespace: Kubernetes namespace
            manifest: Updated deployment manifest

        Returns:
            Updated deployment
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        try:
            return self._apps_v1.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=manifest,
            )
        except ApiException as e:
            logger.error("Failed to update deployment: %s", e)
            raise

    def delete_deployment(self, name: str, namespace: str = "default") -> bool:
        """Delete a deployment.

        Args:
            name: Deployment name
            namespace: Kubernetes namespace

        Returns:
            True if deleted successfully
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        try:
            self._apps_v1.delete_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=client.V1DeleteOptions(),
            )
            return True
        except ApiException as e:
            if e.status == 404:
                return False
            logger.error("Failed to delete deployment: %s", e)
            raise

    def scale_deployment(
        self,
        name: str,
        replicas: int,
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Scale a deployment.

        Args:
            name: Deployment name
            replicas: Number of replicas
            namespace: Kubernetes namespace

        Returns:
            Updated deployment
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        try:
            return self._apps_v1.patch_namespaced_deployment_scale(
                name=name,
                namespace=namespace,
                body=client.V1Scale(spec={"replicas": replicas}),
            )
        except ApiException as e:
            logger.error("Failed to scale deployment: %s", e)
            raise

    def create_service(self, namespace: str, manifest: dict[str, Any]) -> dict[str, Any]:
        """Create a service.

        Args:
            namespace: Kubernetes namespace
            manifest: Service manifest

        Returns:
            Created service
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        try:
            return self._core_v1.create_namespaced_service(
                namespace=namespace,
                body=manifest,
            )
        except ApiException as e:
            logger.error("Failed to create service: %s", e)
            raise

    def get_service(self, name: str, namespace: str = "default") -> dict[str, Any] | None:
        """Get a service.

        Args:
            name: Service name
            namespace: Kubernetes namespace

        Returns:
            Service or None if not found
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        try:
            return self._core_v1.read_namespaced_service(name, namespace)
        except ApiException as e:
            if e.status == 404:
                return None
            logger.error("Failed to get service: %s", e)
            raise

    def create_ingress(self, namespace: str, manifest: dict[str, Any]) -> dict[str, Any]:
        """Create an ingress.

        Args:
            namespace: Kubernetes namespace
            manifest: Ingress manifest

        Returns:
            Created ingress
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        try:
            return self._networking_v1.create_namespaced_ingress(
                namespace=namespace,
                body=manifest,
            )
        except ApiException as e:
            logger.error("Failed to create ingress: %s", e)
            raise

    def get_pod_logs(
        self,
        name: str,
        namespace: str = "default",
        container: str | None = None,
        tail_lines: int = 100,
    ) -> str:
        """Get pod logs.

        Args:
            name: Pod name
            namespace: Kubernetes namespace
            container: Container name (optional)
            tail_lines: Number of lines to fetch

        Returns:
            Pod logs
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        try:
            return self._core_v1.read_namespaced_pod_log(
                name=name,
                namespace=namespace,
                container=container,
                tail_lines=tail_lines,
            )
        except ApiException as e:
            logger.error("Failed to get pod logs: %s", e)
            raise

    def list_namespaced_pods(self, namespace: str = "default") -> list[dict[str, Any]]:
        """List pods in namespace.

        Args:
            namespace: Kubernetes namespace

        Returns:
            List of pods
        """
        if not K8S_AVAILABLE:
            raise RuntimeError("kubernetes library not installed")

        try:
            pods = self._core_v1.list_namespaced_pod(namespace)
            return [pod.to_dict() for pod in pods.items]
        except ApiException as e:
            logger.error("Failed to list pods: %s", e)
            raise


def is_kubernetes_available() -> bool:
    """Check if kubernetes library is available.

    Returns:
        True if kubernetes is available
    """
    return K8S_AVAILABLE
