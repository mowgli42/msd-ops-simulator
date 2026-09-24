Feature: Recommend buy vs slot vs cut process time
  As leadership deciding which package to fund
  I want one command that scores fixed investment packages
  So that sensitivity CSVs do not require eyeballing

  Scenario: Score the fixed v1 package set
    Given fixtures/shared-cabinet.yaml or a topology code
    When analysis.recommend runs
    Then packages include buy devices
    And use 2nd slot or plus one station
    And cut T_O by 25 percent
    And cut T_O by 50 percent

  Scenario: Unstable packages are marked unstable
    Given a package that leaves cabinet or offload rho at or above 1
    When recommend scores it
    Then stable is no
    And cycle time is not reported as a fake finite value

  Scenario: Long offload on one bay
    Given 1 bay and T_O of 1.8 hours
    When recommend runs
    Then cut T_O or 2nd slot beats buy devices on stability or wait

  Scenario: Low rho short pool
    Given low cabinet utilization and a short device pool
    When recommend runs
    Then buy devices wins
