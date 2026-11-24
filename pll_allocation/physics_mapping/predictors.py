"""Small prediction facade over the existing noise integrator; no formal M1/M2."""
from functools import lru_cache
import json
from pathlib import Path

from .analytic_features import analytic_features, parameter_envelope
from .model import fingerprint, parse_parameters
from .noise import MODEL_ID, optimizer_noise_estimate
from ..block_space.profiles import validate_noise


@lru_cache(maxsize=1)
def _default_profile():
    from ..verification.resources import CONFIGS
    return json.loads((CONFIGS/'verification/profiles/noise_all.json').read_text(encoding='utf-8'))


def resolve_noise_profile(profile=None):
    if profile is None:
        profile = _default_profile()
    elif isinstance(profile, (str, Path)):
        profile = json.loads(Path(profile).read_text(encoding='utf-8'))
    return validate_noise(profile)


def predict_rms_jitter(params, fixed_params=None, noise_profile=None, *, band_Hz=(1e4, 1e6), points=2049):
    """Same quadrature, PSDs, one-sided convention and conversion as noise_mapping.

    Source decomposition delegates each integral to optimizer_noise_estimate.
    No extra call to the formal frequency-scan evaluator is hidden here.
    """
    result = {'predicted_jitter_s': None, 'noise_source_fractions': {}, 'dominant_noise_source': None,
        'noise_profile_identity': None, 'prediction_validity': 'UNKNOWN', 'formal_M2_status': 'UNKNOWN'}
    try:
        import math
        if len(band_Hz) != 2 or not all(math.isfinite(x) for x in band_Hz) or not 0 < band_Hz[0] < band_Hz[1]:
            raise ValueError('positive ordered integration band required')
        if type(points) is not int or points < 17:
            raise ValueError('at least 17 integration points required')
        candidate = parameter_envelope(params, fixed_params); p = parse_parameters(candidate)
        profile = resolve_noise_profile(noise_profile)
        result['noise_profile_identity'] = {'profile_id': profile['profile_id'], 'sha256': fingerprint(profile),
            'model_id': MODEL_ID, 'band_Hz': list(band_Hz), 'points': points}
        if analytic_features(candidate)['prediction_validity']['status'] != 'CONDITIONAL_IDEAL_LINEAR':
            raise ValueError('outside stable interior ideal locked domain')
        jitter = optimizer_noise_estimate(p, profile, band_Hz, points=points)
        variances = {s['source_id']: optimizer_noise_estimate(p, profile | {'sources': [s]}, band_Hz, points=points)**2
                     for s in profile['sources']}
        fractions = {k: variances.get(k, 0.)/jitter**2 if jitter else 0.
                     for k in ('reference', 'vco', 'cp', 'resistor')}
        result.update(predicted_jitter_s=jitter, noise_source_fractions=fractions,
            dominant_noise_source=max(variances, key=variances.get) if jitter else None,
            prediction_validity='CONDITIONAL_INDEPENDENT_SMALL_SIGNAL',
            applicability='Ideal locked linear loop; independent frozen research PSDs; one-sided rad^2/Hz; no intrinsic device-noise scaling',
            integration_protocol='m1-noise-log-trapezoid-1.0')
    except (ValueError, TypeError, KeyError, ArithmeticError) as error:
        result['reason'] = str(error)
    return result
