"""Load shared YAML fixtures for analysis and sim sync."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from analysis.capacity_model import OpsParameters, ProcessConfig


@dataclass(frozen=True)
class SharedConfig:
    scenario_id: str
    ticks_per_hour: float
    operating_hours_per_day: float
    vehicles: int
    missions_per_vehicle_per_day: float
    ports_per_vehicle: int
    device_pool: int
    loading_stations: int
    offload_stations: int
    mission_duration_hours: float
    load_time_hours: float
    offload_time_hours: float
    high_data_volume_mode: bool
    offload_factor: float
    utilization_target: float
    device_buffer_fraction: float
    shared_station: bool = False
    cabinet_slots: int = 2
    slots_in_use: int = 1
    process: ProcessConfig | None = None
    arrival_mode: str = "smooth"
    preload_window_hours: float = 2.0
    offload_window_hours: float = 2.0
    topology_code: str | None = None

    @property
    def process_time_hours(self) -> float:
        return self.load_time_hours

    @property
    def process_time_ticks(self) -> int:
        return self.load_time_ticks

    @property
    def mission_duration_ticks(self) -> int:
        return hours_to_ticks(self.mission_duration_hours, self.ticks_per_hour)

    @property
    def load_time_ticks(self) -> int:
        hours = (
            OpsParameters(
                load_time_hours=self.load_time_hours,
                process=self.process,
            ).effective_load_hours()
            if self.process
            else self.load_time_hours
        )
        return hours_to_ticks(hours, self.ticks_per_hour)

    @property
    def offload_time_ticks(self) -> int:
        return hours_to_ticks(self.offload_time_hours, self.ticks_per_hour)

    def effective_offload_ticks(self) -> int:
        params = to_ops_parameters(self)
        return hours_to_ticks(params.effective_offload_hours(), self.ticks_per_hour)


def hours_to_ticks(hours: float, ticks_per_hour: float) -> int:
    return max(1, round(hours * ticks_per_hour))


def ticks_to_hours(ticks: int | float, ticks_per_hour: float) -> float:
    if ticks_per_hour <= 0:
        return 0.0
    return float(ticks) / ticks_per_hour


def _parse_process(raw: dict | None) -> ProcessConfig | None:
    if not raw:
        return None
    return ProcessConfig(
        bytes_per_mission_gb=float(raw.get("bytes_per_mission_gb", 40)),
        compression_ratio=float(raw.get("compression_ratio", 0.0)),
        protocol_rate_MBps=float(raw.get("protocol_rate_MBps", 80)),
        mount_overhead_hours=float(raw.get("mount_overhead_hours", 0.05)),
        sanitize_hours=float(raw.get("sanitize_hours", 0.15)),
        preload_gb=float(raw.get("preload_gb", 2)),
        write_rate_MBps=float(raw.get("write_rate_MBps", 80)),
        write_overhead_hours=float(raw.get("write_overhead_hours", 0.0)),
        verify_hours=float(raw.get("verify_hours", 0.0)),
    )


def load_shared_config(path: str | Path) -> SharedConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    timing = data.get("timing") or {}
    ops = data.get("operations") or {}
    durations = data.get("durations_hours") or {}
    modes = data.get("modes") or {}
    analysis = data.get("analysis") or {}
    arrival = data.get("arrival") or {}
    legacy_process = durations.get("process")
    load_h = float(durations.get("load", legacy_process if legacy_process is not None else 0.5))
    offload_h = float(durations.get("offload", legacy_process if legacy_process is not None else 0.5))

    shared = bool(ops.get("shared_station", False))
    cabinet_slots = int(ops.get("cabinet_slots", 2))
    slots_in_use = int(ops.get("slots_in_use", 1 if shared else ops.get("offload_stations", 3)))

    return SharedConfig(
        scenario_id=str(data.get("scenario_id", "baseline")),
        ticks_per_hour=float(timing.get("ticks_per_hour", 20)),
        operating_hours_per_day=float(timing.get("operating_hours_per_day", 24)),
        vehicles=int(ops.get("vehicles", 8)),
        missions_per_vehicle_per_day=float(ops.get("missions_per_vehicle_per_day", 3)),
        ports_per_vehicle=int(ops.get("ports_per_vehicle", 2)),
        device_pool=int(ops.get("device_pool", 20)),
        loading_stations=int(ops.get("loading_stations", 2)),
        offload_stations=int(ops.get("offload_stations", 3)),
        mission_duration_hours=float(durations.get("mission", 2.0)),
        load_time_hours=load_h,
        offload_time_hours=offload_h,
        high_data_volume_mode=bool(modes.get("high_data_volume", False)),
        offload_factor=float(modes.get("offload_factor", 0.9)),
        utilization_target=float(analysis.get("utilization_target", 0.85)),
        device_buffer_fraction=float(analysis.get("device_buffer_fraction", 0.10)),
        shared_station=shared,
        cabinet_slots=cabinet_slots,
        slots_in_use=slots_in_use,
        process=_parse_process(data.get("process")),
        arrival_mode=str(arrival.get("mode", "smooth")),
        preload_window_hours=float(arrival.get("preload_window_hours", 2.0)),
        offload_window_hours=float(arrival.get("offload_window_hours", 2.0)),
        topology_code=data.get("topology_code"),
    )


def to_ops_parameters(cfg: SharedConfig) -> OpsParameters:
    return OpsParameters(
        vehicles=cfg.vehicles,
        missions_per_vehicle_per_day=cfg.missions_per_vehicle_per_day,
        mission_duration_hours=cfg.mission_duration_hours,
        load_time_hours=cfg.load_time_hours,
        offload_time_hours=cfg.offload_time_hours,
        ports_per_vehicle=cfg.ports_per_vehicle,
        loading_stations=cfg.loading_stations,
        offload_stations=cfg.offload_stations,
        device_pool=cfg.device_pool,
        operating_hours_per_day=cfg.operating_hours_per_day,
        utilization_target=cfg.utilization_target,
        device_buffer_fraction=cfg.device_buffer_fraction,
        high_data_volume_mode=cfg.high_data_volume_mode,
        offload_factor=cfg.offload_factor,
        shared_station=cfg.shared_station,
        cabinet_slots=cfg.cabinet_slots,
        slots_in_use=cfg.slots_in_use,
        process=cfg.process,
        arrival_mode=cfg.arrival_mode,
        preload_window_hours=cfg.preload_window_hours,
        offload_window_hours=cfg.offload_window_hours,
    )


def ops_from_sim_sliders(
    *,
    vehicles: int,
    missions_per_vehicle_per_day: float,
    device_pool: int,
    loading_stations: int,
    offload_stations: int,
    mission_ticks: int,
    load_ticks: int,
    offload_ticks: int,
    ticks_per_hour: float,
    operating_hours_per_day: float = 24.0,
    utilization_target: float = 0.85,
    device_buffer_fraction: float = 0.10,
    ports_per_vehicle: int = 2,
    high_data_volume_mode: bool = False,
    offload_factor: float = 0.9,
    shared_station: bool = False,
    cabinet_slots: int = 2,
    slots_in_use: int = 1,
) -> OpsParameters:
    offload_hours = ticks_to_hours(offload_ticks, ticks_per_hour)
    if high_data_volume_mode:
        offload_hours = ticks_to_hours(mission_ticks, ticks_per_hour) * offload_factor
    return OpsParameters(
        vehicles=vehicles,
        missions_per_vehicle_per_day=missions_per_vehicle_per_day,
        mission_duration_hours=ticks_to_hours(mission_ticks, ticks_per_hour),
        load_time_hours=ticks_to_hours(load_ticks, ticks_per_hour),
        offload_time_hours=offload_hours,
        ports_per_vehicle=ports_per_vehicle,
        loading_stations=loading_stations,
        offload_stations=offload_stations,
        device_pool=device_pool,
        operating_hours_per_day=operating_hours_per_day,
        utilization_target=utilization_target,
        device_buffer_fraction=device_buffer_fraction,
        high_data_volume_mode=high_data_volume_mode,
        offload_factor=offload_factor,
        shared_station=shared_station,
        cabinet_slots=cabinet_slots,
        slots_in_use=slots_in_use,
    )


def sim_config_from_shared(cfg: SharedConfig):
    """Build SimConfig from SharedConfig (import lazily to avoid cycles)."""
    from analysis.sim_engine import SimConfig

    params = to_ops_parameters(cfg)
    stations = cfg.slots_in_use if cfg.shared_station else None
    return SimConfig(
        num_vehicles=cfg.vehicles,
        total_devices=cfg.device_pool,
        num_loading_stations=stations if stations is not None else cfg.loading_stations,
        num_offload_stations=stations if stations is not None else cfg.offload_stations,
        mission_duration=cfg.mission_duration_ticks,
        load_time=hours_to_ticks(params.effective_load_hours(), cfg.ticks_per_hour),
        offload_time=hours_to_ticks(params.effective_offload_hours(), cfg.ticks_per_hour),
        high_data_volume_mode=False,  # already folded into offload_time ticks
        offload_factor=cfg.offload_factor,
        ports_per_vehicle=cfg.ports_per_vehicle,
        seed_loaded_devices=min(cfg.device_pool, max(1, cfg.vehicles)),
        missions_per_vehicle_per_day=cfg.missions_per_vehicle_per_day,
        ticks_per_hour=cfg.ticks_per_hour,
        operating_hours_per_day=cfg.operating_hours_per_day,
        shared_station=cfg.shared_station,
        arrival_mode=cfg.arrival_mode,
        preload_window_hours=cfg.preload_window_hours,
        offload_window_hours=cfg.offload_window_hours,
    )
