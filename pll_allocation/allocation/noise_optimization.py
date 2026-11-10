"""Controlled generation of the existing SLSQP with an optional extra hard margin.

Frozen allocate.py remains exact. This is one checked substitution of its function,
not a second maintained solver. No change to objective/coordinates/domain/enumeration.
"""
import hashlib
import inspect
import importlib
allocate=importlib.import_module(__package__+'.allocate')


def generated_source():
    text=inspect.getsource(allocate.optimize)
    signature='def optimize(model, system_spec, meter, sensitivity_result=None, *, maxiter=60):'
    anchor='                margin = np.array([v - guards.get(k, 0) for k, v in normalized.items()])'
    if text.count(signature)!=1 or text.count(anchor)!=1:raise ValueError('unsupported original solver source')
    text=text.replace(signature,signature.replace('maxiter=60','maxiter=60,extra_margin=None'),1)
    text=text.replace(anchor,anchor+'''
                if extra_margin is not None:
                    extra=extra_margin(p,prediction)
                    margin=np.r_[margin,[float(v) for v in extra.values()]]
                    meter.events[-1]['extra_hard_margins']=extra
''',1)
    return text


def optimize_with_noise(model,spec,meter,sensitivity_result,*,extra_margin):
    namespace=dict(vars(allocate));text=generated_source()
    exec(compile(text,'<original_SLSQP_optional_noise_margin>','exec'),namespace)
    result,meta=namespace['optimize'](model,spec,meter,sensitivity_result,extra_margin=extra_margin)
    meta.update(extension_id='original-SLSQP-extra-hard-margin-1.0',
        frozen_solver_source_sha256=hashlib.sha256(inspect.getsource(allocate.optimize).encode()).hexdigest(),
        generated_solver_sha256=hashlib.sha256(text.encode()).hexdigest())
    return result,meta
