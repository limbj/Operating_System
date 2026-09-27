"""Processor scheduling simulator core engine.

This module contains the scheduling logic shared by the CLI, the PyQt GUI, and
legacy compatibility wrappers (FCFS.py, RR.py, ...).

The simulation models up to four CPU cores:
- P-Core: processes 2 units of work per second, consumes 3 W while active,
  and incurs a 0.5 W startup cost after an idle period.
- E-Core: processes 1 unit of work per second, consumes 1 W while active,
  and incurs a 0.1 W startup cost after an idle period.

Supported algorithms: FCFS, RR, SPN, SRTN, HRRN, DRR.
DRR implements the project's GPT/complexity-aware P/E-core allocation policy
and a dynamic time-quantum table based on remaining work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ALGORITHMS = ("FCFS", "RR", "SPN", "SRTN", "HRRN", "DRR")


@dataclass(frozen=True)
class ProcessSpec:
    pid: int
    arrival_time: int
    burst_time: int
    gpt_model: str = "N/A"
    complexity: int = 0


@dataclass
class ProcessRuntime:
    spec: ProcessSpec
    sequence: int
    remaining_work: int = field(init=False)
    executed_work: int = 0
    run_ticks: int = 0
    waiting_ticks: int = 0
    first_start_time: Optional[int] = None
    completion_time: Optional[int] = None
    quantum: int = 0
    quantum_used: int = 0
    status: str = "pending"
    last_core_id: Optional[int] = None

    def __post_init__(self) -> None:
        self.remaining_work = self.spec.burst_time

    @property
    def pid(self) -> int:
        return self.spec.pid

    @property
    def arrival_time(self) -> int:
        return self.spec.arrival_time

    @property
    def burst_time(self) -> int:
        return self.spec.burst_time

    @property
    def complexity(self) -> int:
        return self.spec.complexity

    @property
    def gpt_model(self) -> str:
        return self.spec.gpt_model


@dataclass
class Core:
    core_id: int
    core_type: Optional[str]
    current: Optional[ProcessRuntime] = None
    power_on: bool = False
    power_usage: float = 0.0

    @property
    def active(self) -> bool:
        return self.core_type in ("P", "E")

    @property
    def speed(self) -> int:
        if self.core_type == "P":
            return 2
        if self.core_type == "E":
            return 1
        return 0

    @property
    def active_power(self) -> float:
        if self.core_type == "P":
            return 3.0
        if self.core_type == "E":
            return 1.0
        return 0.0

    @property
    def startup_power(self) -> float:
        if self.core_type == "P":
            return 0.5
        if self.core_type == "E":
            return 0.1
        return 0.0


@dataclass(frozen=True)
class ProcessResult:
    pid: int
    arrival_time: int
    burst_time: int
    run_time: int
    waiting_time: int
    turnaround_time: int
    normalized_turnaround_time: float
    response_time: int
    completion_time: int
    status: str
    gpt_model: str
    complexity: int
    executed_work: int


@dataclass
class SimulationResult:
    algorithm: str
    duration: int
    process_results: List[ProcessResult]
    core_types: Dict[int, Optional[str]]
    core_timelines: Dict[int, List[int]]
    core_power_history: Dict[int, List[float]]
    core_power_usage: Dict[int, float]
    total_power_history: List[float]
    ready_queue_history: List[List[int]]

    @property
    def completed(self) -> List[ProcessResult]:
        return [p for p in self.process_results if p.status == "completed"]

    @property
    def terminated(self) -> List[ProcessResult]:
        return [p for p in self.process_results if p.status == "terminated"]

    @property
    def total_power_usage(self) -> float:
        return round(sum(self.core_power_usage.values()), 1)

    @property
    def p_core_power_usage(self) -> float:
        return round(
            sum(v for cid, v in self.core_power_usage.items() if self.core_types[cid] == "P"),
            1,
        )

    @property
    def e_core_power_usage(self) -> float:
        return round(
            sum(v for cid, v in self.core_power_usage.items() if self.core_types[cid] == "E"),
            1,
        )

    @property
    def average_waiting_time(self) -> float:
        rows = self.completed
        if not rows:
            return 0.0
        return round(sum(p.waiting_time for p in rows) / len(rows), 2)

    @property
    def average_normalized_turnaround_time(self) -> float:
        rows = self.completed
        if not rows:
            return 0.0
        return round(sum(p.normalized_turnaround_time for p in rows) / len(rows), 2)


class Simulator:
    """Discrete-time scheduler simulator."""

    def __init__(
        self,
        process_specs: Sequence[ProcessSpec],
        core_config: Sequence[int],
        algorithm: str,
        time_quantum: int = 2,
        max_ticks: int = 10000,
    ) -> None:
        self.algorithm = algorithm.upper()
        self.time_quantum = time_quantum
        self.max_ticks = max_ticks

        self._validate(process_specs, core_config)

        self.processes = [ProcessRuntime(spec, i) for i, spec in enumerate(process_specs)]
        self.pending = sorted(self.processes, key=lambda p: (p.arrival_time, p.sequence))
        self.ready: List[ProcessRuntime] = []
        self.finished: List[ProcessRuntime] = []

        padded = list(core_config) + [0] * (4 - len(core_config))
        padded = padded[:4]
        self.cores = [
            Core(i, None if value == 0 else "P" if value == 1 else "E")
            for i, value in enumerate(padded)
        ]

        self.core_timelines: Dict[int, List[int]] = {i: [] for i in range(4)}
        self.core_power_history: Dict[int, List[float]] = {i: [] for i in range(4)}
        self.total_power_history: List[float] = []
        self.ready_queue_history: List[List[int]] = []

    def _validate(self, process_specs: Sequence[ProcessSpec], core_config: Sequence[int]) -> None:
        if self.algorithm not in ALGORITHMS:
            raise ValueError("지원하지 않는 알고리즘입니다: %s" % self.algorithm)
        if not process_specs:
            raise ValueError("프로세스를 하나 이상 입력해야 합니다.")
        if len(core_config) > 4:
            raise ValueError("프로세서는 최대 4개까지만 사용할 수 있습니다.")
        if any(value not in (0, 1, 2) for value in core_config):
            raise ValueError("코어 값은 0(Off), 1(P-Core), 2(E-Core)만 사용할 수 있습니다.")
        if list(core_config).count(1) > 3:
            raise ValueError("P-Core는 최대 3개까지 사용할 수 있습니다.")
        if list(core_config).count(2) > 1:
            raise ValueError("E-Core는 최대 1개까지 사용할 수 있습니다.")
        if not any(value in (1, 2) for value in core_config):
            raise ValueError("활성화된 코어가 하나 이상 필요합니다.")
        if self.algorithm == "RR" and self.time_quantum <= 0:
            raise ValueError("RR의 Time Quantum은 1 이상이어야 합니다.")

        pids = set()
        for spec in process_specs:
            if spec.pid in pids:
                raise ValueError("중복된 PID가 있습니다: %s" % spec.pid)
            pids.add(spec.pid)
            if spec.pid <= 0:
                raise ValueError("PID는 1 이상의 정수여야 합니다.")
            if spec.arrival_time < 0:
                raise ValueError("Arrival Time은 0 이상이어야 합니다.")
            if not 1 <= spec.burst_time <= 45:
                raise ValueError("Burst Time은 1~45 범위여야 합니다.")
            if self.algorithm == "DRR" and not 1 <= spec.complexity <= 30:
                raise ValueError("DRR의 Complexity는 1~30 범위여야 합니다.")

    @property
    def active_cores(self) -> List[Core]:
        return [core for core in self.cores if core.active]

    @staticmethod
    def dynamic_quantum(remaining_work: int) -> int:
        if remaining_work <= 10:
            return 2
        if remaining_work <= 20:
            return 4
        if remaining_work <= 30:
            return 6
        return 8

    def _add_arrivals(self, current_time: int) -> None:
        arrivals = [p for p in self.pending if p.arrival_time == current_time]
        if not arrivals:
            return
        for process in arrivals:
            self.pending.remove(process)
            process.status = "ready"
            self.ready.append(process)

    def _assign(self, core: Core, process: ProcessRuntime, current_time: int) -> None:
        if process in self.ready:
            self.ready.remove(process)
        core.current = process
        process.status = "running"
        process.last_core_id = core.core_id
        if process.first_start_time is None:
            process.first_start_time = current_time
        if self.algorithm == "RR":
            process.quantum = self.time_quantum
            process.quantum_used = 0
        elif self.algorithm == "DRR":
            process.quantum = self.dynamic_quantum(process.remaining_work)
            process.quantum_used = 0

    def _fill_nonpreemptive_or_rr(self, current_time: int) -> None:
        for core in self.active_cores:
            if core.current is not None or not self.ready:
                continue

            if self.algorithm in ("FCFS", "RR"):
                selected = self.ready[0]
            elif self.algorithm == "SPN":
                selected = min(
                    self.ready,
                    key=lambda p: (p.burst_time, p.arrival_time, p.sequence),
                )
            elif self.algorithm == "HRRN":
                def ratio(p: ProcessRuntime) -> float:
                    return (p.waiting_ticks + p.burst_time) / float(p.burst_time)

                selected = max(
                    self.ready,
                    key=lambda p: (ratio(p), -p.arrival_time, -p.sequence),
                )
            else:
                raise RuntimeError("잘못된 non-preemptive 알고리즘 분기")

            self._assign(core, selected, current_time)

    def _schedule_srtn(self, current_time: int) -> None:
        active = self.active_cores
        candidates: List[ProcessRuntime] = list(self.ready)
        for core in active:
            if core.current is not None:
                candidates.append(core.current)

        # Remove accidental duplicates while preserving object identity.
        unique: List[ProcessRuntime] = []
        seen = set()
        for p in candidates:
            marker = id(p)
            if marker not in seen:
                unique.append(p)
                seen.add(marker)

        selected = sorted(
            unique,
            key=lambda p: (p.remaining_work, p.arrival_time, p.sequence),
        )[: len(active)]
        selected_ids = {id(p) for p in selected}

        # Keep selected processes on their existing cores when possible.
        for core in active:
            if core.current is not None and id(core.current) not in selected_ids:
                released = core.current
                core.current = None
                released.status = "ready"
                if released not in self.ready:
                    self.ready.append(released)

        running_ids = {id(core.current) for core in active if core.current is not None}
        for process in selected:
            if id(process) in running_ids:
                if process in self.ready:
                    self.ready.remove(process)
                continue
            idle_core = next((c for c in active if c.current is None), None)
            if idle_core is None:
                break
            self._assign(idle_core, process, current_time)
            running_ids.add(id(process))

    @staticmethod
    def _drr_prefers_e(process: ProcessRuntime) -> bool:
        return process.remaining_work <= 1 or process.complexity <= 5

    def _schedule_drr(self, current_time: int) -> None:
        idle_e = [c for c in self.active_cores if c.core_type == "E" and c.current is None]
        idle_p = [c for c in self.active_cores if c.core_type == "P" and c.current is None]

        # Phase 1: respect the complexity/remaining-work preference.
        for core in idle_e:
            selected = next((p for p in self.ready if self._drr_prefers_e(p)), None)
            if selected is not None:
                self._assign(core, selected, current_time)

        for core in idle_p:
            selected = next((p for p in self.ready if not self._drr_prefers_e(p)), None)
            if selected is not None:
                self._assign(core, selected, current_time)

        # Phase 2: work-conserving fallback. If the preferred core type is busy,
        # use any available core instead of leaving a process waiting unnecessarily.
        for core in self.active_cores:
            if core.current is None and self.ready:
                self._assign(core, self.ready[0], current_time)

    def _schedule_tick(self, current_time: int) -> None:
        if self.algorithm == "SRTN":
            self._schedule_srtn(current_time)
        elif self.algorithm == "DRR":
            self._schedule_drr(current_time)
        else:
            self._fill_nonpreemptive_or_rr(current_time)

    def _record_waiting(self) -> None:
        for process in self.ready:
            process.waiting_ticks += 1

    def _execute_tick(self, current_time: int) -> None:
        # Record the ready queue after assignment and before execution, matching
        # the old project output semantics.
        self.ready_queue_history.append([p.pid for p in self.ready])
        self._record_waiting()

        for core in self.cores:
            process = core.current
            self.core_timelines[core.core_id].append(process.pid if process else 0)

            if process is None:
                core.power_on = False
                self.core_power_history[core.core_id].append(round(core.power_usage, 1))
                continue

            if not core.power_on:
                core.power_usage += core.startup_power
                core.power_on = True

            work = min(core.speed, process.remaining_work)
            process.remaining_work -= work
            process.executed_work += work
            process.run_ticks += 1
            process.quantum_used += 1
            core.power_usage += core.active_power

            self.core_power_history[core.core_id].append(round(core.power_usage, 1))

        self.total_power_history.append(
            round(sum(core.power_usage for core in self.cores), 1)
        )

        # Completion / forced termination / time-slice expiration are resolved
        # after all cores have executed the same simulated second.
        for core in self.active_cores:
            process = core.current
            if process is None:
                continue

            if self.algorithm == "DRR" and process.burst_time >= 30 and process.executed_work >= 30:
                self._finish(core, process, current_time + 1, "terminated")
                continue

            if process.remaining_work <= 0:
                self._finish(core, process, current_time + 1, "completed")
                continue

            if self.algorithm in ("RR", "DRR") and process.quantum_used >= process.quantum:
                core.current = None
                process.status = "ready"
                process.quantum_used = 0
                if self.algorithm == "DRR":
                    process.quantum = self.dynamic_quantum(process.remaining_work)
                self.ready.append(process)

    def _finish(
        self,
        core: Core,
        process: ProcessRuntime,
        completion_time: int,
        status: str,
    ) -> None:
        process.completion_time = completion_time
        process.status = status
        core.current = None
        self.finished.append(process)

    def run(self) -> SimulationResult:
        current_time = 0

        while self.pending or self.ready or any(c.current for c in self.active_cores):
            if current_time >= self.max_ticks:
                raise RuntimeError("시뮬레이션 최대 시간을 초과했습니다. 입력값을 확인하세요.")

            self._add_arrivals(current_time)
            self._schedule_tick(current_time)
            self._execute_tick(current_time)
            current_time += 1

        rows: List[ProcessResult] = []
        for process in self.finished:
            if process.completion_time is None or process.first_start_time is None:
                continue
            turnaround = process.completion_time - process.arrival_time
            ntt = turnaround / float(process.run_ticks) if process.run_ticks else 0.0
            rows.append(
                ProcessResult(
                    pid=process.pid,
                    arrival_time=process.arrival_time,
                    burst_time=process.burst_time,
                    run_time=process.run_ticks,
                    waiting_time=process.waiting_ticks,
                    turnaround_time=turnaround,
                    normalized_turnaround_time=round(ntt, 2),
                    response_time=process.first_start_time - process.arrival_time,
                    completion_time=process.completion_time,
                    status=process.status,
                    gpt_model=process.gpt_model,
                    complexity=process.complexity,
                    executed_work=process.executed_work,
                )
            )

        return SimulationResult(
            algorithm=self.algorithm,
            duration=current_time,
            process_results=rows,
            core_types={core.core_id: core.core_type for core in self.cores},
            core_timelines=self.core_timelines,
            core_power_history=self.core_power_history,
            core_power_usage={core.core_id: round(core.power_usage, 1) for core in self.cores},
            total_power_history=self.total_power_history,
            ready_queue_history=self.ready_queue_history,
        )


def normalize_process_specs(rows: Iterable[Sequence[object]], algorithm: str) -> List[ProcessSpec]:
    """Convert the legacy row format into ProcessSpec objects.

    Classic algorithms accept rows like ``(pid, at, bt)``.
    DRR accepts ``(pid, at, bt, gpt_model, complexity)``.
    """

    specs: List[ProcessSpec] = []
    is_drr = algorithm.upper() == "DRR"
    for row in rows:
        if len(row) < 3:
            raise ValueError("프로세스 정보는 최소 PID, AT, BT가 필요합니다.")
        pid = int(row[0])
        at = int(row[1])
        bt = int(row[2])
        if is_drr:
            model = str(row[3]) if len(row) >= 4 else "Manual"
            complexity = int(row[4]) if len(row) >= 5 else max(1, min(bt, 30))
        else:
            model = str(row[3]) if len(row) >= 4 else "N/A"
            complexity = int(row[4]) if len(row) >= 5 else 0
        specs.append(ProcessSpec(pid, at, bt, model, complexity))
    return specs


def run_simulation(
    process_specs: Sequence[ProcessSpec],
    core_config: Sequence[int],
    algorithm: str,
    time_quantum: int = 2,
) -> SimulationResult:
    return Simulator(process_specs, core_config, algorithm, time_quantum).run()


def legacy_run(info: Sequence[object], algorithm: str) -> List[object]:
    """Return data in the list layout used by the original team project files."""

    if len(info) < 2:
        raise ValueError("Info는 [process_info, core_info, ...] 형식이어야 합니다.")

    process_rows = info[0]
    core_config = info[1]
    time_quantum = 2
    if algorithm.upper() == "RR" and len(info) >= 3:
        time_quantum = int(info[2])

    specs = normalize_process_specs(process_rows, algorithm)
    result = run_simulation(specs, core_config, algorithm, time_quantum)

    core_queues: List[List[Tuple[int, float]]] = []
    for core_id in range(4):
        timeline = result.core_timelines[core_id]
        power = result.core_power_history[core_id]
        core_queues.append(list(zip(timeline, power)))

    completed_rows = [
        (
            row.pid,
            row.arrival_time,
            row.run_time,
            row.waiting_time,
            row.turnaround_time,
            row.normalized_turnaround_time,
            row.completion_time,
        )
        for row in result.completed
    ]

    output: List[object] = [
        core_queues[0],
        core_queues[1],
        core_queues[2],
        core_queues[3],
        result.total_power_history,
        completed_rows,
        result.ready_queue_history,
    ]

    if algorithm.upper() == "DRR":
        terminated_rows = [
            (
                row.pid,
                row.arrival_time,
                row.run_time,
                row.waiting_time,
                row.turnaround_time,
                row.normalized_turnaround_time,
                row.completion_time,
            )
            for row in result.terminated
        ]
        output.append(terminated_rows)

    return output
