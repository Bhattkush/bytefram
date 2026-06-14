# Data Preparation Guide

This project starts from:

- `ML/data/final_training_lean_model_ready_with_season.csv`

That file has weather and yield features but does not include complete soil attributes (`N`, `P`, `K`, `pH`, `Organic_Carbon`), so you should merge additional soil data first.

## Recommended sources

1. ICRISAT district-level data (best India structure): [http://data.icrisat.org/dld/](http://data.icrisat.org/dld/)
2. Kaggle crop recommendation dataset (quick start): [https://www.kaggle.com/datasets/uthmordewanta/crop-recommendation-dataset](https://www.kaggle.com/datasets/uthmordewanta/crop-recommendation-dataset)
3. NASA HLS NDVI data: [https://data.nasa.gov/dataset/hls-sentinel-2-multi-spectral-instrument-vegetation-indices-daily-global-30-m-v2-0-90ed0](https://data.nasa.gov/dataset/hls-sentinel-2-multi-spectral-instrument-vegetation-indices-daily-global-30-m-v2-0-90ed0)
4. ISRO VEDAS vegetation monitoring: [https://vedas.sac.gov.in/vegetation-monitoring/](https://vedas.sac.gov.in/vegetation-monitoring/)

## Merge soil + NDVI data

```bash
python -m ML.src.merge_soil_data \
  --base-csv ML/data/final_training_lean_model_ready_with_season.csv \
  --soil-csv path/to/soil_dataset.csv \
  --ndvi-csv path/to/ndvi_dataset.csv \
  --output-csv ML/data/final_training_enriched.csv
```

`--ndvi-csv` is optional.

## Train all models

```bash
python -m ML.src.train_models \
  --base-csv ML/data/final_training_lean_model_ready_with_season.csv \
  --soil-csv path/to/soil_dataset.csv \
  --ndvi-csv path/to/ndvi_dataset.csv \
  --output-dir ML/models
```

Artifacts generated:

- `ML/models/yield_model.pkl`
- `ML/models/crop_model.pkl`
- `ML/models/disease_model.pkl`
- `ML/models/model_metadata.json`

## Reality check for NDVI + soil joins

Perfect row-level alignment is rare. This pipeline uses approximate matching:

- District-level merge when district columns exist.
- Crop-level aggregation fallback when only crop labels exist.
- Global defaults fallback when neither district nor crop mapping is available.

