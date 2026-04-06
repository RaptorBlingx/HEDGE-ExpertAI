# SAREF Ontology Mapping

How HEDGE-ExpertAI leverages the SAREF (Smart Applications REFerence) ontology for improved search relevance and classification.

---

## Overview

[SAREF](https://saref.etsi.org/) is a reference ontology for IoT published by ETSI. HEDGE-ExpertAI uses SAREF class inference as a ranking signal in the hybrid search engine, boosting results that belong to the same ontology class as the user's query.

The system supports **8 SAREF-aligned categories** derived from SAREF core and its extensions:

| SAREF Class | Extension | Domain |
|---|---|---|
| **Energy** | SAREF4ENER | Energy management, power, renewables |
| **Building** | SAREF4BLDG | Smart buildings, HVAC, occupancy |
| **Environment** | SAREF4ENVI | Environmental monitoring, weather, pollution |
| **Water** | SAREF4WATR | Water management, irrigation, leak detection |
| **Agriculture** | SAREF4AGRI | Precision farming, livestock, greenhouses |
| **City** | SAREF4CITY | Smart city, traffic, waste, public transport |
| **Health** | — | Health monitoring, wearables, eldercare |
| **Manufacturing** | — | Industry 4.0, predictive maintenance, robotics |

---

## How It Works

### 1. Keyword-to-Class Mapping

The `hedge_shared/saref.py` module maintains a comprehensive keyword-to-class dictionary. Each SAREF class is associated with domain-specific keywords:

```python
SAREF_KEYWORDS = {
    "Energy": [
        "energy", "power", "electricity", "solar", "wind", "battery",
        "consumption", "generation", "grid", "meter", "photovoltaic",
        "renewable", "efficiency", "watt", "kwh", "voltage", "current",
        "inverter", "charging", "ev", "heat", "thermal",
        "thermostat", "demand", "load",
    ],
    "Building": [
        "building", "room", "floor", "door", "window", "elevator",
        "lighting", "light", "occupancy", "ventilation", "air",
        "conditioning", "smart home", "home automation", "bms",
        "facility", "space", "zone", "ceiling", "wall",
        "hvac", "heating", "cooling",
    ],
    # ... (8 classes, 150+ keywords total)
}
```

### 2. Class Inference

The function `infer_saref_class()` determines the best-matching SAREF class from text:

1. Tokenize the input (accepts both `str` and `list[str]`)
2. Match tokens against the keyword dictionary
3. Count matches per SAREF class
4. Return the class with the most matches (or `None`)

```python
from hedge_shared.saref import infer_saref_class

infer_saref_class("energy monitoring solar")       # → "Energy"
infer_saref_class(["hvac", "building"])             # → "Building"
infer_saref_class("random unrelated words")         # → None
```

### 3. Search Boost

During hybrid search in Discovery-Ranking, the SAREF class provides a scoring boost:

```
final_score = 0.6 × vector_score + 0.3 × keyword_score + 0.1 × saref_boost
```

Where `saref_boost = 1.0` if the app's `saref_type` matches the query's inferred SAREF class, otherwise `0.0`.

This means a SAREF match adds **+0.1** to the final score, which helps disambiguate between otherwise similar results.

---

## Complete Keyword Reference

### Energy (24 keywords)

`energy`, `power`, `electricity`, `solar`, `wind`, `battery`, `consumption`, `generation`, `grid`, `meter`, `photovoltaic`, `renewable`, `efficiency`, `watt`, `kwh`, `voltage`, `current`, `inverter`, `charging`, `ev`, `heat`, `thermal`, `thermostat`, `demand`, `load`

### Building (23 keywords)

`building`, `room`, `floor`, `door`, `window`, `elevator`, `lighting`, `light`, `occupancy`, `ventilation`, `air`, `conditioning`, `smart home`, `home automation`, `bms`, `facility`, `space`, `zone`, `ceiling`, `wall`, `hvac`, `heating`, `cooling`

### Environment (20 keywords)

`environment`, `weather`, `temperature`, `humidity`, `co2`, `pollution`, `air quality`, `noise`, `radiation`, `pressure`, `climate`, `forecast`, `wind speed`, `rainfall`, `uv`, `particulate`, `pm2.5`, `pm10`, `ozone`, `emission`

### Water (14 keywords)

`water`, `irrigation`, `flood`, `moisture`, `leak`, `wastewater`, `reservoir`, `pump`, `flow`, `pipe`, `hydro`, `rain`, `drainage`, `sewage`

### Agriculture (13 keywords)

`agriculture`, `farm`, `crop`, `soil`, `livestock`, `greenhouse`, `precision farming`, `fertilizer`, `harvest`, `plant`, `garden`, `irrigation`, `pest`

### City (14 keywords)

`city`, `traffic`, `parking`, `street`, `public transport`, `waste`, `bin`, `recycling`, `urban`, `municipal`, `infrastructure`, `road`, `pedestrian`, `bike`

### Health (12 keywords)

`health`, `medical`, `patient`, `hospital`, `wearable`, `fitness`, `heart rate`, `blood pressure`, `glucose`, `wellness`, `elderly`, `care`

### Manufacturing (12 keywords)

`manufacturing`, `factory`, `production`, `machine`, `industrial`, `assembly`, `quality`, `predictive maintenance`, `vibration`, `motor`, `conveyor`, `robot`

---

## App Metadata Integration

Each app in the catalogue has a `saref_type` field that indicates its SAREF class. This is set either:

- **Explicitly** — by the app publisher in the metadata
- **Inferred** — from tags and description using `infer_saref_class()`

Example app metadata with SAREF annotation:

```json
{
  "id": "app-001",
  "title": "SmartEnergy Monitor",
  "description": "Real-time energy consumption monitoring for residential buildings",
  "tags": ["energy", "monitoring", "residential", "anomaly-detection"],
  "saref_type": "Energy",
  "input_datasets": ["smart_meter_readings", "utility_billing_data"],
  "output_datasets": ["energy_consumption_report", "anomaly_alerts"]
}
```

---

## Testing

The SAREF module is thoroughly tested in `tests/unit/test_saref.py`:

```bash
cd shared && python -m pytest ../tests/unit/test_saref.py -v
```

Test coverage includes:
- String input inference for all 8 classes
- List input inference
- Case insensitivity
- Empty input handling
- No-match scenarios
- Query-based class inference
