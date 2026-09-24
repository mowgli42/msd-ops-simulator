Feature: Shared load/offload cabinet model
  As a logistics planner
  I want the capacity model to treat a shared Linux cabinet correctly
  So that ρ_L and ρ_O reported independently do not hide cabinet occupancy

  Background:
    Given OpsParameters supports shared_station, cabinet_slots, and slots_in_use
    And shared_station false preserves independent loading_stations and offload_stations

  Scenario: Combined cabinet utilization with one usable slot
    Given lambda is 1 device per hour
    And load_time_hours is 0.5
    And offload_time_hours is 0.5
    And shared_station is true
    And slots_in_use is 1
    When analyze runs
    Then cabinet_rho equals 1.0
    And the CLI notes slots_available and slots_in_use

  Scenario: Second slot halves cabinet utilization
    Given the same rates as the one-slot case
    And slots_in_use is 2
    When analyze runs
    Then cabinet_rho equals 0.5

  Scenario: High-data offload is unstable on one slot
    Given effective offload_time_hours is 1.8
    And slots_in_use is 1
    And shared_station is true
    When analyze runs
    Then the result is marked offload or shared_station unstable
