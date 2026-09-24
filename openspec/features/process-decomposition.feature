Feature: Process-time decomposition
  As a planner evaluating protocol and compression investments
  I want T_O and T_L derived from bytes, rate, compression, and sanitize
  So that buy-devices can be compared to cut-process-time options

  Scenario: Absent process block keeps slider behavior
    Given a fixture without a process block
    When effective_offload_hours is computed
    Then it equals offload_time_hours or mission times offload_factor

  Scenario: Double protocol rate halves extract component
    Given process bytes_per_mission_gb and protocol_rate_MBps
    When protocol_rate_MBps is doubled
    Then the bytes-over-rate extract hours are halved
    And sanitize_hours is unchanged

  Scenario: Compression halves bytes on the wire
    Given compression_ratio 0.5
    When effective offload is derived
    Then transfer hours use half of bytes_per_mission_gb

  Scenario: Sensitivity modes process and buy
    Given a base OpsParameters with shared cabinet fields
    When sensitivity runs with --mode process
    Then CSV rows sweep compression_ratio times protocol_rate_MBps
    When sensitivity runs with --mode buy
    Then CSV rows sweep device_pool times slots_in_use times offload_time_hours
