#!/usr/bin/env python3
"""Generate the deterministic, provenance-labelled v2 validation catalogue."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from hedge_shared.models_v2 import SUPPORTED_LOCALES, AppMetadataV2
from hedge_shared.saref import (
    SAREF_CORE_URI,
    SAREF_CORE_VERSION,
    SAREF_EXTENSION_URIS,
    SAREF_EXTENSION_VERSIONS,
    validate_app_semantics,
)

OUTPUT = Path(__file__).parents[1] / "services/mock-api/app/data/apps-v2.json"
GENERATED_AT = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)

LOCALE_DOMAIN_NAMES = {
    "en": {},
    "de": {
        "Energy": "Energie",
        "Environment": "Umwelt",
        "Building": "Gebäude",
        "Smart City": "Smart City",
        "Manufacturing": "Fertigung",
        "Agriculture": "Landwirtschaft",
        "Automotive": "Automobilität",
        "eHealth": "E-Health",
        "Wearables": "Wearables",
        "Water": "Wasser",
        "Smart Lifts": "Intelligente Aufzüge",
        "Smart Grid": "Intelligentes Stromnetz",
    },
    "fr": {
        "Energy": "énergie",
        "Environment": "environnement",
        "Building": "bâtiment",
        "Smart City": "ville intelligente",
        "Manufacturing": "industrie",
        "Agriculture": "agriculture",
        "Automotive": "automobile",
        "eHealth": "santé numérique",
        "Wearables": "objets portables",
        "Water": "eau",
        "Smart Lifts": "ascenseurs intelligents",
        "Smart Grid": "réseau électrique intelligent",
    },
    "es": {
        "Energy": "energía",
        "Environment": "medio ambiente",
        "Building": "edificios",
        "Smart City": "ciudad inteligente",
        "Manufacturing": "fabricación",
        "Agriculture": "agricultura",
        "Automotive": "automoción",
        "eHealth": "salud digital",
        "Wearables": "dispositivos portátiles",
        "Water": "agua",
        "Smart Lifts": "ascensores inteligentes",
        "Smart Grid": "red eléctrica inteligente",
    },
    "it": {
        "Energy": "energia",
        "Environment": "ambiente",
        "Building": "edifici",
        "Smart City": "città intelligente",
        "Manufacturing": "produzione",
        "Agriculture": "agricoltura",
        "Automotive": "automotive",
        "eHealth": "sanità digitale",
        "Wearables": "dispositivi indossabili",
        "Water": "acqua",
        "Smart Lifts": "ascensori intelligenti",
        "Smart Grid": "rete elettrica intelligente",
    },
    "nl": {
        "Energy": "energie",
        "Environment": "milieu",
        "Building": "gebouwen",
        "Smart City": "slimme stad",
        "Manufacturing": "productie",
        "Agriculture": "landbouw",
        "Automotive": "automotive",
        "eHealth": "digitale gezondheid",
        "Wearables": "wearables",
        "Water": "water",
        "Smart Lifts": "slimme liften",
        "Smart Grid": "slim elektriciteitsnet",
    },
    "pt": {
        "Energy": "energia",
        "Environment": "ambiente",
        "Building": "edifícios",
        "Smart City": "cidade inteligente",
        "Manufacturing": "indústria",
        "Agriculture": "agricultura",
        "Automotive": "automóvel",
        "eHealth": "saúde digital",
        "Wearables": "dispositivos vestíveis",
        "Water": "água",
        "Smart Lifts": "elevadores inteligentes",
        "Smart Grid": "rede elétrica inteligente",
    },
    "tr": {
        "Energy": "enerji",
        "Environment": "çevre",
        "Building": "bina",
        "Smart City": "akıllı şehir",
        "Manufacturing": "üretim",
        "Agriculture": "tarım",
        "Automotive": "otomotiv",
        "eHealth": "dijital sağlık",
        "Wearables": "giyilebilir cihazlar",
        "Water": "su",
        "Smart Lifts": "akıllı asansörler",
        "Smart Grid": "akıllı elektrik şebekesi",
    },
}

SUMMARY_TEMPLATES = {
    "en": "Synthetic edge application for {domain}: {capability}.",
    "de": "Synthetische Edge-Anwendung für {domain}: {capability}.",
    "fr": "Application edge synthétique pour {domain} : {capability}.",
    "es": "Aplicación edge sintética para {domain}: {capability}.",
    "it": "Applicazione edge sintetica per {domain}: {capability}.",
    "nl": "Synthetische edge-app voor {domain}: {capability}.",
    "pt": "Aplicação edge sintética para {domain}: {capability}.",
    "tr": "{domain} için sentetik uç uygulaması: {capability}.",
}

# Each vertical intentionally covers ten different operational jobs.
VERTICALS = [
    ("SAREF4ENER", "Energy", "energy", ["MQTT", "Modbus TCP"], ["IEC 61850", "EN 50631"], [
        ("FlexLoad Orchestrator", "forecast and schedule flexible electrical loads"),
        ("Solar Yield Sentinel", "monitor photovoltaic yield and inverter performance"),
        ("Battery Dispatch Planner", "optimize battery charge and discharge windows"),
        ("Heat Pump Flex Manager", "coordinate heat-pump demand with price signals"),
        ("Home Power Profile", "build appliance-level power profiles"),
        ("Demand Response Gateway", "translate demand-response events into local actions"),
        ("EV Charge Optimizer", "schedule electric-vehicle charging under site limits"),
        ("Microgrid Balance Desk", "balance local generation, storage, and consumption"),
        ("Energy Tariff Advisor", "compare tariff windows against forecast demand"),
        ("Carbon Aware Scheduler", "shift controllable loads toward lower-carbon periods"),
    ]),
    ("SAREF4ENVI", "Environment", "environment", ["MQTT", "OGC SensorThings"], ["ISO 14001", "OGC SensorThings"], [
        ("Air Quality Watch", "detect particulate and gas concentration anomalies"),
        ("Urban Noise Mapper", "aggregate calibrated sound-level observations"),
        ("Flood Early Warning", "combine rainfall and water-level signals for alerts"),
        ("Wildfire Risk Edge", "estimate local fire risk from weather and vegetation sensors"),
        ("Microclimate Observatory", "track temperature, humidity, pressure, and wind"),
        ("Emission Source Tracker", "correlate stationary-source emission measurements"),
        ("Soil Contamination Monitor", "flag changes in soil quality indicators"),
        ("Coastal Condition Desk", "monitor tide, salinity, and coastal weather conditions"),
        ("Radiation Safety Monitor", "detect threshold breaches in radiation observations"),
        ("Biodiversity Acoustic Scout", "classify privacy-filtered environmental audio events"),
    ]),
    ("SAREF4BLDG", "Building", "building", ["BACnet/IP", "KNX", "MQTT"], ["ISO 52120-1", "BACnet"], [
        ("HVAC Comfort Pilot", "optimize zones using occupancy and comfort constraints"),
        ("Indoor Air Guardian", "coordinate ventilation from air-quality observations"),
        ("Lighting Scene Optimizer", "control lighting scenes using daylight and occupancy"),
        ("Occupancy Flow Insights", "produce privacy-preserving space utilization trends"),
        ("Building Fault Detective", "detect equipment faults from BMS telemetry"),
        ("Thermal Envelope Analyst", "identify heat-loss and insulation performance patterns"),
        ("Access Energy Coordinator", "coordinate access schedules with building operations"),
        ("Room Booking Climate Link", "precondition booked rooms only when needed"),
        ("Refrigeration Plant Monitor", "track cooling plant efficiency and alarms"),
        ("Facility Peak Limiter", "keep aggregate facility demand below configured limits"),
    ]),
    ("SAREF4CITY", "Smart City", "city", ["NGSI-LD", "MQTT"], ["ETSI NGSI-LD", "ISO 37120"], [
        ("Adaptive Traffic Signals", "optimize signal timing from aggregated traffic flow"),
        ("Smart Parking Guide", "publish available spaces and occupancy trends"),
        ("Waste Route Planner", "prioritize collection routes from bin fill levels"),
        ("Streetlight Operations", "schedule and diagnose connected street lighting"),
        ("Transit Reliability Desk", "detect delay patterns in public transport telemetry"),
        ("Cycling Safety Insights", "identify high-risk cycling corridors from sensor data"),
        ("Urban Heat Lens", "map neighborhood heat exposure and cooling resources"),
        ("Public Space Footfall", "analyze privacy-preserving pedestrian counts"),
        ("Road Surface Sentinel", "detect road-condition anomalies from fleet observations"),
        ("Civic Asset Workbench", "prioritize maintenance for connected municipal assets"),
    ]),
    ("SAREF4INMA", "Manufacturing", "manufacturing", ["OPC UA", "MQTT"], ["IEC 62443", "ISA-95"], [
        ("Predictive Motor Care", "detect developing motor faults from vibration and current"),
        ("Zero Defect Inspector", "coordinate in-line quality observations and traceability"),
        ("Batch Genealogy Ledger", "trace material batches through production stages"),
        ("OEE Edge Reporter", "calculate equipment availability, performance, and quality"),
        ("Compressed Air Auditor", "detect leaks and inefficient compressor operation"),
        ("Robot Cell Sentinel", "monitor robot-cell health and safety-related events"),
        ("Tool Wear Forecaster", "estimate remaining tool life from machine telemetry"),
        ("Cold Chain Factory Link", "verify temperature control across production handoffs"),
        ("Production Energy Lens", "attribute energy use to production orders"),
        ("Warehouse Flow Optimizer", "identify congestion and replenishment bottlenecks"),
    ]),
    ("SAREF4AGRI", "Agriculture", "agriculture", ["LoRaWAN", "MQTT"], ["ISO 11783", "OGC SensorThings"], [
        ("Precision Irrigation Planner", "schedule irrigation from soil and weather conditions"),
        ("Greenhouse Climate Pilot", "coordinate ventilation, heating, and shading"),
        ("Crop Stress Sentinel", "identify crop stress from field and imagery indicators"),
        ("Livestock Welfare Watch", "monitor herd activity and environmental comfort"),
        ("Frost Risk Advisor", "issue field-specific frost-risk warnings"),
        ("Nutrient Application Planner", "support traceable variable-rate nutrient plans"),
        ("Beehive Condition Monitor", "detect unusual hive temperature and activity patterns"),
        ("Farm Water Ledger", "account for irrigation abstraction and field delivery"),
        ("Harvest Readiness Desk", "combine crop maturity and weather observations"),
        ("Food Storage Guardian", "monitor storage climate and spoilage risk"),
    ]),
    ("SAREF4AUTO", "Automotive", "automotive", ["CAN", "MQTT"], ["ISO 26262", "VSS"], [
        ("Fleet Energy Coach", "analyze vehicle energy efficiency without driver profiling"),
        ("EV Battery Health Desk", "track battery health and charging history"),
        ("Road Hazard Exchange", "share verified local road-hazard observations"),
        ("Depot Charge Coordinator", "schedule fleet charging under depot constraints"),
        ("Vehicle Service Predictor", "prioritize maintenance from diagnostic trends"),
        ("Tire Condition Sentinel", "track pressure and temperature condition warnings"),
        ("Eco Route Planner", "compare routes using energy and traffic forecasts"),
        ("Cold Chain Vehicle Watch", "verify cargo climate during transport"),
        ("Cooperative Traffic Client", "consume connected-infrastructure traffic messages"),
        ("Fleet Safety Aggregator", "produce privacy-minimized safety event trends"),
    ]),
    ("SAREF4EHAW", "eHealth", "health", ["FHIR", "MQTT"], ["HL7 FHIR", "ISO 27799"], [
        ("Remote Vital Trends", "summarize consented home vital-sign observations"),
        ("Medication Routine Aid", "provide local reminders and adherence summaries"),
        ("Fall Risk Home Monitor", "detect potential falls using privacy-preserving signals"),
        ("Rehabilitation Progress", "track consented exercise and mobility progress"),
        ("Sleep Care Summary", "summarize sleep-related observations for care review"),
        ("Chronic Care Thresholds", "apply clinician-configured thresholds to home observations"),
        ("Assisted Living Alerts", "route configured wellbeing events to authorized carers"),
        ("Respiratory Condition Desk", "track spirometry and environment correlations"),
        ("Postoperative Recovery Log", "organize patient-reported and device observations"),
        ("Care Device Inventory", "track status and maintenance of connected care devices"),
    ]),
    ("SAREF4WEAR", "Wearables", "wearables", ["Bluetooth LE", "MQTT"], ["IEEE 11073", "Bluetooth GATT"], [
        ("Worker Heat Stress Band", "estimate occupational heat-stress conditions"),
        ("Ergonomic Motion Coach", "identify repetitive movement patterns on device"),
        ("Athlete Load Monitor", "summarize training load and recovery indicators"),
        ("Lone Worker Safety Link", "send configured safety events with minimal location data"),
        ("Wearable Battery Fleet", "monitor battery and firmware status across devices"),
        ("Gesture Control Bridge", "translate approved gestures into local commands"),
        ("Personal Noise Dose", "calculate daily occupational noise exposure"),
        ("Contactless Access Band", "manage privacy-preserving wearable access credentials"),
        ("Cold Exposure Monitor", "estimate cold exposure for outdoor personnel"),
        ("Wearable Data Minimizer", "filter and aggregate wearable observations at the edge"),
    ]),
    ("SAREF4WATR", "Water", "water", ["Modbus TCP", "MQTT"], ["ISO 24510", "OGC SensorThings"], [
        ("Network Leak Locator", "detect and localize probable distribution leaks"),
        ("Water Quality Sentinel", "monitor turbidity, conductivity, pH, and temperature"),
        ("Pump Efficiency Desk", "identify inefficient pump operating points"),
        ("Reservoir Operations", "forecast storage levels and configurable release needs"),
        ("Wastewater Aeration Pilot", "optimize aeration under treatment constraints"),
        ("Smart Meter Anomaly Watch", "detect unusual consumption without profiling occupants"),
        ("Stormwater Capacity Lens", "estimate drainage capacity during rainfall events"),
        ("Industrial Water Ledger", "attribute water use to production processes"),
        ("Pressure Zone Optimizer", "manage distribution pressure and burst risk"),
        ("Reuse Quality Gate", "verify reclaimed-water quality against configured uses"),
    ]),
    ("SAREF4LIFT", "Smart Lifts", "lift", ["BACnet/IP", "MQTT"], ["EN 81-20", "ISO 8100"], [
        ("Lift Predictive Care", "detect developing lift component faults"),
        ("Ride Quality Monitor", "analyze acceleration, vibration, and leveling performance"),
        ("Lift Energy Reporter", "measure energy use across operating and standby states"),
        ("Door Cycle Sentinel", "track door timing and obstruction-related events"),
        ("Elevator Traffic Planner", "analyze aggregated demand and dispatch performance"),
        ("Emergency Link Monitor", "verify availability of emergency communication paths"),
        ("Maintenance Evidence Pack", "assemble traceable condition evidence for technicians"),
        ("Accessibility Service Watch", "monitor configured accessibility features"),
        ("Lift Fleet Dashboard", "compare health and alarms across a building portfolio"),
        ("Modernization Planner", "prioritize upgrades from condition and energy indicators"),
    ]),
    ("SAREF4GRID", "Smart Grid", "grid", ["IEC 61850", "CIM"], ["IEC 61850", "IEC 61970"], [
        ("Substation Condition Lens", "monitor substation asset condition indicators"),
        ("Voltage Quality Sentinel", "detect voltage quality excursions and trends"),
        ("Feeder Load Forecaster", "forecast feeder demand from measurements and weather"),
        ("DER Hosting Advisor", "estimate distributed-energy hosting constraints"),
        ("Outage Localization Desk", "correlate grid events for faster fault localization"),
        ("Transformer Thermal Guard", "estimate transformer thermal loading and aging"),
        ("Flexibility Offer Broker", "validate and rank local flexibility offers"),
        ("Grid Topology Validator", "detect inconsistent connectivity and switch state"),
        ("Power Flow Edge Estimate", "estimate local grid state from available measurements"),
        ("Restoration Sequence Aid", "prepare operator-reviewed service restoration options"),
    ]),
]


def localized(domain: str, capability: str) -> dict[str, str]:
    """Build visibly provisional localized summaries."""
    return {
        locale: SUMMARY_TEMPLATES[locale].format(
            domain=LOCALE_DOMAIN_NAMES.get(locale, {}).get(domain, domain),
            capability=capability,
        )
        for locale in SUPPORTED_LOCALES
    }


def make_app(
    sequence: int,
    extension: str,
    domain: str,
    keyword: str,
    protocols: list[str],
    standards: list[str],
    title: str,
    capability: str,
) -> dict:
    """Build and validate one synthetic catalogue record."""
    app_id = f"app-{sequence:03d}"
    extension_uri = SAREF_EXTENSION_URIS[extension]
    summary = localized(domain, capability)
    keywords = {
        locale: [
            LOCALE_DOMAIN_NAMES.get(locale, {}).get(domain, domain),
            keyword,
            *capability.lower().replace("-", " ").split()[:5],
        ]
        for locale in SUPPORTED_LOCALES
    }
    raw = {
        "schema_version": "2.0",
        "id": app_id,
        "slug": title.lower().replace(" ", "-"),
        "title": {locale: title for locale in SUPPORTED_LOCALES},
        "summary": summary,
        "description": (
            f"{title} is a clearly synthetic reference application for {domain.lower()} "
            f"operations. It is designed to {capability} using auditable edge processing, "
            "bounded data retention, configurable thresholds, and operator-reviewed actions. "
            "The listing is representative metadata for validation and is not a commercial product."
        ),
        "localized_keywords": keywords,
        "publisher": {
            "name": f"Synthetic {domain} Systems",
            "website": f"https://synthetic.hedge.invalid/vendors/{extension.lower()}",
            "support_url": f"https://synthetic.hedge.invalid/support/{app_id}",
            "contact": "synthetic-catalogue@example.invalid",
        },
        "lifecycle": {
            "version": f"2.{(sequence - 1) % 10}.0",
            "status": "active",
            "released_at": "2026-01-15T00:00:00Z",
            "updated_at": GENERATED_AT.isoformat(),
        },
        "app_url": f"https://synthetic.hedge.invalid/apps/{app_id}",
        "documentation_url": f"https://synthetic.hedge.invalid/docs/{app_id}",
        "icon_url": f"https://synthetic.hedge.invalid/assets/{app_id}.svg",
        "screenshot_urls": [],
        "tags": [keyword, "edge-ai", "observability", extension.lower()],
        "domains": [domain],
        "capabilities": [capability, "alerting", "trend analysis"],
        "industries": [domain, "IoT operations"],
        "supported_languages": list(SUPPORTED_LOCALES),
        "protocols": protocols,
        "standards": standards,
        "deployment": {
            "modes": ["edge", "hybrid"],
            "platforms": ["Docker", "Kubernetes", "Linux gateway"],
            "minimum_cpu_cores": 1,
            "minimum_memory_mb": 512,
            "architectures": ["amd64", "arm64"],
            "regions": ["EU"],
        },
        "inputs": [
            {
                "name": f"{keyword}_observations",
                "description": f"Timestamped {domain.lower()} observations.",
                "media_type": "application/json",
                "frequency": "configurable, 1 second to 15 minutes",
                "data_classification": "personal" if domain in {"eHealth", "Wearables"} else "internal",
            }
        ],
        "outputs": [
            {
                "name": f"{keyword}_insights",
                "description": "Derived alerts, trends, and operator-review evidence.",
                "media_type": "application/json",
                "frequency": "event-driven",
                "data_classification": "confidential" if domain in {"eHealth", "Wearables"} else "internal",
            }
        ],
        "trust": {
            "license_spdx": "Apache-2.0",
            "pricing_model": "open-source",
            "authentication": ["OIDC", "mTLS for service integration"],
            "data_residency": ["EU", "on-premises"],
            "privacy_summary": (
                "Processes data locally by default and exports only configured aggregates. "
                "Deployers remain responsible for lawful configuration and retention."
            ),
            "security_features": [
                "role-based access control",
                "encrypted transport",
                "signed audit events",
                "configurable retention",
            ],
            "certifications": [],
            "support_tier": "synthetic reference only",
            "sla_summary": "No SLA; this is a non-commercial validation fixture.",
        },
        "semantic_annotations": [
            {
                "term_uri": extension_uri,
                "label": extension,
                "ontology_uri": extension_uri,
                "ontology_version": SAREF_EXTENSION_VERSIONS[extension],
                "relation": "domain",
                "provenance": "curated",
                "review_status": "unreviewed",
            },
            {
                "term_uri": f"{SAREF_CORE_URI}Function",
                "label": "Function",
                "ontology_uri": SAREF_CORE_URI,
                "ontology_version": SAREF_CORE_VERSION,
                "relation": "function",
                "provenance": "curated",
                "review_status": "unreviewed",
            },
            {
                "term_uri": f"{SAREF_CORE_URI}Property",
                "label": "Property",
                "ontology_uri": SAREF_CORE_URI,
                "ontology_version": SAREF_CORE_VERSION,
                "relation": "property",
                "provenance": "curated",
                "review_status": "unreviewed",
            },
        ],
        "provenance": {
            "synthetic": True,
            "source": "HEDGE-ExpertAI deterministic validation catalogue",
            "source_version": "2.0.0",
            "generated_by": "scripts/generate_catalogue.py",
            "license_spdx": "Apache-2.0",
            "review_status": "unreviewed",
        },
    }
    app = AppMetadataV2.model_validate(raw)
    semantic_errors = validate_app_semantics(app)
    if semantic_errors:
        raise ValueError(f"{app_id}: {'; '.join(semantic_errors)}")
    return app.model_dump(mode="json", exclude={"checksum"})


def main() -> None:
    """Generate exactly ten records per official vertical."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the committed asset differs")
    args = parser.parse_args()
    apps = []
    sequence = 1
    for extension, domain, keyword, protocols, standards, solutions in VERTICALS:
        if len(solutions) != 10:
            raise ValueError(f"{extension} must define exactly ten apps")
        for title, capability in solutions:
            apps.append(
                make_app(
                    sequence,
                    extension,
                    domain,
                    keyword,
                    protocols,
                    standards,
                    title,
                    capability,
                )
            )
            sequence += 1
    if len(apps) != 120:
        raise ValueError(f"expected 120 apps, generated {len(apps)}")
    rendered = json.dumps(apps, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"{OUTPUT} is stale; run scripts/generate_catalogue.py")
        print(f"Validated deterministic catalogue: {len(apps)} apps")
        return
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Generated {len(apps)} validated apps at {OUTPUT}")


if __name__ == "__main__":
    main()
