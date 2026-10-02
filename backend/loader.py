"""Loads and validates SOP files. No rule lives here: policy is only in sops/*.yaml."""
from pathlib import Path

import yaml
from pydantic import ValidationError

from backend.models import SOP

SOP_DIR = Path(__file__).parent / "sops"


class SOPLoadError(Exception):
    pass


def load_sops(sop_dir: Path = SOP_DIR) -> dict[str, SOP]:
    files = sorted(Path(sop_dir).glob("*.yaml"))
    if not files:
        raise SOPLoadError(f"no SOP files found in {sop_dir}")
    sops: dict[str, SOP] = {}
    for path in files:
        try:
            blocks = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            if not isinstance(blocks, list):
                raise ValueError("file must be a YAML list of SOP blocks")
            for block in blocks:
                sop = SOP.model_validate(block)
                if sop.id in sops:
                    raise ValueError(f"duplicate SOP id {sop.id}")
                sops[sop.id] = sop
        except (yaml.YAMLError, ValidationError, ValueError) as e:
            raise SOPLoadError(f"Invalid SOP file {path.name}: {e}") from e
    return sops


_cache: dict = {"key": None, "sops": None}


def get_sops(sop_dir: Path = SOP_DIR) -> dict[str, SOP]:
    """Cached, but reloads when any SOP file is added, removed or edited,
    so a new rule goes live on the next message without a restart."""
    files = sorted(Path(sop_dir).glob("*.yaml"))
    key = (str(sop_dir), tuple((f.name, f.stat().st_mtime_ns) for f in files))
    if key != _cache["key"]:
        _cache["sops"] = load_sops(sop_dir)
        _cache["key"] = key
    return _cache["sops"]
