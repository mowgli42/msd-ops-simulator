Feature: Topology fixtures V-S-D
  As an analysis operator
  I want site and comparison fixtures keyed as platforms-stations-devices
  So that plot jobs cannot invent a second meaning for the codes

  Scenario: Shared cabinet is the site default fixture
    Given fixtures/shared-cabinet.yaml
    When loaded through to_ops_parameters
    Then shared_station is true
    And cabinet_slots is 2
    And slots_in_use is 1
    And ports_per_vehicle is 1

  Scenario Outline: Topology codes freeze V S D mapping
    Given fixtures/topologies/<code>.yaml
    When loaded through to_ops_parameters
    Then vehicles equals <vehicles>
    And device_pool equals <devices>
    And the station mapping matches the fixture header comments

    Examples:
      | code  | vehicles | devices |
      | 1-1-1 | 1        | 1       |
      | 2-3-2 | 2        | 2       |
      | 5-3-5 | 5        | 5       |

  Scenario: CLI accepts --topology shorthand
    Given topology code 1-1-1
    When capacity_model is invoked with --topology 1-1-1
    Then it loads fixtures/topologies/1-1-1.yaml successfully
