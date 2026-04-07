# Dev

## build

```cmd
pyinstaller --onefile shocking_vrchat.py --add-data "templates\tiny-qr.html;templates"
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
