# sklearn

description: Classical ML — scikit-learn pipelines, LightGBM/XGBoost for tabular, validation, SHAP explainability.

## When to use
Tabular prediction/classification, baseline models, feature engineering, model comparison.

## How
1. Tabular data: use Polars (fast) to load/shape, then numpy arrays for training.
   ```python
   import polars as pl
   df = pl.read_csv("data.csv")
   X = df.drop("target").to_numpy(); y = df["target"].to_numpy()
   ```
2. Baseline ladder (always start here):
   - linear/logistic regression
   - LightGBM (best tabular SOTA per second): LGBMClassifier(n_estimators=500, learning_rate=0.05, num_leaves=31)
   - XGBoost / CatBoost if LGBM underperforms
3. Validation: train_test_split(stratify=y); cross_val_score for small data; early_stopping_rounds=50 with a valid set for GBMs.
4. Explainability: shap.TreeExplainer(model) on the final GBM.
5. Imbalanced: imbalanced-learn (SMOTE or class_weight), evaluate with PR-AUC not accuracy.
6. Log to MLflow for provenance.

## Gotchas
- Never fit preprocessors on the test set — wrap in a Pipeline.
- LightGBM: force verbose=-1 in sandbox (avoids stderr noise in results).
- For > 1 GB tables, Polars > Pandas (memory + speed); Dask for > RAM.
- Report: metric, dataset size, feature count, seed, wall time.
