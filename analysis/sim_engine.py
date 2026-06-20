"""Discrete tick simulator — Python port of index.html state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class State(str, Enum):
    READY = "READY"
    QUEUED_LOADING = "QUEUED_LOADING"
    LOADING = "LOADING"
    LOADED = "LOADED"
    ASSIGNED = "ASSIGNED"
    INSTALLED = "INSTALLED"
    ON_MISSION = "ON_MISSION"
    MISSION_DONE = "MISSION_DONE"
    QUEUED_OFFLOAD = "QUEUED_OFFLOAD"
    OFFLOADING = "OFFLOADING"
    SANITIZED = "SANITIZED"


@dataclass
class Device:
    id: int
    state: State = State.READY
    timer: int = 0
    vehicle_id: int | None = None
    slot_index: int | None = None


@dataclass
class Vehicle:
    id: int
    slots: list[int | None] = field(default_factory=lambda: [None, None])
    in_mission: bool = False
    mission_end_tick: int = 0
    next_mission_earliest_tick: int = 0


@dataclass
class Station:
    id: int
    current_device_id: int | None = None
    busy_until: int = 0


@dataclass
class SimConfig:
    num_vehicles: int = 8
    total_devices: int = 20
    num_loading_stations: int = 2
    num_offload_stations: int = 3
    mission_duration: int = 40
    load_time: int = 10
    offload_time: int = 10
    high_data_volume_mode: bool = False
    offload_factor: float = 0.9
    ports_per_vehicle: int = 2
    seed_loaded_devices: int = 5
    missions_per_vehicle_per_day: float | None = None
    ticks_per_hour: float = 20.0
    operating_hours_per_day: float = 24.0

    @property
    def process_time(self) -> int:
        return self.load_time

    def effective_offload_ticks(self) -> int:
        if self.high_data_volume_mode:
            return max(1, round(self.mission_duration * self.offload_factor))
        return self.offload_time


@dataclass
class SimMetrics:
    sim_tick: int
    missions_completed: int
    loading_queue: int
    offload_queue: int
    waiting_vehicles: int
    missions_per_hour: float


@dataclass
class SimRunResult:
    metrics: SimMetrics
    window_metrics: SimMetrics
    steady: bool


class SimEngine:
    """Timer-driven MSD ops simulator (matches index.html tick order)."""

    def __init__(self, config: SimConfig) -> None:
        self.config = config
        self.sim_tick = 0
        self.missions_completed = 0
        self.devices: list[Device] = []
        self.vehicles: list[Vehicle] = []
        self.loading_stations: list[Station] = []
        self.offload_stations: list[Station] = []
        self.loading_queue: list[int] = []
        self.offload_queue: list[int] = []
        self.reset()

    def reset(self) -> None:
        cfg = self.config
        self.sim_tick = 0
        self.missions_completed = 0
        self.loading_queue = []
        self.offload_queue = []

        self.devices = [Device(id=i + 1) for i in range(cfg.total_devices)]
        self.vehicles = [
            Vehicle(id=i + 1, slots=[None] * cfg.ports_per_vehicle)
            for i in range(cfg.num_vehicles)
        ]
        self.loading_stations = [
            Station(id=i + 1) for i in range(cfg.num_loading_stations)
        ]
        self.offload_stations = [
            Station(id=i + 1) for i in range(cfg.num_offload_stations)
        ]

        seeded = 0
        for device in self.devices:
            if seeded < cfg.seed_loaded_devices and device.state == State.READY:
                device.state = State.LOADED
                seeded += 1

    def tick_once(self) -> None:
        self.sim_tick += 1
        self._process_loading_stations()
        self._process_offload_stations()
        self._queue_ready_for_loading()
        self._assign_loaded_to_vehicles()
        self._start_missions()
        self._end_missions()
        self._queue_for_offload()

    def run(self, ticks: int) -> SimRunResult:
        if ticks < 1:
            return self._result(steady=False)

        window_start = max(1, ticks - 200)
        missions_at_window = self.missions_completed

        for _ in range(ticks):
            self.tick_once()

        window_missions = self.missions_completed - missions_at_window
        window_ticks = ticks - window_start + 1
        tph = 20  # caller can scale; regression uses shared ticks_per_hour

        full = self._metrics(tph)
        window = SimMetrics(
            sim_tick=self.sim_tick,
            missions_completed=window_missions,
            loading_queue=full.loading_queue,
            offload_queue=full.offload_queue,
            waiting_vehicles=full.waiting_vehicles,
            missions_per_hour=(window_missions / window_ticks * tph) if window_ticks else 0.0,
        )
        steady = self._is_steady()
        return SimRunResult(metrics=full, window_metrics=window, steady=steady)

    def run_until_steady(
        self,
        *,
        max_ticks: int = 4000,
        sample_interval: int = 100,
        stable_windows: int = 3,
        ticks_per_hour: float = 20,
    ) -> SimRunResult:
        """Run until queue/wait metrics stabilize or max_ticks."""
        history: list[tuple[int, int, int]] = []
        for _ in range(max_ticks):
            self.tick_once()
            if self.sim_tick % sample_interval == 0:
                m = self._metrics(ticks_per_hour)
                history.append((m.loading_queue, m.offload_queue, m.waiting_vehicles))
                if len(history) > stable_windows:
                    history.pop(0)
                if len(history) == stable_windows and self._history_stable(history):
                    break

        return SimRunResult(
            metrics=self._metrics(ticks_per_hour),
            window_metrics=self._metrics(ticks_per_hour),
            steady=len(history) == stable_windows and self._history_stable(history),
        )

    def _history_stable(self, history: list[tuple[int, int, int]]) -> bool:
        loads = [h[0] for h in history]
        offs = [h[1] for h in history]
        waits = [h[2] for h in history]
        return (
            max(loads) - min(loads) <= 2
            and max(offs) - min(offs) <= 2
            and max(waits) - min(waits) <= 1
        )

    def _is_steady(self) -> bool:
        return self.sim_tick >= 500

    def _metrics(self, ticks_per_hour: float) -> SimMetrics:
        load_q = sum(
            1
            for d in self.devices
            if d.state in (State.QUEUED_LOADING, State.LOADING)
        )
        off_q = sum(
            1
            for d in self.devices
            if d.state in (State.QUEUED_OFFLOAD, State.OFFLOADING)
        )
        waiting = sum(
            1
            for v in self.vehicles
            if not v.in_mission and all(s is None for s in v.slots)
        )
        hours = self.sim_tick / ticks_per_hour if ticks_per_hour else 0
        mph = self.missions_completed / hours if hours > 0 else 0.0
        return SimMetrics(
            sim_tick=self.sim_tick,
            missions_completed=self.missions_completed,
            loading_queue=load_q,
            offload_queue=off_q,
            waiting_vehicles=waiting,
            missions_per_hour=round(mph, 3),
        )

    def _result(self, steady: bool, ticks_per_hour: float = 20) -> SimRunResult:
        m = self._metrics(ticks_per_hour)
        return SimRunResult(metrics=m, window_metrics=m, steady=steady)

    def _process_loading_stations(self) -> None:
        for station in self.loading_stations:
            if station.current_device_id is None and self.loading_queue:
                device_id = self.loading_queue.pop(0)
                device = self._device(device_id)
                if device:
                    station.current_device_id = device_id
                    station.busy_until = self.sim_tick + self.config.load_time
                    device.state = State.LOADING
                    device.timer = station.busy_until

            if station.current_device_id is not None and self.sim_tick >= station.busy_until:
                device = self._device(station.current_device_id)
                if device:
                    device.state = State.LOADED
                    device.timer = 0
                station.current_device_id = None

    def _process_offload_stations(self) -> None:
        for station in self.offload_stations:
            if station.current_device_id is None and self.offload_queue:
                device_id = self.offload_queue.pop(0)
                device = self._device(device_id)
                if device:
                    station.current_device_id = device_id
                    station.busy_until = self.sim_tick + self.config.effective_offload_ticks()
                    device.state = State.OFFLOADING

            if station.current_device_id is not None and self.sim_tick >= station.busy_until:
                device = self._device(station.current_device_id)
                if device:
                    device.state = State.READY
                station.current_device_id = None

    def _queue_ready_for_loading(self) -> None:
        for device in self.devices:
            if device.state == State.READY and device.id not in self.loading_queue:
                self.loading_queue.append(device.id)
                device.state = State.QUEUED_LOADING

    def _assign_loaded_to_vehicles(self) -> None:
        available = [
            d for d in self.devices if d.state == State.LOADED and d.vehicle_id is None
        ]
        if not available:
            return

        for vehicle in self.vehicles:
            if vehicle.in_mission:
                continue
            free_slots = [i for i, s in enumerate(vehicle.slots) if s is None]
            for slot_idx in free_slots:
                if not available:
                    return
                device = available.pop(0)
                device.vehicle_id = vehicle.id
                device.slot_index = slot_idx
                vehicle.slots[slot_idx] = device.id
                device.state = State.INSTALLED

    def _mission_cooldown_ticks(self) -> int | None:
        cfg = self.config
        if not cfg.missions_per_vehicle_per_day or cfg.missions_per_vehicle_per_day <= 0:
            return None
        total_ticks = cfg.operating_hours_per_day * cfg.ticks_per_hour
        return max(1, int(total_ticks / cfg.missions_per_vehicle_per_day))

    def _start_missions(self) -> None:
        cooldown = self._mission_cooldown_ticks()
        for vehicle in self.vehicles:
            if vehicle.in_mission:
                continue
            if cooldown and self.sim_tick < vehicle.next_mission_earliest_tick:
                continue
            if not any(s is not None for s in vehicle.slots):
                continue
            vehicle.in_mission = True
            vehicle.mission_end_tick = self.sim_tick + self.config.mission_duration
            for dev_id in vehicle.slots:
                if dev_id:
                    d = self._device(dev_id)
                    if d:
                        d.state = State.ON_MISSION

    def _end_missions(self) -> None:
        cooldown = self._mission_cooldown_ticks()
        for vehicle in self.vehicles:
            if not vehicle.in_mission or self.sim_tick < vehicle.mission_end_tick:
                continue
            vehicle.in_mission = False
            if cooldown:
                vehicle.next_mission_earliest_tick = self.sim_tick + cooldown
            for dev_id in vehicle.slots:
                if dev_id:
                    device = self._device(dev_id)
                    if device:
                        device.state = State.MISSION_DONE
                        device.vehicle_id = None
                        device.slot_index = None
            vehicle.slots = [None] * self.config.ports_per_vehicle
            self.missions_completed += 1

    def _queue_for_offload(self) -> None:
        for device in self.devices:
            if device.state == State.MISSION_DONE and device.id not in self.offload_queue:
                self.offload_queue.append(device.id)
                device.state = State.QUEUED_OFFLOAD

    def _device(self, device_id: int) -> Device | None:
        for d in self.devices:
            if d.id == device_id:
                return d
        return None
