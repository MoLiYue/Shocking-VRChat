# Dev

## build

```cmd
pyinstaller --onefile shocking_vrchat.py ^
  --name shocking_vrchat ^
  --add-data "templates\tiny-qr.html;templates" ^
  --add-data "wave_presets\*.json;wave_presets"
```

## touch advanced mode

```yaml
dglab3:
  channel_a:
    mode_config:
      touch:
        freq_ms: 10
        wave_preset: pulse-搓搓揉揉-9058076
        wave_scale: 0.35
        n_derivative: 1
        preset_bands:
          - threshold: 0.25
            wave_preset: pulse-摸摸拍拍-9049275
            wave_scale: 0.25
          - threshold: 0.55
            wave_preset: pulse-搓搓揉揉-9058076
            wave_scale: 0.35
          - threshold: 0.8
            wave_preset: pulse-加速揉搓-9113608
            wave_scale: 0.5
```

`threshold` uses the normalized touch derivative strength in the `0~1` range.
The highest matching band wins. If no band matches, the base `wave_preset` is used.

## config hot reload

The program polls `settings-v0.2.yaml` and `settings-advanced-v0.2.yaml` and applies runtime-safe changes automatically.

Hot-reloadable fields:

- `log_level`
- `dglab3.channel_a.strength_limit`
- `dglab3.channel_b.strength_limit`
- `dglab3.channel_a.mode_config.*`
- `dglab3.channel_b.mode_config.*`
- `machine.tuya.mode_config.*`

In practice this includes:

- `trigger_range`
- `shock.duration`
- `wave_preset`
- `wave_scale`
- `wave_window_ops`
- `wave_sample_step`
- `wave_advance_samples`
- `wave_envelope_curve`
- `touch.n_derivative`
- `touch.derivative_params`
- `touch.preset_bands`

Changes that still require restart:

- `avatar_params`
- parameter `mode` mapping in `settings-v0.2.yaml`
- `osc.*`
- `ws.*`
- `web_server.*`
- `SERVER_IP`

When a non-hot-reloadable field changes, the program keeps the current runtime configuration and logs a restart warning.
