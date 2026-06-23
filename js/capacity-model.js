/**
 * M/M/c capacity model — JS port aligned with analysis/capacity_model.py
 * Keep formulas in sync with docs/CAPACITY_ANALYSIS.md
 */
(function (global) {
    function factorial(n) {
        let v = 1;
        for (let i = 2; i <= n; i++) v *= i;
        return v;
    }

    function erlangC(lambdaRate, mu, servers) {
        if (servers < 1 || lambdaRate <= 0 || mu <= 0) return 0;
        const rho = lambdaRate / (servers * mu);
        if (rho >= 1) return 1;
        const a = lambdaRate / mu;
        let sumTerms = 0;
        for (let n = 0; n < servers; n++) sumTerms += Math.pow(a, n) / factorial(n);
        const last = Math.pow(a, servers) / (factorial(servers) * (1 - rho));
        const denom = sumTerms + last;
        return denom <= 0 ? 0 : last / denom;
    }

    function meanWaitHours(lambdaRate, mu, servers) {
        if (servers < 1 || lambdaRate <= 0) return 0;
        if (lambdaRate >= servers * mu) return Infinity;
        const pw = erlangC(lambdaRate, mu, servers);
        return pw / (servers * mu - lambdaRate);
    }

    function stationsRequired(lambdaRate, mu, utilizationTarget) {
        if (lambdaRate <= 0 || mu <= 0 || utilizationTarget <= 0) return 1;
        return Math.max(1, Math.ceil(lambdaRate / (mu * utilizationTarget)));
    }

    function effectiveOffloadHours(params) {
        if (params.highDataVolumeMode) {
            return params.missionDurationHours * params.offloadFactor;
        }
        return params.offloadTimeHours;
    }

    function fleetFeasible(params, vehicles, atTarget) {
        const trial = { ...params, vehicles };
        const result = analyze(trial);
        if (!result.loadingStable) return { ok: false, factor: 'loading' };
        if (!result.offloadStable) return { ok: false, factor: 'offload' };
        if (result.devicesRecommended > params.devicePool) return { ok: false, factor: 'devices' };
        if (atTarget) {
            if (result.loadingUtilization > params.utilizationTarget) return { ok: false, factor: 'loading' };
            if (result.offloadUtilization > params.utilizationTarget) return { ok: false, factor: 'offload' };
        }
        return { ok: true, factor: 'balanced' };
    }

    function maxSustainableVehicles(params, maxSearch) {
        const cap = maxSearch || 512;

        function search(atTarget) {
            let lo = 1;
            let hi = Math.max(cap, params.vehicles);
            let best = 0;
            let limit = 'balanced';
            while (lo <= hi) {
                const mid = Math.floor((lo + hi) / 2);
                const { ok, factor } = fleetFeasible(params, mid, atTarget);
                if (ok) {
                    best = mid;
                    lo = mid + 1;
                } else {
                    limit = factor;
                    hi = mid - 1;
                }
            }
            if (best > 0) {
                limit = fleetFeasible(params, best + 1, atTarget).factor;
            }
            return { max: best, limit };
        }

        const stable = search(false);
        const target = search(true);
        return {
            maxVehiclesStable: stable.max,
            maxVehiclesAtTarget: target.max,
            limitingFactorStable: stable.limit,
            limitingFactorTarget: target.limit,
        };
    }

    function analyze(params) {
        const notes = [];
        const lambdaRate =
            (params.vehicles * params.missionsPerVehiclePerDay) / params.operatingHoursPerDay;
        const muLoad = params.loadTimeHours > 0 ? 1 / params.loadTimeHours : Infinity;
        const offloadH = effectiveOffloadHours(params);
        const muOffload = offloadH > 0 ? 1 / offloadH : Infinity;

        const rhoL = params.loadingStations > 0 ? lambdaRate / (params.loadingStations * muLoad) : Infinity;
        const rhoO = params.offloadStations > 0 ? lambdaRate / (params.offloadStations * muOffload) : Infinity;

        const pwL = erlangC(lambdaRate, muLoad, params.loadingStations);
        const pwO = erlangC(lambdaRate, muOffload, params.offloadStations);

        const wqL = meanWaitHours(lambdaRate, muLoad, params.loadingStations);
        const wqO = meanWaitHours(lambdaRate, muOffload, params.offloadStations);

        const wLoad = (Number.isFinite(wqL) ? wqL : Infinity) + params.loadTimeHours;
        const wOffload = (Number.isFinite(wqO) ? wqO : Infinity) + offloadH;
        const cycle = wLoad + params.missionDurationHours + wOffload;

        const devicesRequired = Number.isFinite(cycle) ? lambdaRate * cycle : Infinity;
        const deviceFloor = params.vehicles;
        const devicesRec = Math.max(
            deviceFloor,
            Number.isFinite(devicesRequired)
                ? Math.ceil(devicesRequired * (1 + params.deviceBufferFraction))
                : deviceFloor
        );

        const sLMin = stationsRequired(lambdaRate, muLoad, params.utilizationTarget);
        const sOMin = stationsRequired(lambdaRate, muOffload, params.utilizationTarget);

        const loadingStable = rhoL < 1;
        const offloadStable = rhoO < 1;

        let bottleneck = 'balanced';
        if (!loadingStable) {
            bottleneck = 'loading';
            notes.push('loading queue unstable (rho >= 1)');
        } else if (!offloadStable) {
            bottleneck = 'offload';
            notes.push('offload queue unstable (rho >= 1)');
        } else if (devicesRec > params.devicePool) {
            bottleneck = 'devices';
            notes.push(`pool ${params.devicePool} < recommended ${devicesRec}`);
        } else {
            const util = {
                loading: rhoL / params.utilizationTarget,
                offload: rhoO / params.utilizationTarget,
            };
            if (util.loading > 1 || util.offload > 1) {
                bottleneck = util.loading >= util.offload ? 'loading' : 'offload';
            }
        }

        return {
            arrivalRatePerHour: round(lambdaRate, 4),
            loadingUtilization: round(rhoL, 4),
            offloadUtilization: round(rhoO, 4),
            loadingWaitProb: round(pwL, 4),
            offloadWaitProb: round(pwO, 4),
            effectiveOffloadHours: round(offloadH, 4),
            cycleTimeHours: round(cycle, 4),
            devicesRequired: round(devicesRequired, 2),
            devicesRecommended: devicesRec,
            loadingStationsMin: sLMin,
            offloadStationsMin: sOMin,
            bottleneck,
            loadingStable,
            offloadStable,
            notes,
        };
    }

    function paramsFromSim(config, shared) {
        const tph = shared.ticksPerHour || 20;
        const highData = config.highDataVolumeMode || false;
        const offloadFactor = config.offloadFactor != null ? config.offloadFactor : 0.9;
        return {
            vehicles: config.numVehicles,
            missionsPerVehiclePerDay: config.missionsPerVehiclePerDay,
            missionDurationHours: config.missionDuration / tph,
            loadTimeHours: config.loadTime / tph,
            offloadTimeHours: config.offloadTime / tph,
            portsPerVehicle: shared.portsPerVehicle || 2,
            loadingStations: config.numLoadingStations,
            offloadStations: config.numOffloadStations,
            devicePool: config.totalDevices,
            operatingHoursPerDay: shared.operatingHoursPerDay || 24,
            utilizationTarget: shared.utilizationTarget || 0.85,
            deviceBufferFraction: shared.deviceBufferFraction || 0.1,
            highDataVolumeMode: highData,
            offloadFactor,
        };
    }

    function effectiveOffloadTicks(config) {
        if (config.highDataVolumeMode) {
            return Math.max(1, Math.round(config.missionDuration * (config.offloadFactor || 0.9)));
        }
        return config.offloadTime;
    }

    function iterOffloadSensitivity(params, options) {
        const stationsRange = options?.offloadStationsRange || [1, 2, 3, 4, 5, 6];
        const pctValues = options?.offloadPctValues || [0.5, 0.7, 0.9, 1.0, 1.2];
        const rows = [];
        stationsRange.forEach((stations) => {
            pctValues.forEach((pct) => {
                const rowParams = {
                    ...params,
                    offloadStations: stations,
                    highDataVolumeMode: false,
                    offloadTimeHours: params.missionDurationHours * pct,
                };
                const result = analyze(rowParams);
                rows.push({
                    offloadStations: stations,
                    offloadPct: pct,
                    offloadTimeHours: round(rowParams.offloadTimeHours, 2),
                    rhoLoad: result.loadingUtilization,
                    rhoOffload: result.offloadUtilization,
                    bottleneck: result.bottleneck,
                    devicesRecommended: result.devicesRecommended,
                    offloadStationsMin: result.offloadStationsMin,
                });
            });
        });
        return rows;
    }

    function inferObservedBottleneck(metrics) {
        if (metrics.waitingVehicles > 0) return 'devices';
        if (metrics.offloadQueue >= metrics.loadingQueue && metrics.offloadQueue >= 3) return 'offload';
        if (metrics.loadingQueue > metrics.offloadQueue && metrics.loadingQueue >= 3) return 'loading';
        return 'balanced';
    }

    function round(v, d) {
        const f = Math.pow(10, d);
        return Math.round(v * f) / f;
    }

    global.MsdCapacityModel = {
        analyze,
        paramsFromSim,
        effectiveOffloadTicks,
        iterOffloadSensitivity,
        inferObservedBottleneck,
        maxSustainableVehicles,
        erlangC,
    };
})(window);
