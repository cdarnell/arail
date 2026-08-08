# Retrieval A/B results

- git sha: `9362acdb5c8d43dd3557701a86cd952afcda5890`
- embedding model: `nomic-embed-text` (768d)
- LanceDB: `0.30.2`
- corpus manifest sha256: `034940c342fb98264ad99cf1e3b747ecf729db84c91a916cc15cb6fcd1851208`
- queries.yaml sha256: `546bf567ef1484bd12cbceb88b165ed7f393981d0563a1dec12b5e00b1975a96`
- exact_tokens.yaml sha256: `a659be0c54eba2d061bf314491ae17841b4925629d449d4252049f9d629dca8e`
- row counts: {'root': 37, 'ai': 381, 'video-games': 318, 'debt-finance': 82, 'qukaizen': 71}

## Pooled recall@5
- hash: 50.0%
- nomic: 90.6%
- **delta (nomic - hash): 40.6pp**
- 95% bootstrap CI on delta: [25.0, 56.2]pp (seed 20260808, 10000 resamples)
- **verdict: PASS**

## Per-world recall@5
### hash
- root: 57.1%
- ai: 28.6%
- video-games: 33.3%
- debt-finance: 66.7%
- qukaizen: 66.7%
### nomic
- root: 100.0%
- ai: 85.7%
- video-games: 83.3%
- debt-finance: 100.0%
- qukaizen: 83.3%

## Pooled MRR@10
- hash: 0.428
- nomic: 0.718

## Overlap strata
counts: {'zero': 8, 'low': 3, 'high': 21}
- zero: hash=0.0%, nomic=62.5%
- low: hash=66.7%, nomic=100.0%
- high: hash=66.7%, nomic=100.0%

## Exact-token rank-1
- hash: 1/10
- nomic: 9/10

## Throughput
- hash/root: 37 rows, 7214.9 rows/s, wall 0.01s, batch p50=0.00s p95=0.00s
- hash/ai: 381 rows, 17893.9 rows/s, wall 0.02s, batch p50=0.00s p95=0.00s
- hash/video-games: 318 rows, 9458.5 rows/s, wall 0.03s, batch p50=0.00s p95=0.00s
- hash/debt-finance: 82 rows, 13188.6 rows/s, wall 0.01s, batch p50=0.00s p95=0.00s
- hash/qukaizen: 71 rows, 11375.5 rows/s, wall 0.01s, batch p50=0.00s p95=0.00s
- nomic/root: 37 rows, 57.1 rows/s, wall 0.65s, batch p50=0.57s p95=0.57s
- nomic/ai: 381 rows, 133.6 rows/s, wall 2.85s, batch p50=0.22s p95=0.43s
- nomic/video-games: 318 rows, 75.6 rows/s, wall 4.21s, batch p50=0.43s p95=0.85s
- nomic/debt-finance: 82 rows, 104.0 rows/s, wall 0.79s, batch p50=0.25s p95=0.40s
- nomic/qukaizen: 71 rows, 98.2 rows/s, wall 0.72s, batch p50=0.25s p95=0.40s
