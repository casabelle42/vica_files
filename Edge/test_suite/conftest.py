"""
Test-only setup for the Edge package's test suite.

Edge/*.py modules use bare imports (``from model_init import ...``) that
assume the Edge/ directory itself is on sys.path — this mirrors how the
edge device runs them directly (``python client.py``). We replicate that
here instead of touching the production modules.

model_init.py unconditionally imports torch and transformers at module
scope for real VLM inference. Those are multi-gigabyte GPU-oriented
packages that have no place in a laptop-friendly pytest run, and nothing
in this test suite exercises real model weights. We install minimal
stand-ins in sys.modules so the module imports cleanly; any test that
actually needs model.load()/infer() behavior monkeypatches those methods
directly instead of relying on the stub doing real work.
"""

import sys
import types
from pathlib import Path

EDGE_DIR = Path(__file__).resolve().parents[1]
if str(EDGE_DIR) not in sys.path:
    sys.path.insert(0, str(EDGE_DIR))


def _install_stub_module(name: str, **attrs) -> None:
    if name in sys.modules:
        return
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


class _StubNoGrad:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __call__(self, fn):
        return fn


class _StubAutoProcessor:
    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        raise RuntimeError(
            "transformers is stubbed out in tests; real model loading is a lab-only path"
        )


class _StubAutoModel:
    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        raise RuntimeError(
            "transformers is stubbed out in tests; real model loading is a lab-only path"
        )


_install_stub_module("torch", no_grad=_StubNoGrad)
_install_stub_module(
    "transformers",
    AutoProcessor=_StubAutoProcessor,
    AutoModelForImageTextToText=_StubAutoModel,
    AutoModelForVision2Seq=_StubAutoModel,
)
