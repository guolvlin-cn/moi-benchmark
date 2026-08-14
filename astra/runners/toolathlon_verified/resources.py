from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .artifact_contract import missing_observation
from .contract import utc_now


def _key_values(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        fields = line.replace(":", " ").split()
        if len(fields) < 2:
            continue
        try:
            values[fields[0]] = int(fields[1])
        except ValueError:
            continue
    return values


def _process_state(pid: int | None) -> dict[str, Any] | None:
    if pid is None:
        return missing_observation("process_sampler", "process_not_started")
    status = _key_values(Path(f"/proc/{pid}/status"))
    if not status:
        return {
            "pid": pid,
            "available": False,
            "metrics": missing_observation("procfs", "process_not_available"),
        }
    result: dict[str, Any] = {
        "pid": pid,
        "available": True,
        "rss_bytes": status["VmRSS"] * 1024
        if "VmRSS" in status
        else missing_observation("procfs.status", "kernel_not_reported"),
        "peak_rss_bytes": status["VmHWM"] * 1024
        if "VmHWM" in status
        else missing_observation("procfs.status", "kernel_not_reported"),
        "swap_bytes": status["VmSwap"] * 1024
        if "VmSwap" in status
        else missing_observation("procfs.status", "kernel_not_reported"),
        "threads": status["Threads"]
        if "Threads" in status
        else missing_observation("procfs.status", "kernel_not_reported"),
    }
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        result["cpu_seconds"] = (int(stat[13]) + int(stat[14])) / ticks
    except (OSError, ValueError, IndexError):
        result["cpu_seconds"] = missing_observation(
            "procfs.stat", "process_not_available"
        )
    return result


def _cgroup_state(container_id: str | None) -> dict[str, Any]:
    if not container_id:
        return missing_observation("cgroup_v2", "container_not_started")
    candidates = (
        Path(f"/sys/fs/cgroup/system.slice/docker-{container_id}.scope"),
        Path(f"/sys/fs/cgroup/docker/{container_id}"),
    )
    root = next((path for path in candidates if path.is_dir()), None)
    if root is None:
        return missing_observation("cgroup_v2", "container_cgroup_not_visible")

    def scalar(name: str) -> int | dict[str, Any]:
        try:
            value = (root / name).read_text(encoding="utf-8").strip()
            return int(value)
        except (OSError, ValueError):
            return missing_observation("cgroup_v2", "kernel_not_reported")

    return {
        "container_id": container_id,
        "cgroup_path": str(root),
        "memory_current_bytes": scalar("memory.current"),
        "memory_peak_bytes": scalar("memory.peak"),
        "memory_swap_current_bytes": scalar("memory.swap.current"),
        "memory_events": _key_values(root / "memory.events"),
        "cpu_stat": _key_values(root / "cpu.stat"),
        "io_stat": (
            (root / "io.stat").read_text(encoding="utf-8").splitlines()
            if (root / "io.stat").is_file()
            else missing_observation("cgroup_v2", "kernel_not_reported")
        ),
    }


def _network_state(pid: int | None) -> dict[str, Any]:
    if pid is None:
        return missing_observation("procfs.net", "container_not_started")
    path = Path(f"/proc/{pid}/net/dev")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[2:]
    except OSError:
        return missing_observation("procfs.net", "container_process_not_available")
    interfaces: dict[str, dict[str, int]] = {}
    for line in lines:
        name, separator, values = line.partition(":")
        fields = values.split()
        if not separator or len(fields) < 16:
            continue
        interfaces[name.strip()] = {
            "receive_bytes": int(fields[0]),
            "receive_packets": int(fields[1]),
            "transmit_bytes": int(fields[8]),
            "transmit_packets": int(fields[9]),
        }
    return interfaces


class ResourceSampler:
    def __init__(
        self,
        destination: Path,
        *,
        run_id: str,
        system_id: str,
        product_pid: Callable[[], int | None],
        container_id: Callable[[], str | None] | None = None,
        container_pid: Callable[[], int | None] | None = None,
        interval_seconds: float = 1.0,
    ) -> None:
        self.destination = destination
        self.run_id = run_id
        self.system_id = system_id
        self.product_pid = product_pid
        self.container_id = container_id or (lambda: None)
        self.container_pid = container_pid or (lambda: None)
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        if self.destination.exists() and self.destination.stat().st_size:
            raise ValueError("resource usage stream must start empty")
        self._thread = threading.Thread(target=self._run, daemon=True, name="resource-sampler")
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2, self.interval_seconds * 2))
            self._thread = None

    def _sample(self) -> dict[str, Any]:
        memory = _key_values(Path("/proc/meminfo"))
        vmstat = _key_values(Path("/proc/vmstat"))
        try:
            load = [float(item) for item in Path("/proc/loadavg").read_text().split()[:3]]
        except (OSError, ValueError):
            load = []
        return {
            "schema_version": "toolathlon.resource-usage.v1",
            "timestamp": utc_now(),
            "monotonic_ns": time.monotonic_ns(),
            "run_id": self.run_id,
            "system_id": self.system_id,
            "vm": {
                "memory_total_bytes": memory["MemTotal"] * 1024
                if "MemTotal" in memory
                else missing_observation("procfs.meminfo", "kernel_not_reported"),
                "memory_available_bytes": memory["MemAvailable"] * 1024
                if "MemAvailable" in memory
                else missing_observation("procfs.meminfo", "kernel_not_reported"),
                "swap_total_bytes": memory["SwapTotal"] * 1024
                if "SwapTotal" in memory
                else missing_observation("procfs.meminfo", "kernel_not_reported"),
                "swap_free_bytes": memory["SwapFree"] * 1024
                if "SwapFree" in memory
                else missing_observation("procfs.meminfo", "kernel_not_reported"),
                "swap_in_pages": vmstat["pswpin"]
                if "pswpin" in vmstat
                else missing_observation("procfs.vmstat", "kernel_not_reported"),
                "swap_out_pages": vmstat["pswpout"]
                if "pswpout" in vmstat
                else missing_observation("procfs.vmstat", "kernel_not_reported"),
                "load_average": load
                if load
                else missing_observation("procfs.loadavg", "kernel_not_reported"),
            },
            "adapter": _process_state(os.getpid()),
            "product": _process_state(self.product_pid()),
            "task_container": _cgroup_state(self.container_id()),
            "task_container_network": _network_state(self.container_pid()),
            "task_container_network_scope": "host_network_namespace_shared",
        }

    def _run(self) -> None:
        with self.destination.open("a", encoding="utf-8") as stream:
            while True:
                stream.write(
                    json.dumps(
                        self._sample(),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
                if self._stop.wait(self.interval_seconds):
                    break
            # Always capture one terminal sample after the product exits.
            stream.write(
                json.dumps(
                    self._sample(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    def __enter__(self) -> "ResourceSampler":
        self.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()
