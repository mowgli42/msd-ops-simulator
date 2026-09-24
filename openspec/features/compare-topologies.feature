Feature: Topology comparison plots over 100 cycles
  As a leadership audience
  I want a repeatable plot and CSV series for 1-1-1 vs 2-3-2 vs 5-3-5
  So that station concurrency vs device pool trade-offs are visible

  Scenario: One command produces core artifacts
    Given topology fixtures and wait_report counters
    When compare_topologies runs with --topologies 1-1-1,2-3-2,5-3-5 --cycles 100
    Then outdir contains a long CSV
    And wait-by-stage PNG
    And per-device wait small-multiples PNG
    And utilization comparison PNG
    And cycle-time recommended-pool PNG
    And a short README documenting commands and V-S-D mapping

  Scenario: High-data 1-1-1 shows offload wait dominating
    Given topology 1-1-1 with high-data offload
    When the 100-cycle compare runs
    Then offload wait dominates the wait-by-stage cluster for 1-1-1

  Scenario: Chart color convention
    Given any wait-stage chart from compare_topologies
    Then load wait uses steel
    And assign wait uses grey
    And offload wait uses amber
