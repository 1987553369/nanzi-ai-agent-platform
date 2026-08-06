"""In-process lifecycle state shared by orchestration health probes."""

from dataclasses import dataclass


@dataclass
class RuntimeHealthState:
    startup_complete: bool = False
    draining: bool = False

    def begin_startup(self) -> None:
        self.startup_complete = False
        self.draining = False

    def finish_startup(self) -> None:
        self.startup_complete = True

    def begin_draining(self) -> None:
        self.draining = True

    def finish_shutdown(self) -> None:
        self.startup_complete = False

    @property
    def ready_for_traffic(self) -> bool:
        return self.startup_complete and not self.draining


runtime_health = RuntimeHealthState()
