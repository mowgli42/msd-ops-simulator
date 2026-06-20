"""Load shared YAML fixtures for analysis and sim sync."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from analysis.capacity_model import OpsParameters


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
        return hours_to_ticks(self.load_time_hours, self.ticks_per_hour)

    @property
    def offload_time_ticks(self) -> int:
        return hours_to_ticks(self.offload_time_hours, self.ticks_per_hour)

    def effective_offload_ticks(self) -> int:
        if self.high_data_volume_mode:
            return max(1, round(self.mission_duration_ticks * self.offload_factor))
        return self.offload_time_ticks


def hours_to_ticks(hours: float, ticks_per_hour: float) -> int:
    return max(1, round(hours * ticks_per_hour))


def ticks_to_hours(ticks: int | float, ticks_per_hour: float) -> float:
    if ticks_per_hour <= 0:
        return 0.0
    return float(ticks) / ticks_per_hour


def load_shared_config(path: str | Path) -> SharedConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    timing = data.get("timing") or {}
    ops = data.get("operations") or {}
    durations = data.get("durations_hours") or {}
    modes = data.get("modes") or {}
    analysis = data.get("analysis") or {}
    legacy_process = durations.get("process")
    load_h = float(durations.get("load", legacy_process if legacy_process is not None else 0.5))
    offload_h = float(durations.get("offload", legacy_process if legacy_process is not None else 0.5))

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
    )
