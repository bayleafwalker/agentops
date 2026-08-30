#!/usr/bin/env python3
"""One resolver for *our* auditctl publisher, shared by every Python caller.

This is the Python half of ``templates/dispatch/hooks/auditctl-resolve.sh``, which
remains the reference for the policy. It exists because the policy had been written
three times and only two of them were right:

* the hook helper and ``hybrid_dispatch`` carry the ELF guard and honour
  ``AUDITCTL_BIN``;
* ``metanarrative`` had neither -- ``shutil.which("auditctl")`` with a
  ``~/.local/bin`` fallback tested only for *existence*;
* ``dispatch_release`` accepted whatever ``--auditctl-bin``/``AUDITCTL_BIN`` named on
  ``shutil.which()`` alone.

Both of those swallow failure, so a shared-scope ``AUDITCTL_BIN=/bin/true`` silenced
their telemetry with no trace at all. Silent is the part that matters: the 2026-08-29
measurement that produced the hook helper found zero claude-hook events on two days
whose cost log carried eleven sessions, and nothing anywhere said so.

Why resolution is not ``shutil.which("auditctl")``
--------------------------------------------------
``auditctl`` is also the Linux kernel audit control tool, ``/usr/bin/auditctl``, owned
by the ``audit`` package. Ours is a uv-installed Python console script in
``~/.local/bin``. A process whose PATH lacks ``~/.local/bin`` -- a hook shell inherits
neither a login shell nor direnv -- resolves the name to the kernel tool, which answers
"You must be root to run this program." and exits 0. A publish that tolerates failure
then drops the record without a trace.

The guard is written against the class -- "a different program answers to this name" --
rather than against the one colliding package: a candidate is rejected when it is
demonstrably not ours (a compiled executable; our publisher is and has always been a
script), never accepted only when it matches a shape we recognise.

Where this is deliberately *stricter* than the bash helper
-----------------------------------------------------------
``auditctl_bin()`` in the shell helper trusts ``AUDITCTL_BIN`` completely once it is
executable, and its comment names that as the escape hatch should our publisher ever be
rewritten as a compiled binary. Here an override that is an ELF is refused *and said
out loud*, because these callers publish as a side effect of doing something else and
discard the result: an override that points at the wrong program is indistinguishable
from a working one unless something writes it down. If our publisher is ever compiled,
``KNOWN_INSTALL`` below is what has to change, not a silent exception.

Failure is never fatal here. Telemetry is evidence *about* a run, not part of it, so
resolution returns ``None`` and the caller carries on -- but it leaves a line on stderr.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Mapping

#: The env var that names a publisher explicitly. Authoritative when *set*, empty
#: included: an empty value is how a caller says "there is no publisher", which cannot
#: otherwise be expressed now that emptying PATH still finds the known install location.
ENV_VAR = "AUDITCTL_BIN"

#: Where uv installs our console script. Read through the environment on every call
#: rather than captured at import, so a test that moves HOME moves this with it.
KNOWN_INSTALL_RELATIVE = ".local/bin/auditctl"

#: What the publisher is called when nothing names it explicitly.
PROGRAM = "auditctl"

_ELF_MAGIC = b"\x7fELF"


def _known_install() -> Path:
    return Path(os.path.expanduser("~")) / KNOWN_INSTALL_RELATIVE


def _say(message: str) -> None:
    """One line on stderr. The whole point of this module is that this line exists."""
    print(f"auditctl-resolve: {message}", file=sys.stderr)


def _is_compiled(path: str | os.PathLike[str]) -> bool:
    """True when the candidate is an ELF, i.e. demonstrably not our publisher.

    Unreadable is not compiled: a candidate we cannot inspect is left to the caller's
    own failure handling rather than rejected on a guess. The failure direction of a
    wrong guess stays "publish anyway", never "silently stop publishing".
    """
    try:
        with open(path, "rb") as handle:
            return handle.read(4) == _ELF_MAGIC
    except OSError:
        return False


def validate(candidate: str, *, source: str = ENV_VAR) -> str | None:
    """Check an explicitly named publisher, loudly. Returns ``candidate`` or ``None``.

    ``candidate`` is returned unchanged rather than replaced by its resolved path: what
    the caller named is what the caller meant to run, and rewriting a bare name into an
    absolute one would change the command a caller records for itself.
    """
    if not candidate:
        # Deliberate "no publisher". Quiet: this is a statement, not a mistake.
        return None
    resolved = shutil.which(candidate)
    if resolved is None:
        _say(
            f"{source}={candidate!r} is not an executable file; "
            "nothing was published from this call"
        )
        return None
    if _is_compiled(resolved):
        _say(
            f"{source}={candidate!r} resolves to {resolved}, a compiled executable. "
            "Our publisher is a script, so this is a different program answering to "
            "the name -- the kernel audit control tool does, exits 0, and publishes "
            "nothing. Refusing it; nothing was published from this call"
        )
        return None
    return candidate


def resolve(*, quiet_when_absent: bool = False) -> str | None:
    """Resolve our publisher, or return ``None`` after saying why.

    Three outcomes, deliberately not one:

    * ``AUDITCTL_BIN`` is set and usable -- honoured, exactly as the hook helper does;
    * ``AUDITCTL_BIN`` is set and is not our publisher -- refused, loudly;
    * nothing is installed -- expected on a host that never publishes, so one quiet
      line rather than a complaint.
    """
    override = os.environ.get(ENV_VAR)
    if override is not None:
        return validate(override, source=ENV_VAR)
    # PATH order first, so a test stub or a virtualenv install still wins, skipping any
    # candidate that is a compiled executable.
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / PROGRAM
        if not os.access(candidate, os.X_OK) or candidate.is_dir():
            continue
        if _is_compiled(candidate):
            continue
        return str(candidate)
    # The known install location, reached when PATH held only the colliding binary,
    # or nothing at all.
    fallback = _known_install()
    if os.access(fallback, os.X_OK) and not fallback.is_dir():
        return str(fallback)
    if not quiet_when_absent:
        _say(
            f"no {PROGRAM} publisher on PATH or at ~/{KNOWN_INSTALL_RELATIVE}; "
            "nothing was published from this call"
        )
    return None


def child_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment to hand a child process: this one, minus ``AUDITCTL_BIN``.

    Same shape as the ``AGENTOPS_ROOT`` handling in ``hybrid_dispatch``: a value the
    coordinator resolved for *itself* is popped before spawning, so a child cannot
    inherit it. A child process resolves its own publisher under this same policy, and
    one exported value in a shared scope is exactly how a whole process tree comes to
    publish nowhere at once. The publisher itself does not read ``AUDITCTL_BIN``, so
    removing it changes nothing about the call that is made -- only what anything
    spawned *underneath* it can be redirected by.
    """
    env = dict(os.environ if base is None else base)
    env.pop(ENV_VAR, None)
    return env
