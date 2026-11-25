"""Responsibility-named current protocol and exact historical protocol readers."""
from copy import deepcopy

from .experiments import protocol
from ..physics_mapping.model import fingerprint


def integer_n_protocol(values, *, legacy=False):
    """Derive the existing measurements; do not change numerical thresholds."""
    doc = deepcopy(protocol())
    base = doc['protocol_id']
    baseline_sha = fingerprint(doc)
    doc.update(schema_version='behavioral-metric-protocol-1.2' if legacy else 'behavioral-metric-protocol-2.0',
        protocol_id='integer_n_metrics_1.0' if legacy else 'integer_n_metrics_2.0',
        frequency_plan={'f_ref_Hz': values['f_ref'], 'N': values['N'],
                        'output_frequency_Hz': values['N']*values['f_ref']})
    doc['judgment']['BW'] = 'compare converged M2 bandwidth interval to current request Spec bounds'
    doc['judgment']['frequency'] = 'candidate N*f_ref target; retain capture ppm and numerical convergence thresholds'
    if legacy:
        doc['base_protocol_id'] = base
        doc['supersedes'] = 'track_b_metrics_1.1 adapter: bind candidate N and N*f_ref; measurement thresholds unchanged'
    else:
        doc['baseline_protocol_sha256'] = baseline_sha
        doc['measurement_definitions_source'] = 'configs/verification/m2_protocol.json'
        doc['frozen_baseline'] = 'Declared ideal behavioral model; numerical measurement thresholds preserved'
        doc['supersedes'] = 'Earlier integer-N metric identity; measurement definitions and thresholds unchanged'
    return doc
