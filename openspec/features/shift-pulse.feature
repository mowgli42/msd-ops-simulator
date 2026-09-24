Feature: Shift-pulse arrival mode
  As an operator whose shifts dump load and offload in windows
  I want analytic T_clear and W_last plus a sim pulse mode
  So that last-device wait is not understated by smooth daily λ

  Scenario: Smooth mode remains the default
    Given a fixture without arrival.mode or with mode smooth
    When regression and capacity analysis run
    Then results match the pre-shift-pulse baseline behavior

  Scenario: Worked example one slot
    Given 8 returning devices
    And c equals 1
    And T_O equals 0.5 hours
    And arrival mode is shift
    When pulse metrics are computed
    Then T_clear equals 4.0 hours
    And W_last equals 3.5 hours

  Scenario: Worked example two slots
    Given 8 returning devices
    And c equals 2
    And T_O equals 0.5 hours
    When pulse metrics are computed
    Then T_clear equals 2.0 hours
    And W_last equals 1.5 hours

  Scenario: CLI prints window metrics
    Given fixtures/shared-cabinet.yaml
    When capacity_model runs with --arrival shift --window-hours 2
    Then output includes T_clear W_last lambda_window and cabinet rho in the window
