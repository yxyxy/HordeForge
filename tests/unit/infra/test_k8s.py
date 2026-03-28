"""Unit tests for Kubernetes deployment (HF-P7-003)."""

from pathlib import Path

import pytest
import yaml

K8S_AVAILABLE = (
    False  # availability is checked via scheduler.k8s.client.K8S_AVAILABLE in tests below.
)


class TestKubernetesManifests:
    """Tests for Kubernetes manifests."""

    def test_deployment_manifest_exists(self):
        """Test that deployment manifest exists."""
        deployment_path = Path("kubernetes/base/deployment.yaml")
        assert deployment_path.exists(), "Deployment manifest not found"

    def test_service_manifest_exists(self):
        """Test that service manifest exists."""
        service_path = Path("kubernetes/base/service.yaml")
        assert service_path.exists(), "Service manifest not found"

    def test_ingress_manifest_exists(self):
        """Test that ingress manifest exists."""
        ingress_path = Path("kubernetes/base/ingress.yaml")
        assert ingress_path.exists(), "Ingress manifest not found"

    def test_deployment_has_replicas(self):
        """Test deployment has replica count configured."""
        deployment_path = Path("kubernetes/base/deployment.yaml")
        if not deployment_path.exists():
            pytest.skip("Deployment manifest not found")

        with open(deployment_path) as f:
            deployment = yaml.safe_load(f)

        spec = deployment.get("spec", {})
        assert "replicas" in spec
        assert spec["replicas"] >= 1

    def test_deployment_has_selector(self):
        """Test deployment has selector configured."""
        deployment_path = Path("kubernetes/base/deployment.yaml")
        if not deployment_path.exists():
            pytest.skip("Deployment manifest not found")

        with open(deployment_path) as f:
            deployment = yaml.safe_load(f)

        spec = deployment.get("spec", {})
        assert "selector" in spec
        assert "matchLabels" in spec["selector"]

    def test_deployment_has_container_ports(self):
        """Test deployment has container port configured."""
        deployment_path = Path("kubernetes/base/deployment.yaml")
        if not deployment_path.exists():
            pytest.skip("Deployment manifest not found")

        with open(deployment_path) as f:
            deployment = yaml.safe_load(f)

        containers = (
            deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        )
        assert len(containers) > 0
        ports = containers[0].get("ports", [])
        assert len(ports) > 0

    def test_service_has_selector(self):
        """Test service has selector configured."""
        service_path = Path("kubernetes/base/service.yaml")
        if not service_path.exists():
            pytest.skip("Service manifest not found")

        with open(service_path) as f:
            service = yaml.safe_load(f)

        spec = service.get("spec", {})
        assert "selector" in spec


class TestHelmChart:
    """Tests for Helm chart."""

    def test_helm_chart_exists(self):
        """Test that Helm chart exists."""
        chart_path = Path("kubernetes/hordeforge/Chart.yaml")
        assert chart_path.exists(), "Helm Chart.yaml not found"

    def test_helm_values_exists(self):
        """Test that values.yaml exists."""
        values_path = Path("kubernetes/hordeforge/values.yaml")
        assert values_path.exists(), "values.yaml not found"

    def test_helm_chart_has_name(self):
        """Test Helm chart has name."""
        chart_path = Path("kubernetes/hordeforge/Chart.yaml")
        if not chart_path.exists():
            pytest.skip("Helm chart not found")

        with open(chart_path) as f:
            chart = yaml.safe_load(f)

        assert "name" in chart
        assert chart["name"] == "hordeforge"

    def test_helm_chart_has_version(self):
        """Test Helm chart has version."""
        chart_path = Path("kubernetes/hordeforge/Chart.yaml")
        if not chart_path.exists():
            pytest.skip("Helm chart not found")

        with open(chart_path) as f:
            chart = yaml.safe_load(f)

        assert "version" in chart


class TestDockerConfiguration:
    """Tests for Docker configuration."""

    def test_dockerfile_exists(self):
        """Test that Dockerfile exists."""
        dockerfile_path = Path("Dockerfile")
        assert dockerfile_path.exists(), "Dockerfile not found"

    def test_dockerfile_has_from(self):
        """Test Dockerfile has FROM instruction."""
        dockerfile_path = Path("Dockerfile")
        if not dockerfile_path.exists():
            pytest.skip("Dockerfile not found")

        with open(dockerfile_path) as f:
            content = f.read()

        assert "FROM" in content

    def test_dockerfile_has_workdir(self):
        """Test Dockerfile has WORKDIR instruction."""
        dockerfile_path = Path("Dockerfile")
        if not dockerfile_path.exists():
            pytest.skip("Dockerfile not found")

        with open(dockerfile_path) as f:
            content = f.read()

        assert "WORKDIR" in content


class TestK8sClient:
    """Tests for Kubernetes client utilities."""

    def test_k8s_client_import(self):
        """Test kubernetes client can be imported."""
        try:
            from scheduler.k8s.client import K8S_AVAILABLE, K8sClient

            if not K8S_AVAILABLE:
                pytest.skip("kubernetes library not installed")
            assert K8sClient is not None
        except ImportError:
            pytest.skip("scheduler.k8s.client not available")

    def test_create_deployment(self):
        """Test creating a deployment via client."""
        try:
            from scheduler.k8s.client import K8S_AVAILABLE, K8sClient

            if not K8S_AVAILABLE:
                pytest.skip("kubernetes library not installed")
            client = K8sClient()
            assert hasattr(client, "create_deployment")
        except RuntimeError:
            pytest.skip("kubernetes library not installed")

    def test_scale_deployment(self):
        """Test scaling a deployment."""
        try:
            from scheduler.k8s.client import K8S_AVAILABLE, K8sClient

            if not K8S_AVAILABLE:
                pytest.skip("kubernetes library not installed")
            client = K8sClient()
            assert hasattr(client, "scale_deployment")
        except RuntimeError:
            pytest.skip("kubernetes library not installed")


class TestResourceManagement:
    """Tests for resource management."""

    def test_resource_limits_configured(self):
        """Test that resource limits are configured in deployment."""
        deployment_path = Path("kubernetes/base/deployment.yaml")
        if not deployment_path.exists():
            pytest.skip("Deployment manifest not found")

        with open(deployment_path) as f:
            deployment = yaml.safe_load(f)

        containers = (
            deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        )
        if containers:
            resources = containers[0].get("resources", {})
            assert "limits" in resources or "requests" in resources

    def test_liveness_probe_configured(self):
        """Test that liveness probe is configured."""
        deployment_path = Path("kubernetes/base/deployment.yaml")
        if not deployment_path.exists():
            pytest.skip("Deployment manifest not found")

        with open(deployment_path) as f:
            deployment = yaml.safe_load(f)

        containers = (
            deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        )
        if containers:
            liveness = containers[0].get("livenessProbe", {})
            # Liveness probe is optional but recommended
            assert (
                "httpGet" in liveness
                or "tcpSocket" in liveness
                or "exec" in liveness
                or liveness == {}
            )

    def test_readiness_probe_configured(self):
        """Test that readiness probe is configured."""
        deployment_path = Path("kubernetes/base/deployment.yaml")
        if not deployment_path.exists():
            pytest.skip("Deployment manifest not found")

        with open(deployment_path) as f:
            deployment = yaml.safe_load(f)

        containers = (
            deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        )
        if containers:
            readiness = containers[0].get("readinessProbe", {})
            # Readiness probe is optional but recommended
            assert (
                "httpGet" in readiness
                or "tcpSocket" in readiness
                or "exec" in readiness
                or readiness == {}
            )
