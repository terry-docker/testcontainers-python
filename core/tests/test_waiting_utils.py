import pytest

from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs, wait_for, wait_container_is_ready


def test_wait_for_logs() -> None:
    with DockerContainer("hello-world") as container:
        wait_for_logs(container, "Hello from Docker!")


def test_timeout_is_raised_when_waiting_for_logs() -> None:
    with pytest.raises(TimeoutError), DockerContainer("alpine").with_command("sleep 2") as container:
        wait_for_logs(container, "Hello from Docker!", timeout=1e-3)


def test_wait_for_backwards_compatibility() -> None:
    """Test that the legacy wait_for function still works for simple conditions."""
    import time

    # Test with a condition that returns True immediately
    result = wait_for(lambda: True)
    assert result is True

    # Test with a condition that becomes True after some attempts
    # We'll use a counter to simulate a condition that eventually becomes True
    counter = {"value": 0}

    def condition_after_attempts():
        counter["value"] += 1
        return counter["value"] >= 3  # Becomes True on 3rd attempt

    result = wait_for(condition_after_attempts)
    assert result is True
    assert counter["value"] >= 3


def test_wait_container_is_ready_decorator_basic() -> None:
    """Test the basic wait_container_is_ready decorator functionality."""

    @wait_container_is_ready()
    def simple_check():
        return True

    result = simple_check()
    assert result is True


def test_wait_container_is_ready_decorator_with_container() -> None:
    """Test wait_container_is_ready decorator with a real container."""

    @wait_container_is_ready()
    def check_container_logs(container):
        stdout, stderr = container.get_logs()
        return b"Hello from Docker!" in stdout or b"Hello from Docker!" in stderr

    with DockerContainer("hello-world") as container:
        result = check_container_logs(container)
        assert result is True
