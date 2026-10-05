# polars

description: Fast data wrangling — Polars for loading/filtering/joining/aggregating > 1GB or speed-critical tables.

## When to use
CSV/Parquet/JSON data processing, ETL steps, anything Pandas does slowly.

## How
```python
import polars as pl
df = pl.scan_csv("big.csv")                      # LAZY — filters push down
out = (df.filter(pl.col("revenue") > 1000)
         .group_by("product")
         .agg(pl.col("revenue").sum().alias("total"))
         .sort("total", descending=True)
         .head(10))
out.collect()                                     # materialize once, at the end
# fast io: read_parquet is ~5-10x faster than read_csv
df.to_parquet("out.parquet")
```
Key ops: filter, select, with_columns, join (how="inner"/"left"), group_by+agg, pivot, unnest.

## Gotchas
- Lazy API: everything is deferred until .collect() — don't call .collect() mid-pipeline.
- Column names are strings: pl.col("x"); no pandas .loc/.iloc (use .get(), .slice()).
- Time series: df.with_columns(pl.col("ts").str.to_datetime()).set_sorted("ts") then .group_by_dynamic.
- If a result needs pandas (for sklearn), convert: df.to_pandas() or .to_numpy().
