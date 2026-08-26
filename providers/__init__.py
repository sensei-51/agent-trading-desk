#!/usr/bin/env python3
"""
providers — auto-discovered plugins, one per (leg, source).

    providers/
      fundamentals/{none,derived,example}.py     public, ship in the repo
      darkpool/{none,example}.py
      conviction/{none,example}.py
      private/<leg>/*.py                         GITIGNORED — never published

DISCOVERY IS THE PRIVACY MECHANISM. Publishing is "do not copy
`providers/private/`" — a directory that is absent rather than a set of files
that have been edited. That distinction matters: a publish step that strips
vendor names from source works right up until someone writes "the paid
provider" in a docstring, or names a variable after the vendor, or leaves the
name in a committed test fixture. A directory cannot be missed.

The same mechanism is what makes the app extensible: a contributor drops one
file into `providers/<leg>/`, points the config at it, and nothing in core
changes. No registry to edit, no `if adapter == "..."` to extend.

Absence is normal. A fresh clone has no `providers/private/`, and discovery
treats that as an ordinary empty result rather than an error — that is the
public build, working as intended.
"""

import importlib.util
import os

from . import contracts
from .contracts import ProviderError

HERE = os.path.dirname(os.path.abspath(__file__))
PRIVATE_DIR = os.path.join(HERE, "private")


class Provider:
    """One discovered provider: its declaration, its entry point, its origin."""

    def __init__(self, declaration, module, path):
        self.declaration = declaration
        self.module = module
        self.path = path

    # --- identity -------------------------------------------------------
    @property
    def name(self):
        return self.declaration["name"]

    @property
    def leg(self):
        return self.declaration["leg"]

    @property
    def ingestion(self):
        return self.declaration["ingestion"]

    @property
    def approx(self):
        return self.declaration["approx"]

    @property
    def private(self):
        return self.declaration["private"]

    @property
    def max_age_days(self):
        return self.declaration.get("max_age_days")

    @property
    def supplies_set(self):
        return set(self.declaration.get("supplies") or ())

    def supplies(self, capability):
        return capability in self.supplies_set

    # --- invocation -----------------------------------------------------
    def fetch(self, ticker, ctx=None):
        """Per-ticker legs. Validates the payload so a malformed provider is
        named here rather than surfacing as an AttributeError downstream."""
        if self.leg not in contracts.PER_TICKER_LEGS:
            raise ProviderError(f"{self.name}: fetch() on a whole-book leg ({self.leg})")
        out = self.module.fetch(ticker, ctx or {})
        return contracts.validate_payload(self.leg, out, self.path)

    def load(self, ctx=None):
        """Whole-book legs (darkpool, conviction)."""
        if self.leg not in contracts.WHOLE_BOOK_LEGS:
            raise ProviderError(f"{self.name}: load() on a per-ticker leg ({self.leg})")
        out = self.module.load(ctx or {})
        return contracts.validate_payload(self.leg, out, self.path)

    def __repr__(self):
        vis = "private" if self.private else "public"
        return f"<Provider {self.leg}/{self.name} {self.ingestion} {vis}>"


def _load_module(path):
    """Import a provider file by path, under a name that cannot collide with a
    real package (two providers may both be called `none.py`)."""
    rel = os.path.relpath(path, HERE).replace(os.sep, "_")[:-3]
    spec = importlib.util.spec_from_file_location(f"_tp_provider_{rel}", path)
    if spec is None or spec.loader is None:
        raise ProviderError(f"{path}: not importable")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _scan(directory, leg, out, errors):
    if not os.path.isdir(directory):
        return
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        # `example.py` is documentation-by-code for contributors. It is a valid
        # provider so it stays honest (it must actually satisfy the contract),
        # but it is not offered for selection.
        path = os.path.join(directory, fn)
        try:
            mod = _load_module(path)
            decl = contracts.validate_declaration(mod, os.path.relpath(path, HERE))
        except ProviderError as e:
            errors.append(str(e))
            continue
        except Exception as e:                       # a provider that raises on import
            errors.append(f"{os.path.relpath(path, HERE)}: import failed — {e!r}")
            continue
        if decl["leg"] != leg:
            errors.append(f"{os.path.relpath(path, HERE)}: declares leg {decl['leg']!r} "
                          f"but lives under {leg}/")
            continue
        key = decl["name"]
        if key in out[leg]:
            errors.append(f"{os.path.relpath(path, HERE)}: duplicate provider name "
                          f"{key!r} for leg {leg!r} (already at {out[leg][key].path})")
            continue
        out[leg][key] = Provider(decl, mod, os.path.relpath(path, HERE))


_CACHE = None


def discover(refresh=False):
    """{leg: {name: Provider}}, plus a list of discovery errors.

    Errors are RETURNED rather than raised so one broken third-party provider
    cannot stop the run — but they are surfaced by `checks.py --pre`, so a
    broken provider is loud without being fatal. A provider that fails to
    import is a bug in that provider; a run that dies because of it is a bug
    in this file.
    """
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    found = {leg: {} for leg in contracts.LEGS}
    errors = []
    for leg in contracts.LEGS:
        _scan(os.path.join(HERE, leg), leg, found, errors)
        _scan(os.path.join(PRIVATE_DIR, leg), leg, found, errors)   # may not exist
    _CACHE = (found, errors)
    return _CACHE


def get(leg, name):
    """Provider or None. `None` is a legitimate answer — the caller decides
    whether an unknown name is fatal (it is, for a configured leg)."""
    found, _ = discover()
    return found.get(leg, {}).get(name)


def names(leg, include_examples=False):
    found, _ = discover()
    ns = sorted(found.get(leg, {}))
    return ns if include_examples else [n for n in ns if n != "example"]


def all_providers():
    found, _ = discover()
    return [p for leg in contracts.LEGS for p in found[leg].values()]


def private_providers():
    """Everything that must never reach a published tree. Used by
    `tools/publish.py` and asserted by `checks.py --publish`."""
    return [p for p in all_providers() if p.private]


def errors():
    _, errs = discover()
    return errs
