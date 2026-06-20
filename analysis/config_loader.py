"""Load shared YAML fixtures for analysis and sim sync."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    process_time_hours: float
    utilization_target: float
    device_buffer_fraction: float

    @property
    def mission_duration_ticks(self) -> int:
        return hours_to_ticks(self.mission_duration_hours, self.ticks_per_hour)

    @property
    def process_time_ticks(self) -> int:
        return hours_to_ticks(self.process_time_hours, self.ticks_per_hour)


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
    analysis = data.get("analysis") or {}

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
        process_time_hours=float(durations.get("process", 0.5)),
        utilization_target=float(analysis.get("utilization_target", 0.85)),
        device_buffer_fraction=float(analysis.get("device_buffer_fraction", 0.10)),
    )


def to_ops_parameters(cfg: SharedConfig) -> OpsParameters:
    return OpsParameters(
        vehicles=cfg.vehicles,
        missions_per_vehicle_per_day=cfg.missions_per_vehicle_per_day,
        mission_duration_hours=cfg.mission_duration_hours,
        process_time_hours=cfg.process_time_hours,
        ports_per_vehicle=cfg.ports_per_vehicle,
        loading_stations=cfg.loading_stations,
        offload_stations=cfg.offload_stations,
        device_pool=cfg.device_pool,
        operating_hours_per_day=cfg.operating_hours_per_day,
        utilization_target=cfg.utilization_target,
        device_buffer_fraction=cfg.device_buffer_fraction,
    )


def ops_from_sim_sliders(
    *,
    vehicles: int,
    missions_per_vehicle_per_day: float,
    device_pool: int,
    loading_stations: int,
    offload_stations: int,
    mission_ticks: int,
    process_ticks: int,
    ticks_per_hour: float,
    operating_hours_per_day: float = 24.0,
    utilization_target: float = 0.85,
    device_buffer_fraction: float = 0.10,
    ports_per_vehicle: int = 2,
) -> OpsParameters:
    return OpsParameters(
        vehicles=vehicles,
        missions_per_vehicle_per_day=missions_per_vehicle_per_day,
        mission_duration_hours=ticks_to_hours(mission_ticks, ticks_per_hour),
        process_time_hours=ticks_to_hours(process_ticks, ticks_per_hour),
        ports_per_vehicle=ports_per_vehicle,
        loading_stations=loading_stations,
        offload_stations=offload_stations,
        device_pool=device_pool,
        operating_hours_per_day=operating_hours_per_day,
        utilization_target=utilization_target,
        device_buffer_fraction=device_buffer_fraction,
    )
