# Caliper scan report

Reference: `hole spacing 40mm`. Describer: `classical`.

## Feature tree

```
base [base_plate] length=80, width=50, thickness=5
  fillet [fillet] radius=6, corners=free
  flange [flange] height=40.5, thickness=5, edge=+y
    fh1 [hole] u=-22, v=26, diameter=5
    fh2 [hole] u=22, v=26, diameter=5
  h1 [hole] x=-20, y=-8, diameter=6.5
  h2 [hole] x=20, y=-8, diameter=6.5
  slot1 [slot] x=0, y=8, length=14, width=5, angle=0
```

## Scale calibration

| View | mm per pixel | Source |
|---|---|---|
| top | 0.08945 | reference: hole spacing 40mm |
| side | 0.09034 | chained through the plate width seen in the top view |
| front | 0.09994 | chained through the plate length seen in the top view |

## Measured vs design-intent values

| Parameter | Measured (mm) | Snapped (mm) |
|---|---|---|
| base.length | 80.055 | 80 |
| base.width | 50.140 | 50 |
| base.thickness | 5.059 | 5 |
| fillet.radius | 6.134 | 6 |
| flange.height | 40.474 | 40.5 |
| flange.thickness | 5.059 | 5 |
| h1.x | -20.101 | -20 |
| h1.y | -7.944 | -8 |
| h1.diameter | 6.485 | 6.5 |
| h2.x | 19.899 | 20 |
| h2.y | -7.967 | -8 |
| h2.diameter | 6.480 | 6.5 |
| slot1.x | -0.090 | 0 |
| slot1.y | 8.063 | 8 |
| slot1.length | 13.954 | 14 |
| slot1.width | 5.009 | 5 |
| slot1.angle | 0.000 | 0 |
| fh1.u | -22.072 | -22 |
| fh1.v | 26.106 | 26 |
| fh1.diameter | 5.165 | 5 |
| fh2.u | 21.883 | 22 |
| fh2.v | 26.092 | 26 |
| fh2.diameter | 5.164 | 5 |

## Manufacturability (FDM)

Minimum wall: 1.2 mm. Overhang limit: 45 degrees from vertical.

| Wall / web | Thickness (mm) | OK |
|---|---|---|
| base thickness | 5.00 | yes |
| flange thickness | 5.00 | yes |
| fh1 to flange edge | 12.00 | yes |
| fh2 to flange edge | 12.00 | yes |
| h1 to plate edge | 13.75 | yes |
| h2 to plate edge | 13.75 | yes |
| slot1 to plate edge | 14.50 | yes |
| web h1 to slot1 | 15.36 | yes |
| web h2 to slot1 | 15.36 | yes |
| web h1 to h2 | 33.50 | yes |
| web fh1 to fh2 | 39.00 | yes |

| Print orientation | Unsupported overhang (mm2) | Share of surface | Bed contact (mm2) |
|---|---|---|---|
| +z up (as modelled) | 39.9 | 0.3% | 3854 |
| -y up | 115.2 | 0.7% | 3201 |
| +x up | 133.4 | 0.9% | 398 |
| -x up | 133.4 | 0.9% | 398 |
| +y up | 2963.0 | 19.2% | 340 |
| -z up (flipped) | 3493.4 | 22.6% | 400 |

Suggested orientation: **+z up (as modelled)**.
