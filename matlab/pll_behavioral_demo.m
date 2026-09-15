function result = pll_behavioral_demo(output_path)
%PLL_BEHAVIORAL_DEMO Minimal averaged Integer-N CPPLL behavioral model.
%
% This MATLAB implementation follows the same reference-cycle phase-domain
% equations as v1/model/pll_behavioral.py. It is intended for fast behavioral
% exploration, not transistor-level signoff.
%
% Example:
%   addpath('matlab');
%   r = pll_behavioral_demo('results/matlab_pll_demo.json');

if nargin < 1
    output_path = '';
end

pll.f_ref_hz = 50e6;
pll.divider_n = 100;
pll.vdd_v = 1.8;
pll.temperature_c = 25.0;
pll.vctrl_initial_v = 0.30;
pll.vctrl_min_v = 0.10;
pll.vctrl_max_v = 1.10;
pll.cp_current_a = 100e-6;
pll.loop_filter_r_ohm = 2e3;
pll.loop_filter_c_f = 20e-9;
pll.kp = 0.05;
pll.ki = 2e-4;
pll.max_cycles = 5000;
pll.lock_relative_frequency_tolerance = 1e-5;
pll.lock_consecutive_cycles = 100;
pll.jitter_f_low_hz = 10.0;
pll.jitter_f_high_hz = 20e6;
pll.jitter_points = 240;
pll.loop_bandwidth_hz = [];

vco.f0_hz = 4.45e9;
vco.v0_v = 0.50;
vco.k1_hz_per_v = 1.60e9;
vco.k2_hz_per_v2 = 0.70e9;
vco.tempco_hz_per_c = 0.15e6;
vco.nominal_temperature_c = 25.0;
vco.vctrl_min_v = 0.10;
vco.vctrl_max_v = 1.10;
vco.nominal_power_w = 5e-3;
vco.power_vctrl_coeff = 0.12;
vco.pn_1mhz_dbc_hz = -116.0;
vco.pn_vctrl_coeff_db_per_v = 8.0;
vco.pn_temp_coeff_db_per_c = 0.018;
vco.pn_power_coeff_db_per_decade = -3.0;

target_frequency_hz = pll.f_ref_hz * pll.divider_n;
vctrl = min(max(pll.vctrl_initial_v, ...
    max(pll.vctrl_min_v, vco.vctrl_min_v)), ...
    min(pll.vctrl_max_v, vco.vctrl_max_v));
integrator = 0.0;
phase_reference_cycles = 0.0;
phase_divided_cycles = 0.0;
lock_run = 0;
lock_cycle = [];

history.cycle = zeros(pll.max_cycles, 1);
history.time_s = zeros(pll.max_cycles, 1);
history.vctrl_v = zeros(pll.max_cycles, 1);
history.fosc_hz = zeros(pll.max_cycles, 1);
history.fdiv_hz = zeros(pll.max_cycles, 1);
history.relative_frequency_error = zeros(pll.max_cycles, 1);
history.phase_error_cycles = zeros(pll.max_cycles, 1);

for cycle = 0:(pll.max_cycles - 1)
    output_frequency_hz = vco_frequency(vco, vctrl, pll.temperature_c);
    divided_frequency_hz = output_frequency_hz / pll.divider_n;
    relative_frequency_error = ...
        (target_frequency_hz - output_frequency_hz) / target_frequency_hz;

    phase_reference_cycles = phase_reference_cycles + 1.0;
    phase_divided_cycles = phase_divided_cycles + ...
        divided_frequency_hz / pll.f_ref_hz;
    phase_error_cycles = phase_reference_cycles - phase_divided_cycles;
    wrapped_phase_error_cycles = mod(phase_error_cycles + 0.5, 1.0) - 0.5;

    integrator = integrator + relative_frequency_error;
    vctrl = vctrl + pll.kp * relative_frequency_error + pll.ki * integrator;
    vctrl = min(max(vctrl, max(pll.vctrl_min_v, vco.vctrl_min_v)), ...
        min(pll.vctrl_max_v, vco.vctrl_max_v));

    if abs(relative_frequency_error) <= pll.lock_relative_frequency_tolerance
        lock_run = lock_run + 1;
        if lock_run >= pll.lock_consecutive_cycles && isempty(lock_cycle)
            lock_cycle = cycle - pll.lock_consecutive_cycles + 1;
        end
    else
        lock_run = 0;
    end

    idx = cycle + 1;
    history.cycle(idx) = cycle;
    history.time_s(idx) = (cycle + 1) / pll.f_ref_hz;
    history.vctrl_v(idx) = vctrl;
    history.fosc_hz(idx) = output_frequency_hz;
    history.fdiv_hz(idx) = divided_frequency_hz;
    history.relative_frequency_error(idx) = relative_frequency_error;
    history.phase_error_cycles(idx) = wrapped_phase_error_cycles;
end

tail_length = min(100, pll.max_cycles);
tail_idx = (pll.max_cycles - tail_length + 1):pll.max_cycles;
final_vctrl_v = history.vctrl_v(end);
final_output_frequency_hz = mean(history.fosc_hz(tail_idx));
final_relative_error = ...
    (target_frequency_hz - final_output_frequency_hz) / target_frequency_hz;
final_power_w = vco_power(vco, final_vctrl_v, pll.temperature_c);
integrated_jitter = integrated_vco_jitter(vco, pll, final_vctrl_v, ...
    final_output_frequency_hz);
bandwidth_hz = estimate_bandwidth(pll, vco, final_vctrl_v);

metrics.output_frequency_hz = final_output_frequency_hz;
metrics.integrated_jitter_s = integrated_jitter;
if isempty(lock_cycle)
    metrics.lock_time_s = [];
else
    metrics.lock_time_s = (lock_cycle + pll.lock_consecutive_cycles) / ...
        pll.f_ref_hz;
end
metrics.power_w = final_power_w;
metrics.phase_noise_100khz_dbc_hz = vco_phase_noise(vco, 100e3, ...
    final_vctrl_v, pll.temperature_c, final_power_w);
metrics.phase_noise_1mhz_dbc_hz = vco_phase_noise(vco, 1e6, ...
    final_vctrl_v, pll.temperature_c, final_power_w);
metrics.phase_noise_10mhz_dbc_hz = vco_phase_noise(vco, 10e6, ...
    final_vctrl_v, pll.temperature_c, final_power_w);
metrics.kvco_hz_per_v = vco_kvco(vco, final_vctrl_v);
metrics.loop_bandwidth_hz = bandwidth_hz;
metrics.final_relative_frequency_error = final_relative_error;
metrics.final_vctrl_v = final_vctrl_v;

context.vctrl_min_v = min(history.vctrl_v);
context.vctrl_max_v = max(history.vctrl_v);
context.fosc_min_hz = min(history.fosc_hz);
context.fosc_max_hz = max(history.fosc_hz);
context.temperature_c = pll.temperature_c;
context.vdd_v = pll.vdd_v;
context.divider_n = pll.divider_n;
context.f_ref_hz = pll.f_ref_hz;

result.model = 'averaged_integer_n_cppll_v1';
result.mode = 'reference_cycle_phase_domain';
result.target_frequency_hz = target_frequency_hz;
result.metrics = metrics;
result.context = context;
result.locked = ~isempty(lock_cycle);
result.lock_cycle = lock_cycle;
result.simulation_cycles = pll.max_cycles;
result.parameters.pll = pll;
result.parameters.vco = vco;
result.history = history;

if ~isempty(output_path)
    output_dir = fileparts(output_path);
    if ~isempty(output_dir) && ~exist(output_dir, 'dir')
        mkdir(output_dir);
    end
    fid = fopen(output_path, 'w');
    if fid < 0
        error('Could not open output path: %s', output_path);
    end
    fprintf(fid, '%s', jsonencode(result));
    fclose(fid);
end
end

function frequency_hz = vco_frequency(vco, vctrl_v, temperature_c)
x = vctrl_v - vco.v0_v;
frequency_hz = vco.f0_hz + vco.k1_hz_per_v * x + ...
    vco.k2_hz_per_v2 * x * x + ...
    vco.tempco_hz_per_c * (temperature_c - vco.nominal_temperature_c);
end

function kvco_hz_per_v = vco_kvco(vco, vctrl_v)
kvco_hz_per_v = vco.k1_hz_per_v + ...
    2.0 * vco.k2_hz_per_v2 * (vctrl_v - vco.v0_v);
end

function power_w = vco_power(vco, vctrl_v, temperature_c)
normalized_v = (vctrl_v - vco.vctrl_min_v) / ...
    (vco.vctrl_max_v - vco.vctrl_min_v);
temp_factor = 1.0 + 0.001 * ...
    (temperature_c - vco.nominal_temperature_c);
power_w = max(0.1e-3, vco.nominal_power_w * ...
    (1.0 + vco.power_vctrl_coeff * normalized_v) * temp_factor);
end

function pn_dbc_hz = vco_phase_noise(vco, offset_hz, vctrl_v, ...
    temperature_c, power_w)
if offset_hz <= 0
    error('offset_hz must be positive');
end
if offset_hz < 1e6
    slope_term = 30.0 * log10(1e6 / offset_hz);
else
    slope_term = -20.0 * log10(offset_hz / 1e6);
end
power_ratio = max(power_w / vco.nominal_power_w, 1e-6);
pn_dbc_hz = vco.pn_1mhz_dbc_hz + ...
    vco.pn_vctrl_coeff_db_per_v * (vctrl_v - vco.v0_v) + ...
    vco.pn_temp_coeff_db_per_c * ...
    (temperature_c - vco.nominal_temperature_c) + ...
    vco.pn_power_coeff_db_per_decade * log10(power_ratio) + slope_term;
end

function bandwidth_hz = estimate_bandwidth(pll, vco, vctrl_v)
if ~isempty(pll.loop_bandwidth_hz)
    bandwidth_hz = max(1.0, pll.loop_bandwidth_hz);
    return;
end
gain_term = pll.kp + sqrt(max(pll.ki, 0.0));
kvco_term = max(vco_kvco(vco, vctrl_v) / 1e9, 0.05);
bandwidth_hz = pll.f_ref_hz * gain_term * sqrt(kvco_term);
bandwidth_hz = min(max(bandwidth_hz, 1e3), 0.20 * pll.f_ref_hz);
end

function jitter_s = integrated_vco_jitter(vco, pll, vctrl_v, ...
    output_frequency_hz)
bandwidth_hz = estimate_bandwidth(pll, vco, vctrl_v);
offsets = logspace(log10(pll.jitter_f_low_hz), ...
    log10(pll.jitter_f_high_hz), pll.jitter_points);
integral_value = 0.0;
previous_offset = [];
previous_density = [];
for i = 1:numel(offsets)
    offset_hz = offsets(i);
    power_w = vco_power(vco, vctrl_v, pll.temperature_c);
    pn_dbc_hz = vco_phase_noise(vco, offset_hz, vctrl_v, ...
        pll.temperature_c, power_w);
    transfer_sq = offset_hz^2 / (offset_hz^2 + bandwidth_hz^2);
    phase_density = 2.0 * 10^(pn_dbc_hz / 10.0) * transfer_sq;
    if ~isempty(previous_offset)
        integral_value = integral_value + 0.5 * ...
            (phase_density + previous_density) * ...
            (offset_hz - previous_offset);
    end
    previous_offset = offset_hz;
    previous_density = phase_density;
end
jitter_s = sqrt(max(integral_value, 0.0)) / ...
    (2.0 * pi * output_frequency_hz);
end

