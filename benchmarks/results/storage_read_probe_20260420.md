# Storage.read scaling probe — ADR 0001 Phase N+1B

- Date (UTC): 2026-04-20T09:25:05.927407+00:00
- Branch: proto/phase-7a-rr-action-name-index
- Commit SHA: 8f087e747318c6386ea6c67de1dc19f398ca1cb5
- Python: 3.10.20
- Platform: macOS-26.3.1-arm64-arm-64bit
- Fixture size: 100,000 entries  ·  seed: 44
- Runs per point: 50 timed + 5 warmup

## Mode segmented

- Segments written: 10

### Main sweep — varying offset, limit=100

| Offset K | median (ms) | p95 (ms) | max (ms) | stdev (ms) | entries returned | fingerprint stable |
|---:|---:|---:|---:|---:|---:|:-:|
| 0 | 2.7346 | 4.1621 | 5.0937 | 0.5806 | 100 | ✅ |
| 1,000 | 4.9992 | 6.7115 | 6.9091 | 0.6644 | 100 | ✅ |
| 10,000 | 28.4174 | 29.5484 | 29.9638 | 0.6580 | 100 | ✅ |
| 50,000 | 131.7497 | 134.9923 | 138.0096 | 1.7535 | 100 | ✅ |
| 90,000 | 234.0189 | 252.4095 | 303.5872 | 11.0278 | 100 | ✅ |
| 99,900 | 257.3502 | 271.3664 | 304.4668 | 9.5774 | 100 | ✅ |

### Slope analysis

- Baseline at offset=0 : 2.7346 ms

| Offset K | Δ vs K=0 (ms) | Δ / K (µs per offset skipped) |
|---:|---:|---:|
| 1,000 | 2.2646 | 2.2646 |
| 10,000 | 25.6828 | 2.5683 |
| 50,000 | 129.0151 | 2.5803 |
| 90,000 | 231.2842 | 2.5698 |
| 99,900 | 254.6156 | 2.5487 |

- Growth pattern : **linear-like**
- Empirical classification : `linear-like`

### Limit sensitivity sweep — fixed offset=50 000

| Limit | median (ms) | p95 (ms) | max (ms) | entries returned |
|---:|---:|---:|---:|---:|
| 10 | 130.0837 | 132.3211 | 256.5976 | 10 |
| 100 | 131.8964 | 135.1383 | 136.0807 | 100 |
| 1,000 | 135.6166 | 152.0092 | 206.2865 | 1000 |

## Mode monolithic


### Main sweep — varying offset, limit=100

| Offset K | median (ms) | p95 (ms) | max (ms) | stdev (ms) | entries returned | fingerprint stable |
|---:|---:|---:|---:|---:|---:|:-:|
| 0 | 353.8337 | 362.2442 | 463.3785 | 16.4137 | 100 | ✅ |
| 1,000 | 356.5947 | 364.8590 | 411.4389 | 8.0064 | 100 | ✅ |
| 10,000 | 360.6210 | 640.5415 | 1150.2322 | 157.5125 | 100 | ✅ |
| 50,000 | 490.1829 | 530.6453 | 622.9294 | 41.3203 | 100 | ✅ |
| 90,000 | 608.9752 | 646.5735 | 970.3897 | 72.1128 | 100 | ✅ |
| 99,900 | 529.0806 | 601.7451 | 650.9068 | 40.6227 | 100 | ✅ |

### Slope analysis

- Baseline at offset=0 : 353.8337 ms

| Offset K | Δ vs K=0 (ms) | Δ / K (µs per offset skipped) |
|---:|---:|---:|
| 1,000 | 2.7610 | 2.7610 |
| 10,000 | 6.7872 | 0.6787 |
| 50,000 | 136.3492 | 2.7270 |
| 90,000 | 255.1415 | 2.8349 |
| 99,900 | 175.2469 | 1.7542 |

- Growth pattern : **other / unclear**
- Empirical classification : `other / unclear`

### Limit sensitivity sweep — fixed offset=50 000

| Limit | median (ms) | p95 (ms) | max (ms) | entries returned |
|---:|---:|---:|---:|---:|
| 10 | 440.8885 | 452.5758 | 453.7877 | 10 |
| 100 | 442.4413 | 453.8636 | 531.7876 | 100 |
| 1,000 | 444.0574 | 453.4527 | 455.0053 | 1000 |

## Cross-mode comparison (main sweep)

| Offset K | segmented median (ms) | monolithic median (ms) | Ratio mono / seg |
|---:|---:|---:|---:|
| 0 | 2.7346 | 353.8337 | 129.39× |
| 1,000 | 4.9992 | 356.5947 | 71.33× |
| 10,000 | 28.4174 | 360.6210 | 12.69× |
| 50,000 | 131.7497 | 490.1829 | 3.72× |
| 90,000 | 234.0189 | 608.9752 | 2.60× |
| 99,900 | 257.3502 | 529.0806 | 2.06× |
