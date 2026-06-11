"""Fetch, cache, and query curated CLI workflow matrices."""

import importlib.metadata
import importlib.util
import json
import os
import shutil
import time
from pathlib import Path

import requests

MATRIX_REGISTRY_URL = "https://hkuds.github.io/CLI-Anything/matrix_registry.json"
MATRIX_CACHE_FILE = Path.home() / ".cli-hub" / "matrix_registry_cache.json"
CACHE_TTL = 3600  # 1 hour

AGENT_INSTALLABLE_KINDS = {"agent-skill"}


def _ensure_cache_dir():
    MATRIX_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_cached_data():
    if not MATRIX_CACHE_FILE.exists():
        return None
    try:
        cached = json.loads(MATRIX_CACHE_FILE.read_text())
        return cached["data"]
    except (json.JSONDecodeError, KeyError):
        return None


def _load_local_registry():
    """Load matrix_registry.json from a source checkout when available."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "matrix_registry.json"
        if not candidate.exists():
            continue
        try:
            return json.loads(candidate.read_text())
        except json.JSONDecodeError:
            return None
    return None


def fetch_matrix_registry(force_refresh=False):
    """Fetch the matrix registry with local file caching."""
    _ensure_cache_dir()

    if not force_refresh and MATRIX_CACHE_FILE.exists():
        try:
            cached = json.loads(MATRIX_CACHE_FILE.read_text())
            if time.time() - cached.get("_cached_at", 0) < CACHE_TTL:
                return cached["data"]
        except (json.JSONDecodeError, KeyError):
            pass

    try:
        resp = requests.get(MATRIX_REGISTRY_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        cached_data = _load_cached_data()
        if cached_data is not None:
            return cached_data
        local_data = _load_local_registry()
        if local_data is not None:
            return local_data
        raise

    MATRIX_CACHE_FILE.write_text(json.dumps({"_cached_at": time.time(), "data": data}, indent=2))
    return data


def fetch_all_matrices(force_refresh=False):
    """Return all matrix entries."""
    return fetch_matrix_registry(force_refresh).get("matrices", [])


def get_matrix(name, force_refresh=False):
    """Look up a matrix entry by name (case-insensitive)."""
    name_lower = name.lower()
    for matrix_item in fetch_all_matrices(force_refresh):
        if matrix_item["name"].lower() == name_lower:
            return matrix_item
    return None


def _string_values(value):
    """Yield lowercase strings from nested matrix registry values."""
    if isinstance(value, str):
        yield value.lower()
    elif isinstance(value, dict):
        for child in value.values():
            yield from _string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_values(child)


def search_matrices(query, force_refresh=False):
    """Search matrices by name, capabilities, providers, recipes, or gaps."""
    query_lower = query.lower()
    results = []
    for matrix_item in fetch_all_matrices(force_refresh):
        haystack_values = {
            "name": matrix_item.get("name", ""),
            "display_name": matrix_item.get("display_name", ""),
            "description": matrix_item.get("description", ""),
            "category": matrix_item.get("category", ""),
            "matrix_id": matrix_item.get("matrix_id", ""),
            "capabilities": matrix_item.get("capabilities", []),
            "recipes": matrix_item.get("recipes", []),
            "known_gaps": matrix_item.get("known_gaps", []),
            "clis": matrix_item.get("clis", []),
        }
        if any(query_lower in value for value in _string_values(haystack_values)):
            results.append(matrix_item)
    return results


def _as_list(value):
    """Normalize registry requirement fields to lists."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _package_available(name):
    try:
        if importlib.util.find_spec(name) is not None:
            return True
    except Exception:
        pass
    try:
        normalized = name.replace("-", "_")
        if normalized != name and importlib.util.find_spec(normalized) is not None:
            return True
    except Exception:
        pass
    try:
        importlib.metadata.version(name)
        return True
    except Exception:
        pass
    return False


def check_provider_requirements(provider):
    """Check whether a provider's declared requirements are available locally."""
    kind = provider.get("kind", "")
    if kind in AGENT_INSTALLABLE_KINDS:
        return {
            "name": provider.get("name", ""),
            "kind": kind,
            "available": False,
            "agent_installable": True,
            "status": "agent-installable",
            "offline": bool(provider.get("offline")),
            "cost_tier": provider.get("cost_tier", "unknown"),
            "quality_tier": provider.get("quality_tier", "unknown"),
            "requires": provider.get("requires") or {},
            "present": {"env": [], "binary": [], "package": []},
            "missing": {"env": [], "binary": [], "package": []},
            "notes": provider.get("notes", ""),
        }

    requires = provider.get("requires") or {}
    env_names = _as_list(requires.get("env"))
    binary_names = _as_list(requires.get("binary"))
    package_names = _as_list(requires.get("package"))

    present = {
        "env": [name for name in env_names if os.environ.get(name)],
        "binary": [name for name in binary_names if shutil.which(name)],
        "package": [name for name in package_names if _package_available(name)],
    }
    missing = {
        "env": [name for name in env_names if name not in present["env"]],
        "binary": [name for name in binary_names if name not in present["binary"]],
        "package": [name for name in package_names if name not in present["package"]],
    }
    available = not any(missing.values())

    return {
        "name": provider.get("name", ""),
        "kind": kind,
        "available": available,
        "agent_installable": False,
        "status": "available" if available else "missing",
        "offline": bool(provider.get("offline")),
        "cost_tier": provider.get("cost_tier", "unknown"),
        "quality_tier": provider.get("quality_tier", "unknown"),
        "requires": requires,
        "present": present,
        "missing": missing,
        "notes": provider.get("notes", ""),
    }


def preflight_matrix(matrix_item, capability_id=None, offline=False):
    """Return provider availability for a matrix, optionally filtered."""
    capability_results = []

    for capability in matrix_item.get("capabilities", []):
        if capability_id and capability.get("id") != capability_id:
            continue

        provider_results = [
            check_provider_requirements(provider)
            for provider in capability.get("providers", [])
            if not offline or provider.get("offline")
        ]
        capability_results.append({
            "id": capability.get("id", ""),
            "intent": capability.get("intent", ""),
            "provider_count": len(provider_results),
            "available_count": sum(1 for provider in provider_results if provider["available"]),
            "agent_installable_count": sum(
                1 for provider in provider_results
                if provider.get("agent_installable")
            ),
            "providers": provider_results,
        })

    summary = {
        "capabilities": len(capability_results),
        "with_available_provider": sum(1 for cap in capability_results if cap["available_count"] > 0),
        "with_agent_installable_provider": sum(
            1 for cap in capability_results
            if cap["available_count"] == 0 and cap["agent_installable_count"] > 0
        ),
        "providers": sum(cap["provider_count"] for cap in capability_results),
        "available_providers": sum(cap["available_count"] for cap in capability_results),
        "agent_installable_providers": sum(
            cap["agent_installable_count"] for cap in capability_results
        ),
    }

    return {
        "matrix": {
            "name": matrix_item.get("name", ""),
            "display_name": matrix_item.get("display_name", matrix_item.get("name", "")),
            "schema_version": matrix_item.get("schema_version", "1"),
        },
        "capability_filter": capability_id,
        "offline": offline,
        "summary": summary,
        "capabilities": capability_results,
    }
