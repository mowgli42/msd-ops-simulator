Feature: Wait accounting and wait_report CLI
  As a planner choosing buy-devices vs cut-process-time
  I want per-device hours waiting for the next step
  So that queue length is not confused with constraint type

  Scenario: Engine accumulates wait counters without changing tick order
    Given the AGENTS.md tick order
    When the sim runs
    Then devices accumulate wait_load_ticks wait_assign_ticks wait_offload_ticks
    And service_load_ticks service_offload_ticks mission_ticks
    And service time is not counted as wait

  Scenario: wait_report stops at completed missions
    Given fixtures/topologies/1-1-1.yaml
    When wait_report runs with --missions 100
    Then it stops after 100 completed missions not 100 ticks
    And it writes CSV and PNG artifacts

  Scenario: Offload saturation shows offload wait dominance
    Given an offload-saturated fixture
    When wait_report runs
    Then wait_offload totals greatly exceed wait_assign totals

  Scenario: Tiny pool with idle bays shows assign wait dominance
    Given a tiny device pool and idle stations
    When wait_report runs
    Then assign or device wait dominates
