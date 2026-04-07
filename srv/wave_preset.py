import json
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger


PRESET_DIR = Path(__file__).resolve().parent.parent / "wave_presets"


def _coerce_ops(raw_wave_data) -> List[str]:
    if raw_wave_data is None:
        return []
    if isinstance(raw_wave_data, str):
        parsed = json.loads(raw_wave_data)
    else:
        parsed = raw_wave_data
    if not isinstance(parsed, list):
        raise ValueError("Wave data must be a JSON array.")
    ops = []
    for op in parsed:
        if not isinstance(op, str) or len(op) != 16:
            raise ValueError(f"Invalid wave op: {op}")
        ops.append(op.upper())
    return ops


def _ops_to_wavestrs(ops: List[str], chunk_size: int = 86) -> List[str]:
    if not ops:
        return []
    return [
        json.dumps(ops[idx:idx + chunk_size], separators=(",", ":"))
        for idx in range(0, len(ops), chunk_size)
    ]


class WavePresetLibrary:
    def __init__(self, preset_dir: Optional[Path] = None) -> None:
        self.preset_dir = Path(preset_dir) if preset_dir is not None else PRESET_DIR
        self.presets: Dict[str, Dict[str, List[str]]] = {}
        self.reload()

    def reload(self):
        self.presets = {}
        if not self.preset_dir.exists():
            logger.warning(f"Wave preset directory not found: {self.preset_dir}")
            return
        for preset_file in sorted(self.preset_dir.glob("*.json")):
            try:
                with preset_file.open("r", encoding="utf-8") as fr:
                    raw = json.load(fr)
                name = raw.get("name") or preset_file.stem
                ops = []
                if "ops" in raw:
                    ops = _coerce_ops(raw["ops"])
                elif "wavestrs" in raw:
                    for wavestr in raw["wavestrs"]:
                        ops.extend(_coerce_ops(wavestr))
                else:
                    raise ValueError("Preset must contain `ops` or `wavestrs`.")
                self.presets[name] = {
                    "ops": ops,
                    "wavestrs": _ops_to_wavestrs(ops),
                }
                logger.info(f"Loaded wave preset `{name}` with {len(ops)} ops.")
            except Exception as exc:
                logger.error(f"Failed to load wave preset {preset_file}: {exc}")

    def get(self, name: Optional[str]):
        if not name:
            return None
        preset = self.presets.get(name)
        if preset is None:
            logger.warning(f"Wave preset `{name}` not found.")
        return preset

    @staticmethod
    def scale_op(op: str, strength_scale: float) -> str:
        strength_scale = max(0.0, min(1.0, float(strength_scale)))
        freq_hex = op[:8]
        strength_bytes = [
            max(0, min(100, round(int(op[idx:idx + 2], 16) * strength_scale)))
            for idx in range(8, 16, 2)
        ]
        return freq_hex + "".join(f"{value:02X}" for value in strength_bytes)

    def build_scaled_single_op(self, name: Optional[str], index: int, strength_scale: float) -> Optional[str]:
        preset = self.get(name)
        if not preset or not preset["ops"]:
            return None
        op = preset["ops"][index % len(preset["ops"])]
        return json.dumps([self.scale_op(op, strength_scale)], separators=(",", ":"))

    def build_scaled_wavestrs(self, name: Optional[str], strength_scale: float) -> List[str]:
        preset = self.get(name)
        if not preset or not preset["ops"]:
            return []
        scaled_ops = [self.scale_op(op, strength_scale) for op in preset["ops"]]
        return _ops_to_wavestrs(scaled_ops)
