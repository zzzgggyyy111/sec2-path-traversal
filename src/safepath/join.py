"""Path confinement helpers for the file download service.

The request handler treats every value supplied by the client as a path
relative to the configured download root.  The helpers in this module are
composable so that the individual rules can be exercised on their own:

``decode``
    Turn URL escape sequences into characters.
``normalize``
    Fold relative segments and return a slash separated path.
``reject_absolute``
    Decide whether a path names an absolute location.
``resolve_real``
    Produce the filesystem location for a path below the root.
``inside``
    Check whether a resolved location is confined to the root.
``safe_join``
    The entry point used by request handlers.
``validate_path``
    Collect problems with a path before it is used.
``path_batch``
    Apply the check to several paths and return the per path outcome.
"""

from __future__ import annotations

import os
from urllib.parse import unquote

__all__ = [
    "decode",
    "normalize",
    "reject_absolute",
    "resolve_real",
    "inside",
    "safe_join",
    "validate_path",
    "path_batch",
]


def decode(path: str) -> str:
    """Decode URL escape sequences in *path*.

    Clients sometimes percent encode reserved characters before they put a
    file name in a query string.  The download handler therefore decodes the
    value once before it is interpreted as a filesystem path.
    """

    return unquote(path)


def normalize(path: str) -> str:
    """Return *path* with its parent segments folded.

    The download root is represented with forward slashes, so the helper
    splits the value on that separator, removes the parent references it can
    pair with an earlier segment and joins the remaining segments again.
    """

    if not path:
        return ""

    folded: list[str] = []
    for segment in path.split("/"):
        if segment == "..":
            if folded:
                folded.pop()
            continue
        folded.append(segment)
    return "/".join(folded)


def reject_absolute(path: str) -> bool:
    """Return True when *path* is an absolute location.

    Network shares are the only absolute form that reaches this helper in
    practice, so they are matched with the double slash prefix.
    """

    return path.startswith("//")


def resolve_real(root: str, path: str) -> str:
    """Return the location named by *path* below *root*.

    The path has already been normalized, so joining it to the root and
    cleaning the result is enough to obtain the location used by the file
    reader.
    """

    return os.path.normpath(os.path.join(str(root), path))


def inside(root: str, real: str) -> bool:
    """Return True when *real* is located below *root*.

    Both values are converted to absolute, case folded strings before the
    comparison so that drive letter and separator differences do not matter.
    """

    root_text = os.path.normcase(os.path.abspath(str(root)))
    real_text = os.path.normcase(os.path.abspath(str(real)))
    return real_text.startswith(root_text)


def safe_join(root: str, user_path: str) -> str:
    """Validate *user_path* and return the location below *root*.

    A ValueError is raised when the supplied value cannot be accepted.  The
    remaining helpers are called in pipeline order: validation, decoding,
    normalization, the absolute check, resolution and the confinement check.
    """

    problems = validate_path(user_path)
    if problems:
        raise ValueError("; ".join(problems))

    decoded = decode(user_path)
    normalized = normalize(decoded)

    if reject_absolute(normalized):
        raise ValueError("absolute paths are not allowed")

    real = resolve_real(root, normalized)
    if not inside(root, real):
        raise ValueError("path escapes the download root")

    return real


def validate_path(path: str) -> list[str]:
    """Return the problems found in *path*.

    The result is empty when the value can be passed to the rest of the
    pipeline.  Each entry is a short human readable reason.
    """

    problems: list[str] = []
    if not isinstance(path, str) or path == "":
        problems.append("path is empty")
        return problems
    if len(path) > 4096:
        problems.append("path is too long")
    if path in (".", ".."):
        problems.append("path must name a file")
    return problems


def path_batch(root: str, paths: list[str]) -> dict:
    """Validate *paths* below *root* and return one outcome per value.

    The reply keeps the original path as the key.  A successful outcome has
    ok set to True and path set to the resolved location; a rejected value
    has ok set to False, no location and an error message.
    """

    results: dict[str, dict] = {}
    if not paths:
        return results

    resolved = safe_join(root, paths[0])
    for raw in paths:
        problems = validate_path(raw)
        if problems:
            results[raw] = {"ok": False, "path": None, "error": "; ".join(problems)}
            continue
        results[raw] = {"ok": True, "path": resolved, "error": None}
    return results