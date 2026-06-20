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

    function analyze(params) {
        const notes = [];
        const lambdaRate =
            (params.vehicles * params.missionsPerVehiclePerDay) / params.operatingHoursPerDay;
        const mu = params.processTimeHours > 0 ? 1 / params.processTimeHours : Infinity;

        const rhoL = params.loadingStations > 0 ? lambdaRate / (params.loadingStations * mu) : Infinity;
        const rhoO = params.offloadStations > 0 ? lambdaRate / (params.offloadStations * mu) : Infinity;

        const pwL = erlangC(lambdaRate, mu, params.loadingStations);
        const pwO = erlangC(lambdaRate, mu, params.offloadStations);

        const wqL = meanWaitHours(lambdaRate, mu, params.loadingStations);
        const wqO = meanWaitHours(lambdaRate, mu, params.offloadStations);

        const wLoad = (Number.isFinite(wqL) ? wqL : Infinity) + params.processTimeHours;
        const wOffload = (Number.isFinite(wqO) ? wqO : Infinity) + params.processTimeHours;
        const cycle = wLoad + params.missionDurationHours + wOffload;

        const devicesRequired = Number.isFinite(cycle) ? lambdaRate * cycle : Infinity;
        const deviceFloor = params.vehicles;
        const devicesRec = Math.max(
            deviceFloor,
            Number.isFinite(devicesRequired)
                ? Math.ceil(devicesRequired * (1 + params.deviceBufferFraction))
                : deviceFloor
        );

        const sLMin = stationsRequired(lambdaRate, mu, params.utilizationTarget);
        const sOMin = stationsRequired(lambdaRate, mu, params.utilizationTarget);

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
        return {
            vehicles: config.numVehicles,
            missionsPerVehiclePerDay: config.missionsPerVehiclePerDay,
            missionDurationHours: config.missionDuration / tph,
            processTimeHours: config.processTime / tph,
            portsPerVehicle: shared.portsPerVehicle || 2,
            loadingStations: config.numLoadingStations,
            offloadStations: config.numOffloadStations,
            devicePool: config.totalDevices,
            operatingHoursPerDay: shared.operatingHoursPerDay || 24,
            utilizationTarget: shared.utilizationTarget || 0.85,
            deviceBufferFraction: shared.deviceBufferFraction || 0.1,
        };
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
        inferObservedBottleneck,
        erlangC,
    };
})(window);
