"""Opt-in conditional predictions shared by construction, Runner and ranking."""
from copy import deepcopy

from .contracts import number, require
from ..physics_mapping.analytic_features import analytic_features
from ..physics_mapping.model import fingerprint, parse_parameters
from ..physics_mapping.noise import optimizer_noise_estimate
from ..physics_mapping.predictors import predict_rms_jitter, resolve_noise_profile

FLAGS = ('analytic_features_enabled', 'noise_allocation_enabled',
         'initial_state_aware_enabled', 'physics_ranking_enabled')
OPTION_DEFAULTS = {'delta_offsets_V': [.03, .10], 'safe_rail_margin_V': .02,
                   'noise_band_Hz': [1e4, 1e6], 'noise_points': 2049, 'noise_trial_points': 257}


def allocation_options(config):
    for k in FLAGS:
        require(type(config.get(k, False)) is bool, k+': boolean required')
    raw = config.get('physics_options', {})
    require(isinstance(raw, dict) and set(raw) <= set(OPTION_DEFAULTS) | {'noise_profile'}, 'unknown physics options')
    opt = deepcopy(OPTION_DEFAULTS) | deepcopy(raw)
    require(isinstance(opt['delta_offsets_V'], list) and 1 <= len(opt['delta_offsets_V']) <= 8 and
            all(abs(number(x, 'delta offset')) <= 1.2 for x in opt['delta_offsets_V']), 'bounded startup offsets required')
    require(0 <= number(opt['safe_rail_margin_V'], 'safe rail margin') < .6, 'invalid safe rail margin')
    band = opt['noise_band_Hz']
    require(isinstance(band, list) and len(band) == 2 and
            0 < number(band[0], 'band lower') < number(band[1], 'band upper'), 'invalid noise band')
    for k in ('noise_points', 'noise_trial_points'):
        require(type(opt[k]) is int and 17 <= opt[k] <= 16385, 'bounded noise integration points required')
    if not any(config.get(k, False) for k in FLAGS):
        return None
    opt.update({k: config.get(k, False) for k in FLAGS})
    opt['schema_version'] = 'pll-conditional-physics-1.0'
    opt['noise_profile'] = resolve_noise_profile(opt.get('noise_profile'))
    return opt


def validate_options(opt):
    require(isinstance(opt, dict) and opt.get('schema_version') == 'pll-conditional-physics-1.0',
            'versioned conditional physics options required')
    expected = set(OPTION_DEFAULTS) | set(FLAGS) | {'schema_version', 'noise_profile'}
    require(set(opt) == expected, 'complete conditional physics options required')
    validated = allocation_options({k: opt[k] for k in FLAGS} | {
        'physics_options': {k: opt[k] for k in set(OPTION_DEFAULTS) | {'noise_profile'}}})
    require(validated == opt, 'invalid conditional physics options')
    return deepcopy(opt)


def jitter_limit(problem):
    return next((s['max'] for s in problem['specs'] if s['enabled'] and s['metric'] == 'jitter_s' and 'max' in s), None)


class ConditionalPhysics:
    def __init__(self, problem, options):
        self.problem, self.options = problem, validate_options(options)
        self.limit = jitter_limit(problem)
        self.scale = next((s['normalization_scale'] for s in problem['specs'] if s['enabled'] and
                           s['metric'] == 'jitter_s' and 'max' in s), 1.)
        self.cache = {}; self.prediction_calls = 0

    def describe(self, candidate):
        key = fingerprint(candidate)
        if key not in self.cache:
            opt = self.options; info = {}
            if any(opt[k] for k in ('analytic_features_enabled', 'initial_state_aware_enabled', 'physics_ranking_enabled')):
                info['analytic_features'] = analytic_features(candidate)
            if opt['noise_allocation_enabled']:
                info.update(predict_rms_jitter(candidate, noise_profile=opt['noise_profile'],
                    band_Hz=opt['noise_band_Hz'], points=opt['noise_points']))
                value = info['predicted_jitter_s']
                info['jitter_margin_s'] = self.limit-value if self.limit is not None and value is not None else None
                info['conditional_noise_status'] = ('UNKNOWN' if value is None else 'NO_ENABLED_LIMIT' if self.limit is None
                    else 'CONDITIONAL_FEASIBLE' if value <= self.limit else 'CONDITIONAL_LIMIT_EXCEEDED')
            self.cache[key] = info; self.prediction_calls += 1
        return deepcopy(self.cache[key])

    def qualified(self, row):
        if not self.options['noise_allocation_enabled'] or self.limit is None:
            return True
        return self.describe(row['parameters'])['conditional_noise_status'] == 'CONDITIONAL_FEASIBLE'

    def extra_margin(self, row):
        if not self.options['noise_allocation_enabled'] or self.limit is None:
            return []
        info = self.describe(row['parameters']); value = info.get('predicted_jitter_s')
        return [(self.limit-value)/self.scale if value is not None else -1e6]

    def cheap_estimate(self, candidate):
        return optimizer_noise_estimate(parse_parameters(candidate), self.options['noise_profile'],
            self.options['noise_band_Hz'], points=self.options['noise_trial_points'])
