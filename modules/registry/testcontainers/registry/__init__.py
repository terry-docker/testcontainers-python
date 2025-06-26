import time
from io import BytesIO
from tarfile import TarFile, TarInfo
from typing import Any, Optional

import bcrypt

from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy
from testcontainers.core.waiting_utils import wait_container_is_ready as wait_container_is_ready


class DockerRegistryContainer(DockerContainer):
    # https://docs.docker.com/registry/
    credentials_path: str = "/htpasswd/credentials.txt"

    def __init__(
        self,
        image: str = "registry:2",
        port: int = 5000,
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(image=image, **kwargs)
        self.port: int = port
        self.username: Optional[str] = username
        self.password: Optional[str] = password
        self.with_exposed_ports(self.port)

    def _copy_credentials(self) -> None:
        # Create credentials and write them to the container
        if self.password is None:
            raise ValueError("Password cannot be None")
        hashed_password: str = bcrypt.hashpw(
            self.password.encode("utf-8"),
            bcrypt.gensalt(rounds=12, prefix=b"2a"),
        ).decode("utf-8")
        content: bytes = f"{self.username}:{hashed_password}".encode("utf-8")  # noqa: UP012

        with BytesIO() as tar_archive_object, TarFile(fileobj=tar_archive_object, mode="w") as tmp_tarfile:
            tarinfo: TarInfo = TarInfo(name=self.credentials_path)
            tarinfo.size = len(content)
            tarinfo.mtime = int(time.time())

            tmp_tarfile.addfile(tarinfo, BytesIO(content))
            tar_archive_object.seek(0)
            self.get_wrapped_container().put_archive("/", tar_archive_object)

    def start(self) -> "DockerRegistryContainer":
        if self.username and self.password:
            self.with_env("REGISTRY_AUTH_HTPASSWD_REALM", "local-registry")
            self.with_env("REGISTRY_AUTH_HTPASSWD_PATH", self.credentials_path)

            # Start container first without wait strategy
            super().start()
            # Copy credentials after container is running
            self._copy_credentials()

            # Now apply wait strategy with authentication
            wait_strategy = (
                HttpWaitStrategy(self.port, "/v2")
                .with_basic_credentials(self.username, self.password)
                .for_status_code(200)
            )
            wait_strategy.wait_until_ready(self)
        else:
            # Use HttpWaitStrategy for unauthenticated registry
            wait_strategy = HttpWaitStrategy(self.port, "/v2").for_status_code(200)
            self.waiting_for(wait_strategy)
            super().start()

        return self

    def get_registry(self) -> str:
        host: str = self.get_container_host_ip()
        port: str = self.get_exposed_port(self.port)
        return f"{host}:{port}"
