#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DG-LAB .pulse (Dungeonlab+pulse:...) -> DG websocket "pulse-A:[...]" converter (best-effort).

What you send over WS:
  {"type":"msg","clientId":"...","targetId":"...","message":"pulse-A:<wavestr>"}

Where <wavestr> is a JSON array string like:
  ["F0F0F0F000326445","..."]

This converter:
  - parses Dungeonlab+pulse exports (with or without header '=')
  - rebuilds a 0.1s time-grid from each section's point list
  - repeats the pulse unit to cover section duration
  - maps frequency sliders to bytes [10..240] (inverted linear)
  - packs 4 samples (0.4s) per operation: 4 freq bytes + 4 strength bytes => 8 bytes => hex

⚠️ IMPORTANT
DG-LAB's export format is a *high-level* description (sections + point list).
The actual app/device may use a different internal mapping for frequency/speed.
So this is a practical starting point; validate by listening/feeling/oscilloscope and adjust mapping if needed.
"""

import json
import math
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

PULSE_PREFIX = "Dungeonlab+pulse:"

def _parse_float(s: str) -> float:
    try:
        return float(s)
    except Exception:
        return float(re.sub(r"[^\d\.\-]", "", s) or 0.0)

@dataclass
class PulseHeader:
    rest_ticks: int          # best-effort: ticks of 0.1s
    speed: int               # best-effort: 1/2/4
    balance: Optional[int]   # optional
    raw_header: str

@dataclass
class PulseSection:
    meta: List[int]                      # comma-separated ints before "/"
    points: List[Tuple[float, int]]      # (value, anchor_flag) after "/"
    raw: str

def parse_dungeonlab_pulse_text(pulse_text: str) -> Tuple[Optional[PulseHeader], List[PulseSection]]:
    pulse_text = pulse_text.strip()
    if pulse_text.startswith(PULSE_PREFIX):
        body = pulse_text[len(PULSE_PREFIX):]
    else:
        body = pulse_text

    header = None
    if "=" in body:
        header_str, sections_str = body.split("=", 1)
        header_nums = [x.strip() for x in header_str.split(",") if x.strip() != ""]
        rest_ticks = int(float(header_nums[0])) if len(header_nums) > 0 else 0
        speed_raw = header_nums[1] if len(header_nums) > 1 else "1"
        try:
            speed = int(speed_raw) if str(speed_raw).isdigit() else 1
        except Exception:
            speed = 1
        balance = int(float(header_nums[2])) if len(header_nums) > 2 else None
        header = PulseHeader(rest_ticks=rest_ticks, speed=speed, balance=balance, raw_header=header_str)
    else:
        sections_str = body

    sections: List[PulseSection] = []
    for raw in sections_str.split("+section+"):
        raw = raw.strip()
        if not raw:
            continue
        if "/" in raw:
            left, right = raw.split("/", 1)
        else:
            left, right = raw, ""

        meta: List[int] = []
        for tok in left.split(","):
            tok = tok.strip()
            if tok == "":
                continue
            try:
                meta.append(int(float(tok)))
            except Exception:
                pass

        points: List[Tuple[float, int]] = []
        if right.strip():
            for p in right.split(","):
                p = p.strip()
                if not p:
                    continue
                if "-" in p:
                    v, fl = p.rsplit("-", 1)
                    val = _parse_float(v)
                    try:
                        flag = int(float(fl))
                    except Exception:
                        flag = 0
                else:
                    val = _parse_float(p)
                    flag = 0
                points.append((val, flag))

        sections.append(PulseSection(meta=meta, points=points, raw=raw))
    return header, sections

def slider_to_freq(slider: float) -> int:
    """Map slider 0..100 to freq byte 240..10 (inverted linear)."""
    slider = max(0.0, min(100.0, float(slider)))
    f = 240.0 - (slider * (240.0 - 10.0) / 100.0)
    return int(round(max(10.0, min(240.0, f))))

def fill_autopoints(values_flags: List[Tuple[float, int]]) -> List[float]:
    """
    Fill non-anchor points (flag==0) by linear interpolation between anchors (flag==1).
    If no anchors exist, return values as-is.
    """
    if not values_flags:
        return []
    vals = [v for v, _ in values_flags]
    anchors = [i for i, (_, fl) in enumerate(values_flags) if fl == 1]
    if len(anchors) == 0:
        return vals

    # Ensure edges are anchors for stable interpolation
    if 0 not in anchors:
        values_flags[0] = (values_flags[0][0], 1)
    if (len(values_flags) - 1) not in anchors:
        values_flags[-1] = (values_flags[-1][0], 1)

    vals = [v for v, _ in values_flags]
    anchors = [i for i, (_, fl) in enumerate(values_flags) if fl == 1]
    out = vals[:]
    for a, b in zip(anchors, anchors[1:]):
        va, vb = vals[a], vals[b]
        span = b - a
        if span <= 1:
            continue
        for k in range(a + 1, b):
            t = (k - a) / span
            out[k] = va + (vb - va) * t
    return out

def convert_to_ops(
    pulse_text: str,
    *,
    default_rest_ticks: int = 0,
    default_speed: int = 1,
    max_ops_per_msg: int = 86
) -> Tuple[List[str], List[str], Optional[PulseHeader], List[PulseSection]]:
    """
    Returns:
      ops: list of 8-byte hex strings (uppercase)
      wavestrs: list of JSON array strings (each <= max_ops_per_msg entries), ready for "pulse-A:<wavestr>"
      header, sections: parsed metadata for debugging
    """
    header, sections = parse_dungeonlab_pulse_text(pulse_text)

    rest_ticks = default_rest_ticks
    speed = default_speed
    if header:
        rest_ticks = header.rest_ticks
        speed = header.speed or default_speed

    freq_samples: List[int] = []
    strength_samples: List[int] = []

    for sec in sections:
        meta = sec.meta
        pts = sec.points

        # Skip empty placeholders
        if not meta and not pts:
            continue

        # Best-effort meta layout:
        # meta[0]=freq_start_slider, meta[1]=freq_end_slider, meta[2]=section_duration_ticks, meta[3]=freq_mode (1..4)
        fs = meta[0] if len(meta) > 0 else 50
        fe = meta[1] if len(meta) > 1 else fs
        dur_ticks = meta[2] if len(meta) > 2 else len(pts)
        mode = meta[3] if len(meta) > 3 else 1

        f0 = slider_to_freq(fs)
        f1 = slider_to_freq(fe)

        unit_vals = fill_autopoints(pts) if pts else [0.0]
        unit_strength = [int(round(max(0.0, min(100.0, v)))) for v in unit_vals]
        unit_len = max(1, len(unit_strength))

        dur_ticks = max(0, int(dur_ticks))
        if dur_ticks == 0:
            continue
        repeats = int(math.ceil(dur_ticks / unit_len))
        total = repeats * unit_len

        for i in range(total):
            strength_samples.append(unit_strength[i % unit_len])

        if mode == 1:
            freq_samples.extend([f0] * total)
        elif mode == 2:
            for i in range(total):
                t = i / (total - 1) if total > 1 else 0.0
                freq_samples.append(int(round(f0 + (f1 - f0) * t)))
        elif mode == 3:
            for i in range(total):
                pos = i % unit_len
                t = pos / (unit_len - 1) if unit_len > 1 else 0.0
                freq_samples.append(int(round(f0 + (f1 - f0) * t)))
        elif mode == 4:
            num_units = repeats
            for u in range(num_units):
                t = u / (num_units - 1) if num_units > 1 else 0.0
                fu = int(round(f0 + (f1 - f0) * t))
                freq_samples.extend([fu] * unit_len)
        else:
            freq_samples.extend([f0] * total)

    if rest_ticks and rest_ticks > 0:
        freq_samples.extend([10] * rest_ticks)
        strength_samples.extend([0] * rest_ticks)

    speed = max(1, int(speed))
    if speed > 1:
        freq_samples = freq_samples[::speed]
        strength_samples = strength_samples[::speed]

    n = min(len(freq_samples), len(strength_samples))
    freq_samples = freq_samples[:n]
    strength_samples = strength_samples[:n]

    pad = (-n) % 4
    if pad:
        freq_samples.extend([10] * pad)
        strength_samples.extend([0] * pad)
        n += pad

    ops: List[str] = []
    for i in range(0, n, 4):
        fb = bytes([int(max(10, min(240, x))) for x in freq_samples[i:i+4]])
        sb = bytes([int(max(0, min(100, x))) for x in strength_samples[i:i+4]])
        ops.append((fb + sb).hex().upper())

    wavestrs: List[str] = []
    for i in range(0, len(ops), max_ops_per_msg):
        wavestrs.append(json.dumps(ops[i:i+max_ops_per_msg], ensure_ascii=False))

    return ops, wavestrs, header, sections

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Convert Dungeonlab .pulse export to DG websocket pulse-A wavestr JSON.")
    ap.add_argument("pulse_file", help="Path to .pulse file (text starting with Dungeonlab+pulse:...)")
    ap.add_argument("--out", default="", help="Output file path for wavestr JSON. Default: <pulse_file>.wavestr.json")
    ap.add_argument("--max-ops", type=int, default=86, help="Max ops per websocket message (default 86).")
    args = ap.parse_args()

    with open(args.pulse_file, "r", encoding="utf-8", errors="replace") as f:
        txt = f.read().strip()

    ops, wavestrs, header, sections = convert_to_ops(txt, max_ops_per_msg=args.max_ops)

    out_path = args.out or (args.pulse_file + ".wavestr.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"wavestrs": wavestrs, "num_ops": len(ops), "header": (header.__dict__ if header else None)}, f, ensure_ascii=False, indent=2)

    print(f"Parsed sections: {len(sections)}")
    print(f"Total ops: {len(ops)}")
    print(f"WS messages needed: {len(wavestrs)}")
    print(f"Wrote: {out_path}")
    print("Example message payload (first chunk):")
    print(f"pulse-A:{wavestrs[0][:180]}{' ...' if len(wavestrs[0])>180 else ''}")

if __name__ == "__main__":
    main()
