import tempfile
import time
from pathlib import Path

import pytest

from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import (
    LogMessageWaitStrategy,
    PortWaitStrategy,
    FileExistsWaitStrategy,
    CompositeWaitStrategy,
)


class TestRealDockerIntegration:
    """Integration tests using real Docker containers."""

    def test_log_message_wait_strategy_with_real_container(self):
        """Test LogMessageWaitStrategy with a real container that outputs known logs."""
        strategy = LogMessageWaitStrategy("Hello from Docker!")

        with DockerContainer("hello-world").waiting_for(strategy) as container:
            # If we get here, the strategy worked
            assert container.get_wrapped_container() is not None

    def test_port_wait_strategy_with_real_container(self):
        """Test PortWaitStrategy with a real nginx container."""
        strategy = PortWaitStrategy(80)

        with DockerContainer("nginx:alpine").with_exposed_ports(80).waiting_for(strategy) as container:
            # If we get here, port 80 is available
            assert container.get_exposed_port(80) is not None

    def test_file_exists_wait_strategy_with_existing_file(self):
        """Test FileExistsWaitStrategy with a file that already exists."""
        # Create a file that already exists
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write("test content")
            temp_file_path = temp_file.name

        try:
            # Strategy to wait for the existing file
            strategy = FileExistsWaitStrategy(temp_file_path).with_startup_timeout(5)

            # Simple container - the file already exists so strategy should succeed immediately
            container = DockerContainer("alpine:latest").with_command("sleep 2").waiting_for(strategy)

            with container:
                # If we get here, the file exists and strategy succeeded
                assert Path(temp_file_path).exists()
        finally:
            # Cleanup
            if Path(temp_file_path).exists():
                Path(temp_file_path).unlink()

    def test_composite_wait_strategy_with_real_container(self):
        """Test CompositeWaitStrategy combining log and port strategies."""
        # Wait for both nginx startup log and port availability
        log_strategy = LogMessageWaitStrategy("start worker process")
        port_strategy = PortWaitStrategy(80)
        composite_strategy = CompositeWaitStrategy(log_strategy, port_strategy)

        with DockerContainer("nginx:alpine").with_exposed_ports(80).waiting_for(composite_strategy) as container:
            # If we get here, both conditions were met
            assert container.get_exposed_port(80) is not None
            logs = container.get_logs()
            assert b"start worker process" in logs[0] or b"start worker process" in logs[1]

    def test_wait_strategy_timeout_with_real_container(self):
        """Test that wait strategies properly timeout with real containers."""
        # Use a very short timeout with a condition that won't be met
        strategy = LogMessageWaitStrategy("this_message_will_never_appear").with_startup_timeout(2)

        with pytest.raises(TimeoutError):
            with DockerContainer("alpine:latest").with_command("sleep 10").waiting_for(strategy):
                pass  # Should not reach here

    def test_file_exists_wait_strategy_timeout(self):
        """Test FileExistsWaitStrategy timeout with a file that doesn't exist."""
        # Use a file path that will never exist
        non_existent_file = Path("/tmp/testcontainers_never_created_file_12345.txt")

        # Ensure the file doesn't exist
        if non_existent_file.exists():
            non_existent_file.unlink()

        # Wait for a file that will never be created
        strategy = FileExistsWaitStrategy(non_existent_file).with_startup_timeout(2)

        with pytest.raises(TimeoutError):
            with DockerContainer("alpine:latest").with_command("sleep 5").waiting_for(strategy):
                pass  # Should not reach here


class TestDockerComposeIntegration:
    """Integration tests for wait strategies with Docker Compose."""

    def test_compose_service_wait_strategies(self):
        """Test that wait strategies work with Docker Compose services."""
        from testcontainers.compose import DockerCompose
        import tempfile
        from pathlib import Path

        # Use basic_multiple fixture with two alpine services that output logs
        compose = DockerCompose(
            context=Path(__file__).parent / "compose_fixtures" / "basic_multiple",
            compose_file_name="docker-compose.yaml",
        )

        # Configure wait strategies for both services
        # Wait for the date output that these containers produce
        compose.waiting_for(
            {
                "alpine1": LogMessageWaitStrategy("202").with_startup_timeout(30),  # Date includes year 202X
                "alpine2": LogMessageWaitStrategy("202").with_startup_timeout(30),  # Date includes year 202X
            }
        )

        with compose:
            # Verify both services are running
            container1 = compose.get_container("alpine1")
            container2 = compose.get_container("alpine2")

            assert container1.State == "running"
            assert container2.State == "running"

            # Verify logs contain expected patterns
            logs1 = container1.get_logs()
            logs2 = container2.get_logs()

            # Both containers should have date output (which contains "202" for year 202X)
            assert any(b"202" in log for log in logs1)
            assert any(b"202" in log for log in logs2)

    def test_compose_port_wait_strategies(self):
        """Test port wait strategies with compose services that expose ports."""
        from testcontainers.compose import DockerCompose
        from pathlib import Path

        # Use port_single fixture with nginx service
        compose = DockerCompose(
            context=Path(__file__).parent / "compose_fixtures" / "port_single", compose_file_name="compose.yaml"
        )

        # Wait for nginx to be ready on port 80
        compose.waiting_for({"alpine": PortWaitStrategy(80).with_startup_timeout(30)})

        with compose:
            # Verify service is running and port is accessible
            container = compose.get_container("alpine")
            assert container.State == "running"

            # Verify we can get the exposed port
            exposed_port = container.get_exposed_port(80)
            assert exposed_port is not None
            assert int(exposed_port) > 0

    @pytest.mark.skip("Skipping due to Docker port conflict issue")
    def test_compose_mixed_wait_strategies(self):
        """Test multiple different wait strategies with compose services."""
        from testcontainers.compose import DockerCompose
        from pathlib import Path

        # Use port_multiple fixture with multiple nginx services
        compose = DockerCompose(
            context=Path(__file__).parent / "compose_fixtures" / "port_multiple", compose_file_name="compose.yaml"
        )

        # Use different wait strategies for different services
        compose.waiting_for(
            {
                "alpine": PortWaitStrategy(80).with_startup_timeout(45),  # Wait for main nginx port
                "alpine2": LogMessageWaitStrategy("nginx").with_startup_timeout(45),  # Wait for nginx log message
            }
        )

        with compose:
            # Verify both services are running
            container1 = compose.get_container("alpine")
            container2 = compose.get_container("alpine2")

            assert container1.State == "running"
            assert container2.State == "running"

            # Verify first service has port available
            exposed_port1 = container1.get_exposed_port(80)
            assert exposed_port1 is not None

            # Verify second service has nginx in logs
            logs2 = container2.get_logs()
            assert any(b"nginx" in log for log in logs2)

    def test_compose_wait_strategy_timeout(self):
        """Test that compose wait strategies properly timeout."""
        from testcontainers.compose import DockerCompose
        from pathlib import Path

        compose = DockerCompose(
            context=Path(__file__).parent / "compose_fixtures" / "basic", compose_file_name="docker-compose.yaml"
        )

        # Use a wait strategy that will never succeed with very short timeout
        compose.waiting_for(
            {"alpine": LogMessageWaitStrategy("this_message_will_never_appear").with_startup_timeout(2)}
        )

        with pytest.raises(TimeoutError):
            with compose:
                pass  # Should not reach here

    def test_compose_composite_wait_strategies(self):
        """Test composite wait strategies with compose services."""
        from testcontainers.compose import DockerCompose
        from pathlib import Path

        # Use port_single fixture
        compose = DockerCompose(
            context=Path(__file__).parent / "compose_fixtures" / "port_single", compose_file_name="compose.yaml"
        )

        # Combine log message and port wait strategies
        log_strategy = LogMessageWaitStrategy("nginx").with_startup_timeout(30)
        port_strategy = PortWaitStrategy(80).with_startup_timeout(30)
        composite_strategy = CompositeWaitStrategy(log_strategy, port_strategy)

        compose.waiting_for({"alpine": composite_strategy})

        with compose:
            container = compose.get_container("alpine")
            assert container.State == "running"

            # Both conditions should be met
            exposed_port = container.get_exposed_port(80)
            assert exposed_port is not None

            logs = container.get_logs()
            assert any(b"nginx" in log for log in logs)

    def test_compose_file_exists_wait_strategy(self):
        """Test FileExistsWaitStrategy with compose - wait for host file."""
        from testcontainers.compose import DockerCompose
        from pathlib import Path
        import tempfile

        # Create a temporary file that will exist
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write("compose test content")
            temp_file_path = temp_file.name

        try:
            compose = DockerCompose(
                context=Path(__file__).parent / "compose_fixtures" / "basic", compose_file_name="docker-compose.yaml"
            )

            # Wait for the file that already exists - should succeed quickly
            compose.waiting_for({"alpine": FileExistsWaitStrategy(temp_file_path).with_startup_timeout(10)})

            with compose:
                container = compose.get_container("alpine")
                assert container.State == "running"
                # File should still exist
                assert Path(temp_file_path).exists()
        finally:
            # Cleanup
            if Path(temp_file_path).exists():
                Path(temp_file_path).unlink()
