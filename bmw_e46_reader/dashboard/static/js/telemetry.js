/* ============================================================
   BMW E46 Telemetry Engine
   Real-time data handling, gauge updates, and WebSocket comms
   ============================================================ */

'use strict';

// ── Configuration ──────────────────────────────────────────
const CFG = {
    WS_URL: `ws://${location.host}/ws`,
    RECONNECT_DELAY: 2000,
    MAX_RECONNECT: 50,
    UPDATE_RATE_WINDOW: 20,         // samples for Hz calc
    RPM_MAX: 8000,
    RPM_REDLINE: 7000,
    RPM_SHIFT: 7200,
    GFORCE_MAX: 1.8,               // max G for display scale
    GFORCE_TRAIL_LENGTH: 40,       // dot trail history
    // Alarm thresholds
    THRESH: {
        oil_temp_warn: 130,
        oil_temp_crit: 145,
        coolant_warn: 105,
        coolant_crit: 115,
        oil_press_low: 1.5,
        oil_press_crit: 0.8,
        batt_low: 12.0,
        batt_crit: 11.0,
    }
};

// ── State ─────────────────────────────────────────────────
let ws = null;
let reconnectAttempts = 0;
let connected = false;
let lastUpdateTimes = [];
let simMode = false;
let simInterval = null;

// Lap timer state
const lap = {
    running: false,
    startTime: 0,
    currentMs: 0,
    previousMs: null,
    bestMs: null,
    lapCount: 0,
    sectorDelta: 0,
};

// G-force trail buffer
const gforceTrail = [];

// ── DOM Cache ─────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const DOM = {};
function cacheDom() {
    const ids = [
        'rpmValue', 'rpmBar',
        'oilPressValue', 'oilPressBar',
        'oilTempValue', 'oilTempBar',
        'coolantValue', 'coolantBar',
        'afrValue', 'afrBar',
        'battValue', 'battBar',
        'loadValue', 'loadBar',
        'iatValue', 'iatBar',
        'mafValue', 'mafBar',
        'tpsValue', 'tpsBar',
        'timingValue', 'timingBar',
        'fuelTrimValue', 'fuelTrimBar',
        'speedValue', 'gearValue', 'shiftMode',
        'gforceLat', 'gforceLon', 'gforceCanvas',
        'tractionFL', 'tractionFR', 'tractionRL', 'tractionRR',
        'dscDot', 'dscStatus',
        'currentLap', 'sectorDelta', 'sectorTime', 'prevLap', 'bestLap', 'lapCount',
        'vanosIn', 'vanosEx', 'knock1', 'knock2', 'injTime',
        'smgHydP', 'clutchPos', 'gboxTemp',
        'healthEcu', 'healthSmg', 'healthKline', 'healthSensors', 'healthDtc', 'dtcCount',
        'connDot', 'connText', 'timestamp', 'updateHz', 'lapTimerTop',
        'trackMode',
    ];
    ids.forEach(id => { DOM[id] = $(id); });
}

// ── Utility ───────────────────────────────────────────────
function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

function pct(value, min, max) {
    return clamp(((value - min) / (max - min)) * 100, 0, 100);
}

function formatLap(ms) {
    if (ms == null || ms < 0) return '--:--.---';
    const mins = Math.floor(ms / 60000);
    const secs = Math.floor((ms % 60000) / 1000);
    const millis = Math.floor(ms % 1000);
    return `${mins}:${String(secs).padStart(2, '0')}.${String(millis).padStart(3, '0')}`;
}

function formatDelta(ms) {
    if (ms == null) return '+0.000';
    const sign = ms >= 0 ? '+' : '-';
    const abs = Math.abs(ms);
    return `${sign}${(abs / 1000).toFixed(3)}`;
}

// ── Value Formatting ──────────────────────────────────────
function fmtVal(v, decimals = 1) {
    return v != null ? v.toFixed(decimals) : '--';
}

function fmtInt(v) {
    return v != null ? Math.round(v).toString() : '--';
}

// ── Threshold Classification ──────────────────────────────
function classifyTemp(val, warn, crit) {
    if (val == null) return 'normal';
    if (val >= crit) return 'crit';
    if (val >= warn) return 'warn';
    return 'normal';
}

function classifyLow(val, warn, crit) {
    if (val == null) return 'normal';
    if (val <= crit) return 'crit';
    if (val <= warn) return 'warn';
    return 'normal';
}

function applyValueState(el, state) {
    el.classList.remove('val--normal', 'val--ok', 'val--warn', 'val--crit', 'val--crit-flash');
    if (state === 'crit') {
        el.classList.add('val--crit', 'val--crit-flash');
    } else if (state === 'warn') {
        el.classList.add('val--warn');
    } else {
        el.classList.add('val--normal');
    }
}

function applyBarState(el, state) {
    el.classList.remove('bar--normal', 'bar--warn', 'bar--crit', 'bar--cyan', 'bar--blue', 'bar--rpm');
    if (state === 'crit') {
        el.classList.add('bar--crit');
    } else if (state === 'warn') {
        el.classList.add('bar--warn');
    } else {
        el.classList.add('bar--normal');
    }
}

// ── RPM Update ────────────────────────────────────────────
function updateRPM(rpm) {
    if (rpm == null) {
        DOM.rpmValue.textContent = '----';
        DOM.rpmBar.style.width = '0%';
        return;
    }

    DOM.rpmValue.textContent = Math.round(rpm).toString();
    const p = pct(rpm, 0, CFG.RPM_MAX);
    DOM.rpmBar.style.width = p + '%';

    // Color based on RPM zone
    DOM.rpmBar.classList.remove('bar--normal', 'bar--warn', 'bar--crit', 'bar--rpm');
    if (rpm >= CFG.RPM_SHIFT) {
        DOM.rpmBar.classList.add('bar--crit');
    } else if (rpm >= CFG.RPM_REDLINE) {
        DOM.rpmBar.classList.add('bar--warn');
    } else {
        DOM.rpmBar.classList.add('bar--rpm');
    }
}

// ── Critical Gauge Update ─────────────────────────────────
function updateGauge(valEl, barEl, value, min, max, decimals, classifyFn) {
    valEl.textContent = fmtVal(value, decimals);
    const p = value != null ? pct(value, min, max) : 0;
    barEl.style.width = p + '%';

    if (classifyFn) {
        const state = classifyFn(value);
        applyValueState(valEl, state);
        applyBarState(barEl, state);
    }
}

// ── G-Force Canvas ────────────────────────────────────────
let gforceCtx = null;
function initGforce() {
    const canvas = DOM.gforceCanvas;
    gforceCtx = canvas.getContext('2d');
}

function drawGforce(lat, lon) {
    const ctx = gforceCtx;
    if (!ctx) return;

    const canvas = DOM.gforceCanvas;
    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const radius = Math.min(cx, cy) - 4;

    lat = lat || 0;
    lon = lon || 0;

    // Add to trail
    gforceTrail.push({ x: lat, y: lon });
    if (gforceTrail.length > CFG.GFORCE_TRAIL_LENGTH) gforceTrail.shift();

    ctx.clearRect(0, 0, w, h);

    // Background circles
    const rings = [0.5, 1.0, 1.5];
    ctx.strokeStyle = '#1f1f26';
    ctx.lineWidth = 1;
    rings.forEach(g => {
        const r = (g / CFG.GFORCE_MAX) * radius;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
    });

    // Crosshairs
    ctx.strokeStyle = '#1a1a22';
    ctx.beginPath();
    ctx.moveTo(cx - radius, cy);
    ctx.lineTo(cx + radius, cy);
    ctx.moveTo(cx, cy - radius);
    ctx.lineTo(cx, cy + radius);
    ctx.stroke();

    // 1G reference circle label
    const r1g = (1.0 / CFG.GFORCE_MAX) * radius;
    ctx.fillStyle = '#2a2a32';
    ctx.font = '9px JetBrains Mono, monospace';
    ctx.textAlign = 'left';
    ctx.fillText('1G', cx + r1g + 3, cy - 2);

    // Trail dots
    for (let i = 0; i < gforceTrail.length; i++) {
        const pt = gforceTrail[i];
        const px = cx + (pt.x / CFG.GFORCE_MAX) * radius;
        const py = cy - (pt.y / CFG.GFORCE_MAX) * radius;
        const alpha = (i / gforceTrail.length) * 0.3;
        ctx.fillStyle = `rgba(6, 182, 212, ${alpha})`;
        ctx.beginPath();
        ctx.arc(px, py, 1.5, 0, Math.PI * 2);
        ctx.fill();
    }

    // Current position
    const dotX = cx + (lat / CFG.GFORCE_MAX) * radius;
    const dotY = cy - (lon / CFG.GFORCE_MAX) * radius;

    // Glow
    ctx.fillStyle = 'rgba(6, 182, 212, 0.15)';
    ctx.beginPath();
    ctx.arc(dotX, dotY, 8, 0, Math.PI * 2);
    ctx.fill();

    // Main dot
    ctx.fillStyle = '#06b6d4';
    ctx.beginPath();
    ctx.arc(dotX, dotY, 3.5, 0, Math.PI * 2);
    ctx.fill();

    // Update numeric values
    DOM.gforceLat.textContent = lat.toFixed(2);
    DOM.gforceLon.textContent = lon.toFixed(2);
}

// ── Gear Display ──────────────────────────────────────────
function updateGear(gear, mode) {
    let display = 'N';
    if (gear === 7 || gear === -1) display = 'R';
    else if (gear > 0 && gear <= 6) display = gear.toString();
    DOM.gearValue.textContent = display;

    if (mode != null) {
        DOM.shiftMode.textContent = mode;
    }
}

// ── Connection Status ─────────────────────────────────────
function setConnected(state) {
    connected = state;
    DOM.connDot.classList.remove('connection-status__dot--connected', 'connection-status__dot--error');
    if (state) {
        DOM.connDot.classList.add('connection-status__dot--connected');
        DOM.connText.textContent = 'CONNECTED';
    } else {
        DOM.connDot.classList.add('connection-status__dot--error');
        DOM.connText.textContent = 'DISCONNECTED';
    }
}

// ── Health Row Update ─────────────────────────────────────
function setHealth(el, status, text) {
    el.classList.remove('health--ok', 'health--warn', 'health--error');
    el.classList.add(`health--${status}`);
    const span = el.querySelector('.health-row__status span');
    if (span && text != null) span.textContent = text;
}

// ── Lap Timer ─────────────────────────────────────────────
function updateLapTimer() {
    if (lap.running) {
        lap.currentMs = performance.now() - lap.startTime;
    }

    DOM.currentLap.textContent = formatLap(lap.currentMs);
    DOM.lapTimerTop.textContent = formatLap(lap.currentMs);

    const deltaEl = DOM.sectorDelta;
    deltaEl.textContent = formatDelta(lap.sectorDelta);
    deltaEl.classList.remove('lap-times__delta--ahead', 'lap-times__delta--behind');
    deltaEl.classList.add(lap.sectorDelta <= 0 ? 'lap-times__delta--ahead' : 'lap-times__delta--behind');

    DOM.prevLap.textContent = formatLap(lap.previousMs);
    DOM.bestLap.textContent = formatLap(lap.bestMs);
    DOM.lapCount.textContent = lap.lapCount.toString();
}

// ── Update Rate Tracking ──────────────────────────────────
function trackUpdateRate() {
    const now = performance.now();
    lastUpdateTimes.push(now);
    if (lastUpdateTimes.length > CFG.UPDATE_RATE_WINDOW) {
        lastUpdateTimes.shift();
    }
    if (lastUpdateTimes.length >= 2) {
        const dt = (lastUpdateTimes[lastUpdateTimes.length - 1] - lastUpdateTimes[0]) / 1000;
        const hz = (lastUpdateTimes.length - 1) / dt;
        DOM.updateHz.textContent = hz.toFixed(1) + ' Hz';
    }
}

// ── Master Data Update ────────────────────────────────────
function processData(data) {
    trackUpdateRate();

    // Timestamp
    DOM.timestamp.textContent = new Date().toLocaleTimeString('en-GB', { hour12: false });

    const e = data.engine || {};
    const s = data.smg || {};
    const t = data.track || {};
    const h = data.health || {};

    // ── RPM
    updateRPM(e.rpm);

    // ── Critical gauges
    updateGauge(DOM.oilPressValue, DOM.oilPressBar, e.oil_pressure, 0, 6, 1,
        v => classifyLow(v, CFG.THRESH.oil_press_low, CFG.THRESH.oil_press_crit));

    updateGauge(DOM.oilTempValue, DOM.oilTempBar, e.oil_temp, 50, 150, 1,
        v => classifyTemp(v, CFG.THRESH.oil_temp_warn, CFG.THRESH.oil_temp_crit));

    updateGauge(DOM.coolantValue, DOM.coolantBar, e.coolant_temp, 50, 130, 1,
        v => classifyTemp(v, CFG.THRESH.coolant_warn, CFG.THRESH.coolant_crit));

    updateGauge(DOM.afrValue, DOM.afrBar, e.lambda_sensor_1, 0.70, 1.30, 2, null);

    updateGauge(DOM.battValue, DOM.battBar, e.battery_voltage, 10, 16, 1,
        v => classifyLow(v, CFG.THRESH.batt_low, CFG.THRESH.batt_crit));

    updateGauge(DOM.loadValue, DOM.loadBar, e.engine_load, 0, 100, 1, null);

    // ── Secondary telemetry
    DOM.iatValue.textContent = fmtVal(e.intake_temp, 1);
    DOM.iatBar.style.width = (e.intake_temp != null ? pct(e.intake_temp, 0, 80) : 0) + '%';

    DOM.mafValue.textContent = fmtVal(e.maf, 1);
    DOM.mafBar.style.width = (e.maf != null ? pct(e.maf, 0, 300) : 0) + '%';

    DOM.tpsValue.textContent = fmtVal(e.throttle_position, 1);
    DOM.tpsBar.style.width = (e.throttle_position != null ? pct(e.throttle_position, 0, 100) : 0) + '%';

    DOM.timingValue.textContent = fmtVal(e.timing_advance, 1);
    DOM.timingBar.style.width = (e.timing_advance != null ? pct(e.timing_advance, -10, 50) : 0) + '%';

    const stft = e.short_fuel_trim_1;
    DOM.fuelTrimValue.textContent = stft != null ? (stft >= 0 ? '+' : '') + stft.toFixed(1) : '--';
    DOM.fuelTrimBar.style.width = (stft != null ? pct(stft, -25, 25) : 50) + '%';

    // ── Speed & Gear
    DOM.speedValue.textContent = fmtInt(e.speed);
    updateGear(s.gear, s.shift_mode);

    // ── G-Force
    drawGforce(data.gforce_lat || 0, data.gforce_lon || 0);

    // ── Traction (simulated from ABS wheel speeds if available)
    const trac = data.traction || {};
    DOM.tractionFL.style.width = (trac.fl != null ? trac.fl : 80) + '%';
    DOM.tractionFR.style.width = (trac.fr != null ? trac.fr : 80) + '%';
    DOM.tractionRL.style.width = (trac.rl != null ? trac.rl : 80) + '%';
    DOM.tractionRR.style.width = (trac.rr != null ? trac.rr : 80) + '%';

    if (data.dsc_active != null) {
        const dsc = data.dsc_active;
        DOM.dscDot.style.background = dsc ? 'var(--color-ok)' : 'var(--color-warn)';
        DOM.dscStatus.textContent = dsc ? 'DSC ON' : 'DSC OFF';
        DOM.dscStatus.style.color = dsc ? 'var(--color-ok)' : 'var(--color-warn)';
    }

    // ── BMW-specific (MSS54 / SMG)
    DOM.vanosIn.textContent = e.vanos_intake != null ? fmtVal(e.vanos_intake, 1) + '°' : '--';
    DOM.vanosEx.textContent = e.vanos_exhaust != null ? fmtVal(e.vanos_exhaust, 1) + '°' : '--';
    DOM.knock1.textContent = e.knock_sensor_1 != null ? fmtVal(e.knock_sensor_1, 1) + '°r' : '--';
    DOM.knock2.textContent = e.knock_sensor_2 != null ? fmtVal(e.knock_sensor_2, 1) + '°r' : '--';
    DOM.injTime.textContent = e.fuel_injector_time != null ? fmtVal(e.fuel_injector_time, 2) + 'ms' : '--';
    DOM.smgHydP.textContent = s.hydraulic_pressure != null ? fmtVal(s.hydraulic_pressure, 1) + 'bar' : '--';
    DOM.clutchPos.textContent = s.clutch_position != null ? fmtVal(s.clutch_position, 0) + '%' : '--';
    DOM.gboxTemp.textContent = s.gearbox_temp != null ? fmtVal(s.gearbox_temp, 0) + '°C' : '--';

    // ── Lap times (from server or local)
    if (t.current_lap_ms != null) lap.currentMs = t.current_lap_ms;
    if (t.previous_lap_ms != null) lap.previousMs = t.previous_lap_ms;
    if (t.best_lap_ms != null) lap.bestMs = t.best_lap_ms;
    if (t.lap_count != null) lap.lapCount = t.lap_count;
    if (t.sector_delta_ms != null) lap.sectorDelta = t.sector_delta_ms;
    if (t.sector_time != null) DOM.sectorTime.textContent = formatLap(t.sector_time);
    updateLapTimer();

    // ── System health
    if (h.ecu) setHealth(DOM.healthEcu, h.ecu.status, h.ecu.text);
    if (h.smg) setHealth(DOM.healthSmg, h.smg.status, h.smg.text);
    if (h.kline) setHealth(DOM.healthKline, h.kline.status, h.kline.text);
    if (h.sensors) setHealth(DOM.healthSensors, h.sensors.status, h.sensors.text);
    if (h.dtc_count != null) {
        DOM.dtcCount.textContent = h.dtc_count.toString();
        setHealth(DOM.healthDtc, h.dtc_count > 0 ? 'warn' : 'ok', h.dtc_count.toString());
    }
}

// ── WebSocket ─────────────────────────────────────────────
function connectWS() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

    try {
        ws = new WebSocket(CFG.WS_URL);
    } catch (e) {
        console.warn('WebSocket unavailable, starting sim mode');
        startSimMode();
        return;
    }

    ws.onopen = () => {
        console.log('[WS] Connected');
        reconnectAttempts = 0;
        setConnected(true);
    };

    ws.onmessage = (evt) => {
        try {
            const data = JSON.parse(evt.data);
            processData(data);
        } catch (e) {
            console.error('[WS] Parse error', e);
        }
    };

    ws.onclose = () => {
        setConnected(false);
        if (reconnectAttempts < CFG.MAX_RECONNECT) {
            reconnectAttempts++;
            setTimeout(connectWS, CFG.RECONNECT_DELAY);
        } else {
            console.log('[WS] Max reconnect attempts, entering sim mode');
            startSimMode();
        }
    };

    ws.onerror = (e) => {
        console.error('[WS] Error', e);
    };
}

// ── Simulation Mode (demo / offline) ─────────────────────
function startSimMode() {
    if (simMode) return;
    simMode = true;
    DOM.trackMode.textContent = 'DEMO';
    DOM.trackMode.style.color = 'var(--color-amber)';
    DOM.trackMode.style.background = 'rgba(245, 158, 11, 0.1)';
    DOM.trackMode.style.borderColor = 'rgba(245, 158, 11, 0.15)';
    setConnected(false);
    DOM.connText.textContent = 'DEMO MODE';
    DOM.connDot.classList.remove('connection-status__dot--error');

    let t = 0;
    // simulated lap timer
    lap.running = true;
    lap.startTime = performance.now();
    lap.bestMs = 98432;
    lap.previousMs = 101203;
    lap.lapCount = 7;

    simInterval = setInterval(() => {
        t += 0.1;

        // Simulate realistic track data
        const rpm = 3500 + 2500 * Math.sin(t * 0.7) + 800 * Math.sin(t * 2.1) + Math.random() * 100;
        const speed = 60 + 80 * Math.sin(t * 0.3) ** 2 + Math.random() * 5;
        const throttle = 50 + 45 * Math.sin(t * 0.7) + Math.random() * 3;
        const gear = Math.max(1, Math.min(6, Math.round(speed / 30) + 1));
        const load = clamp(throttle * 0.9 + Math.random() * 5, 0, 100);

        const data = {
            engine: {
                rpm: clamp(rpm, 800, 7800),
                speed: clamp(speed, 0, 280),
                engine_load: load,
                throttle_position: clamp(throttle, 0, 100),
                coolant_temp: 88 + 4 * Math.sin(t * 0.05) + Math.random() * 0.5,
                oil_temp: 102 + 8 * Math.sin(t * 0.04) + Math.random() * 0.3,
                oil_pressure: 3.2 + 1.2 * Math.sin(t * 0.6) + Math.random() * 0.1,
                intake_temp: 32 + 5 * Math.sin(t * 0.08) + Math.random() * 0.2,
                maf: 80 + 60 * Math.sin(t * 0.7) + Math.random() * 3,
                battery_voltage: 13.8 + 0.3 * Math.sin(t * 0.3) + Math.random() * 0.05,
                timing_advance: 22 + 8 * Math.sin(t * 0.5) + Math.random() * 0.5,
                lambda_sensor_1: 0.98 + 0.05 * Math.sin(t * 1.5) + Math.random() * 0.01,
                short_fuel_trim_1: 2.1 + 3 * Math.sin(t * 0.8) + Math.random() * 0.3,
                vanos_intake: 28 + 12 * Math.sin(t * 0.4),
                vanos_exhaust: 18 + 8 * Math.sin(t * 0.35),
                knock_sensor_1: Math.max(0, 0.5 * Math.sin(t * 2) + Math.random() * 0.3),
                knock_sensor_2: Math.max(0, 0.3 * Math.sin(t * 1.8) + Math.random() * 0.2),
                fuel_injector_time: 6.5 + 3 * Math.sin(t * 0.7) + Math.random() * 0.2,
            },
            smg: {
                gear: gear,
                shift_mode: 'S5',
                hydraulic_pressure: 48 + 5 * Math.sin(t * 0.2) + Math.random() * 0.5,
                clutch_position: gear > 0 ? 0 + Math.max(0, 80 * Math.sin(t * 3) ** 8) : 100,
                gearbox_temp: 65 + 6 * Math.sin(t * 0.03) + Math.random() * 0.2,
            },
            gforce_lat: 0.6 * Math.sin(t * 0.5) + 0.2 * Math.sin(t * 1.3) + Math.random() * 0.05,
            gforce_lon: 0.4 * Math.cos(t * 0.35) + 0.15 * Math.sin(t * 0.9) + Math.random() * 0.05,
            dsc_active: true,
            traction: {
                fl: 75 + 15 * Math.sin(t * 0.8) + Math.random() * 3,
                fr: 75 + 15 * Math.sin(t * 0.8 + 0.3) + Math.random() * 3,
                rl: 70 + 20 * Math.sin(t * 0.6) + Math.random() * 4,
                rr: 70 + 20 * Math.sin(t * 0.6 + 0.4) + Math.random() * 4,
            },
            track: {
                sector_delta_ms: -320 + 200 * Math.sin(t * 0.15),
            },
            health: {
                ecu: { status: 'ok', text: 'OK' },
                smg: { status: 'ok', text: 'OK' },
                kline: { status: 'ok', text: 'OK' },
                sensors: { status: 'ok', text: 'OK' },
                dtc_count: 0,
            }
        };

        processData(data);
    }, 100);    // 10 Hz
}

function stopSimMode() {
    simMode = false;
    if (simInterval) {
        clearInterval(simInterval);
        simInterval = null;
    }
}

// ── Initialization ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    cacheDom();
    initGforce();
    drawGforce(0, 0);

    // Try WebSocket, fall back to sim
    connectWS();

    // Auto sim if no WS after 3 seconds
    setTimeout(() => {
        if (!connected && !simMode) {
            console.log('[Init] No WebSocket connection, starting demo');
            startSimMode();
        }
    }, 3000);

    // Lap timer RAF loop
    function lapTick() {
        if (lap.running) {
            lap.currentMs = performance.now() - lap.startTime;
            DOM.currentLap.textContent = formatLap(lap.currentMs);
            DOM.lapTimerTop.textContent = formatLap(lap.currentMs);
        }
        requestAnimationFrame(lapTick);
    }
    requestAnimationFrame(lapTick);
});
