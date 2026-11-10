"""Observe unchanged formal CLI functions in memory; never alter source or values."""
import functools
import importlib
import json
from pathlib import Path
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
events = []


def timed(module, name, label):
    original = getattr(module, name)
    @functools.wraps(original)
    def observe(*args, **kwargs):
        event = {'component': label, 'status': 'STARTED'}
        if label == 'response_sweep':
            event['folder'] = str(args[0])
        events.append(event)
        start = time.perf_counter()
        try:
            result = original(*args, **kwargs)
            event['status'] = 'RETURNED'
            return result
        except BaseException as error:
            event.update(status='ERROR', error_type=type(error).__name__)
            raise
        finally:
            event['wall_s'] = time.perf_counter() - start
    setattr(module, name, observe)


if __name__ == '__main__':
    destination = Path(sys.argv[1])
    actual_args = sys.argv[2:]
    verify = importlib.import_module('pll_allocation.verification.verify')
    model = importlib.import_module('pll_allocation.physics_mapping.model')
    for name in ('capture_pair', 'response_sweep', 'comparison_after_measurement', 'assemble_result'):
        timed(verify, name, name)
    timed(model, 'evaluate', 'full_M1_evaluate')
    # The exact formal module route is executed with the same CLI arguments.
    sys.argv = ['pll_allocation', *actual_args]
    started = time.perf_counter()
    exit_code = 0
    try:
        runpy.run_module('pll_allocation', run_name='__main__')
    except SystemExit as error:
        exit_code = error.code
        raise
    finally:
        document = {'formal_module': 'python -B -m pll_allocation', 'sys_argv': sys.argv,
            'exit_code': exit_code, 'observed_module_wall_s': time.perf_counter()-started,
            'events': events, 'method': 'in-memory timing wrappers invoke unchanged functions exactly once; inputs and return values unchanged; source never edited',
            'overlap': 'full_M1_evaluate is nested inside comparison_after_measurement; do not add nested times twice'}
        with destination.open('x', encoding='utf-8') as stream:
            json.dump(document, stream, indent=2, allow_nan=False)

