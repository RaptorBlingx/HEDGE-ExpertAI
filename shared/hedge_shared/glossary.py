"""General domain background for explanations; never evidence about an App.

Definitions describe what a concept usually means in the HEDGE-IoT domain
(energy flexibility, grids, IoT and data sharing). They are written for people
without that background. They are agent-authored and pending domain-expert
review (`REVIEW`). Explanations must present them as general background, and
the recommendation boundary never reads them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

REVIEW = "agent_authored_pending_domain_review"


@dataclass(frozen=True)
class Category:
    label: str
    context: str


CATEGORIES = {
    "flexibility": Category(
        "energy flexibility",
        "Electricity use and production have to stay in balance at every moment, and local grids "
        "can only "
        "carry so much power. Changing when electricity is used helps keep that balance."),
    "markets": Category(
        "energy markets",
        "Electricity, and services that keep the grid stable, are bought and sold on markets with "
        "strict "
        "rules about who may take part and how offers are submitted."),
    "grid": Category(
        "electricity grids",
        "The electricity grid carries power from producers to consumers through networks that are "
        "run by "
        "system operators."),
    "data": Category(
        "shared data definitions",
        "When organisations exchange data, each tends to name and structure the same information "
        "differently, so their systems can't understand each other automatically."),
    "messaging": Category(
        "data exchange between systems",
        "Software systems exchange data as messages. Each side has to agree on the format, or the "
        "receiver "
        "can't use what it gets."),
    "iot": Category(
        "connected devices",
        "Sensors, meters and other connected devices send measurements over networks so software "
        "can "
        "monitor equipment and buildings."),
    "maintenance": Category(
        "equipment maintenance",
        "Machines wear out. Their measurements can reveal problems early, before they cause a "
        "breakdown."),
    "forecasting": Category(
        "forecasting",
        "Forecasts estimate future values, such as prices or demand, from past data so people can "
        "plan ahead."),
    "access": Category(
        "access and data protection",
        "Shared platforms have to control who may see which data and protect sensitive "
        "information."),
    "software": Category(
        "software delivery",
        "Software can be installed on your own servers or used as a service that the provider runs "
        "for you."),
}


@dataclass(frozen=True)
class Term:
    id: str
    term: str
    aliases: tuple[str, ...]
    category: str
    plain: str
    why: str = ""
    example: str = ""
    analogy: str = ""
    related: tuple[str, ...] = ()
    acronym: bool = False
    patterns: tuple[re.Pattern, ...] = field(default=(), compare=False, repr=False)


def _t(id, term, aliases, category, plain, why="", example="", analogy="", related=(),
       acronym=False):
    return Term(id, term, tuple(aliases), category, plain, why, example, analogy, tuple(related),
                acronym)


TERMS: tuple[Term, ...] = (
    _t("flexibility",
        "flexibility",
        ["flexibility", "energy flexibility", "demand flexibility", "flexibility services",
         "flexibility potential", "flexibility needs"],
        "flexibility",
        "the ability to change when or how much electricity is used or produced, for example "
        "running a dishwasher later or pausing a heat pump for an hour",
        why="flexible use helps the grid avoid overloads and make better use of solar and wind"
            " power, and whoever provides it can be paid for it",
        example="a school cools its building a little extra in the morning so it can switch "
                "the air conditioning off for an hour during the afternoon peak",
        analogy="it is like moving a meeting to a quieter time slot so the room isn't "
                "overbooked",
        related=["flexibility-bid", "aggregator"]),
    _t("flexibility-bid",
        "flexibility bid",
        ["flexibility bid", "bid", "market bid", "common market bid", "flexibility offer",
         "sub-bid"],
        "markets",
        "an offer to change electricity use or production by a certain amount, at a certain "
        "time, for a certain price",
        why="bids are how flexibility is traded: the buyer, often a grid operator, chooses the"
            " bids it needs",
        example="“we can reduce our consumption by 200 kW between 17:00 and 18:00 tomorrow for"
                " €40”",
        analogy="it works like a quote from a contractor: what they will do, when, and for how"
                " much",
        related=["flexibility", "market-operator"]),
    _t("aggregator",
        "aggregator",
        ["aggregator", "aggregator services", "aggregation"],
        "markets",
        "a company that pools the flexibility of many smaller energy users, such as homes, "
        "shops and factories, and offers it on energy markets as one larger amount",
        why="single households are far too small to trade on energy markets on their own, so "
            "aggregators make their flexibility usable",
        example="an aggregator that controls the hot-water heaters of 2,000 homes offers the "
                "grid operator a combined reduction when demand peaks",
        analogy="it is like a cooperative that collects milk from many small farms and sells "
                "it to a dairy as one delivery",
        related=["flexibility", "flexibility-bid"]),
    _t("market-operator",
        "market operator",
        ["market operator", "energy market operator"],
        "markets",
        "the organisation that runs an energy market: it receives bids, matches buyers and "
        "sellers and publishes the results",
        analogy="it is like an auction house: it collects the offers, decides which ones are "
                "accepted and announces the results",
        related=["energy-market"]),
    _t("energy-market",
        "energy market",
        ["energy market", "electricity market", "flexibility market", "market participation",
         "market platform"],
        "markets",
        "a marketplace where electricity, or services such as flexibility, are bought and "
        "sold, often for each hour or quarter-hour of the next day",
        example="a battery owner offers to deliver power between 18:00 and 19:00 tomorrow and "
                "is paid if the offer is accepted",
        related=["market-operator", "flexibility-bid"]),
    _t("day-ahead",
        "day-ahead market",
        ["day-ahead market", "day-ahead"],
        "markets",
        "a market where electricity for each hour of tomorrow is traded today",
        example="on Monday, traders buy and sell the electricity for each hour of Tuesday"),
    _t("bsp",
        "balancing service provider (BSP)",
        ["BSP", "balancing service provider", "BSP markets"],
        "markets",
        "a company that is qualified to provide balancing services: fast increases or "
        "decreases in power that the national grid operator uses to keep the grid stable",
        related=["balancing", "tso"],
        acronym=True),
    _t("balancing",
        "balancing services",
        ["balancing services", "balancing market", "ancillary services"],
        "markets",
        "services that keep electricity supply and demand matched from second to second, for "
        "example by quickly adding or removing power",
        analogy="it works like a thermostat for the whole grid, making small corrections all "
                "the time"),
    _t("settlement",
        "settlement",
        ["settlement", "settlement services", "settlement schemes", "settlement allocations",
         "financial settlement", "settlement process"],
        "markets",
        "the accounting step after delivery: checking what each participant actually delivered"
        " and working out who is paid, or penalised, and how much",
        why="without settlement, providers can't be paid fairly for the flexibility they "
            "actually delivered",
        example="after an evening peak, the delivered reductions are compared with what was "
                "promised, and each provider's payment is calculated",
        analogy="it is like splitting a restaurant bill after the meal according to what each "
                "person ordered",
        related=["baseline", "activation"]),
    _t("baseline",
        "baseline",
        ["baseline"],
        "flexibility",
        "an estimate of how much electricity a site would have used if it had not changed its "
        "behaviour",
        why="flexibility is measured against the baseline: the difference is what the provider"
            " delivered",
        example="a supermarket normally uses 500 kW at 18:00; if it uses 400 kW after a "
                "request, it delivered 100 kW of flexibility",
        analogy="it is like comparing your step count today with a normal day to see how much "
                "extra you walked",
        related=["settlement"]),
    _t("prequalification",
        "pre-qualification",
        ["pre-qualification", "prequalification", "qualification"],
        "markets",
        "a check, before someone may take part in a market, that their equipment can really "
        "deliver the flexibility they promise",
        analogy="it is like a driving test before you get a licence: you prove you can do it "
                "before you are allowed to",
        related=["flexible-asset"]),
    _t("activation",
        "activation",
        ["activation", "activated flexibility"],
        "markets",
        "the moment a buyer actually calls on flexibility it has accepted, asking the provider"
        " to change its consumption or production now",
        example="at 17:55 the grid operator asks an aggregator to start the reduction it "
                "offered for 18:00"),
    _t("flexible-asset",
        "flexible asset",
        ["flexible asset"],
        "flexibility",
        "a device or installation whose electricity use or production can be adjusted on "
        "request, such as a battery, heat pump, electric-vehicle charger or industrial process",
        example="an office's heat pump can pause for 30 minutes without the building getting "
                "noticeably colder"),
    _t("demand-response",
        "demand response",
        ["demand response"],
        "flexibility",
        "changing electricity consumption in response to a signal or a price, for example "
        "using less at peak times",
        example="a factory delays a cooling cycle by an hour when it is told electricity is "
                "scarce"),
    _t("prosumer",
        "prosumer",
        ["prosumer"],
        "flexibility",
        "someone who both uses and produces energy, for example a household with solar panels"),
    _t("energy-community",
        "energy community",
        ["energy community", "energy communities", "energy community management platform"],
        "flexibility",
        "a group of residents, businesses or public bodies in an area that produce, share or "
        "manage energy together",
        example="neighbours share the power from solar panels on a school roof"),
    _t("building-energy-management",
        "building energy management",
        ["building energy management", "building energy management service",
         "building energy management system", "BEMS", "energy management system"],
        "flexibility",
        "software that monitors and controls a building's heating, cooling, lighting and other"
        " equipment so it uses energy efficiently",
        example="the system lowers heating in empty meeting rooms and pre-heats them before a "
                "booked meeting"),
    _t("value-chain",
        "value chain",
        ["value chain", "flexibility value chain", "value-chain", "energy value chain"],
        "flexibility",
        "everyone involved, step by step, in turning something into value; for flexibility "
        "that runs from the devices that can adjust their use, through aggregators, to the "
        "markets and grid operators that use it"),
    _t("multilateral-agreement",
        "multilateral agreement",
        ["multilateral agreement", "multilateral aggregator agreement", "combination agreement"],
        "markets",
        "an agreement among several parties at once, rather than separate one-to-one agreements"),
    _t("system-operator",
        "system operator",
        ["system operator", "grid operator", "network operator"],
        "grid",
        "the organisation responsible for running an electricity network safely, keeping power"
        " flowing and preventing overloads",
        analogy="it is like air-traffic control for electricity: it keeps everything moving "
                "safely without collisions",
        related=["dso", "tso"]),
    _t("dso",
        "distribution system operator (DSO)",
        ["DSO", "distribution system operator"],
        "grid",
        "the operator of the local and regional networks that deliver electricity to homes and"
        " businesses",
        acronym=True),
    _t("tso",
        "transmission system operator (TSO)",
        ["TSO", "transmission system operator"],
        "grid",
        "the operator of the national high-voltage network that moves electricity over long "
        "distances",
        acronym=True),
    _t("lv-mv",
        "low- and medium-voltage grids (LV/MV)",
        ["LV and MV grids", "LV", "MV", "low voltage", "medium voltage", "low-voltage",
         "medium-voltage"],
        "grid",
        "the parts of the grid closest to customers: low-voltage (LV) lines reach homes and "
        "small businesses, and medium-voltage (MV) lines feed neighbourhoods and larger sites",
        acronym=True),
    _t("congestion",
        "grid congestion",
        ["grid congestion", "congestion", "congestion management"],
        "grid",
        "a situation where part of the grid would have to carry more power than it safely can",
        analogy="it is like a traffic jam on a road that too many cars want to use at the same"
                " time"),
    _t("meter-readings",
        "meter readings",
        ["meter readings", "meter reading", "electricity meter", "smart meter", "meter data",
         "metered delivery"],
        "iot",
        "measurements of how much electricity a site used or produced, recorded by its meter, "
        "often every 15 minutes",
        example="a reading might say that a building used 12 kWh between 09:00 and 09:15"),
    _t("forecasting",
        "forecasting",
        ["forecasting", "forecast", "demand forecasting", "load forecasting", "forecasts",
         "predicts"],
        "forecasting",
        "estimating future values, such as tomorrow's prices or electricity demand, from past "
        "data and inputs like the weather",
        example="using last year's data and tomorrow's weather to estimate how much "
                "electricity a town will use at 18:00",
        analogy="it works like a weather forecast, but for numbers such as prices or demand"),
    _t("data-model",
        "data model",
        ["data model", "shared data model", "approved model"],
        "data",
        "an agreed description of what a set of data looks like: which fields it has, what "
        "each one is called, what it means and which values it may take",
        why="when two systems use the same data model they can exchange data without "
            "misunderstanding each other",
        example="a data model for meter readings might say that every reading has a meter ID, "
                "a time and an energy value in kWh",
        analogy="it is like a form template: everyone fills in the same boxes with the same "
                "labels",
        related=["mapping", "vocabulary"]),
    _t("mapping",
        "mapping",
        ["mapping", "field mapping", "data mapping"],
        "data",
        "a translation rule that says which field or term in one data model corresponds to "
        "which field or term in another",
        example="“consumption” in one system corresponds to “energy_used_kwh” in another",
        analogy="it is like a bilingual dictionary between two systems' vocabularies",
        related=["data-model"]),
    _t("vocabulary",
        "vocabulary",
        ["vocabulary", "vocabularies", "business vocabulary", "shared vocabulary",
         "controlled vocabulary", "vocabulary translation", "vocabulary governance"],
        "data",
        "an agreed list of terms and their meanings that organisations use when describing "
        "their data",
        example="agreeing that “consumption” always means energy used in kWh, measured every "
                "15 minutes",
        analogy="it works like a shared glossary that everyone on a project agrees to use",
        related=["data-model"]),
    _t("vocabulary-hub",
        "vocabulary hub",
        ["vocabulary hub"],
        "data",
        "a shared online place where organisations publish, look up and agree on vocabularies "
        "and data models",
        analogy="it is like a common reference library for data definitions",
        related=["vocabulary", "data-model"]),
    _t("semantic",
        "semantic interoperability",
        ["semantic interoperability", "ontology", "ontologies", "semantic"],
        "data",
        "making sure systems agree not only on data formats but on what the data means"),
    _t("interoperability",
        "interoperability",
        ["interoperability", "interoperable"],
        "data",
        "the ability of different systems to work together and exchange data without custom "
        "fixes",
        analogy="it is like plugs and sockets that follow the same standard, so any device fits"),
    _t("data-space",
        "data space",
        ["data space", "dataspace"],
        "data",
        "an arrangement in which organisations share data with each other under common rules "
        "and technical standards, while each keeps control over who may use its data",
        example="a grid operator shares anonymised meter data with researchers, who may use it"
                " only for an agreed study",
        analogy="it is like a members' club with house rules: members share things with each "
                "other, but each owner decides who may use what",
        related=["connector"]),
    _t("connector",
        "data-space connector",
        ["dataspace connector", "data space connector", "connector"],
        "data",
        "the software component an organisation uses to join a data space and exchange data "
        "under its rules"),
    _t("payload",
        "payload",
        ["payload", "message payload"],
        "messaging",
        "the actual content of a message sent between systems: the data itself, rather than "
        "its addressing or technical wrapping",
        example="in a message from a meter, the payload is the reading itself, such as “12 kWh"
                " at 09:15”",
        analogy="it is like the letter inside an envelope: the address gets it there, but the "
                "letter is what matters"),
    _t("validation",
        "validation",
        ["validation", "payload validation", "validation and verification", "schema validation",
         "verification", "validates", "validate"],
        "messaging",
        "automatically checking that data follows the agreed rules, such as the right fields, "
        "formats and values, before it is used",
        example="rejecting a reading whose value is text instead of a number",
        analogy="it is like a spell-checker, but for data: it flags what doesn't follow the "
                "rules",
        related=["schema"]),
    _t("schema",
        "schema",
        ["schema", "JSON schema"],
        "messaging",
        "a machine-readable rulebook describing what a valid message or file must contain",
        example="a schema can say that every reading must have a numeric “value” field and a "
                "“timestamp”",
        analogy="it is like the rules for filling in an official form: which boxes are "
                "required and what may go in each",
        related=["validation"]),
    _t("json",
        "JSON",
        ["JSON"],
        "messaging",
        "a common text format for structured data that almost all software can read and write",
        acronym=True),
    _t("transformation",
        "data transformation",
        ["transformation", "payload transformation", "data transformation", "conversion",
         "transforms", "converts"],
        "messaging",
        "converting data from one format or structure into another so that a receiving system "
        "can use it",
        example="turning a message that says “temp_c: 21” into one that says “temperature: 21 "
                "°C” for another system",
        analogy="it works like a translator between two systems that speak different dialects"),
    _t("api",
        "API",
        ["API", "APIs", "interface"],
        "messaging",
        "a defined way for one piece of software to request data or actions from another",
        analogy="it is like a restaurant menu: it lists what you can ask for and how to order "
                "it",
        acronym=True),
    _t("http",
        "HTTP endpoint",
        ["HTTP endpoint", "HTTP"],
        "messaging",
        "a web address that software can send data to or request data from",
        acronym=True),
    _t("mqtt",
        "MQTT",
        ["MQTT"],
        "iot",
        "a lightweight messaging protocol that many IoT devices use to send small messages, "
        "such as sensor readings",
        example="a temperature sensor publishes its reading every minute, and any system that "
                "subscribed to that sensor receives it",
        analogy="it works like a group chat for devices: a sensor posts a message and everyone"
                " subscribed to that topic receives it",
        acronym=True),
    _t("telemetry",
        "telemetry",
        ["telemetry", "sensor telemetry"],
        "iot",
        "measurements sent automatically from remote devices, such as temperatures or machine "
        "status",
        example="a wind turbine reports its speed and temperature every few seconds to a "
                "control room",
        analogy="it is like a fitness tracker sending your heart rate to your phone"),
    _t("sensor",
        "sensor",
        ["sensor", "sensor readings"],
        "iot",
        "a device that measures something physical, such as temperature, vibration or power, "
        "and reports it",
        example="a thermometer in a meeting room reports 21 °C every five minutes"),
    _t("iot",
        "IoT (Internet of Things)",
        ["IoT", "Internet of Things"],
        "iot",
        "everyday devices and equipment that are connected to a network and send or receive "
        "data",
        acronym=True),
    _t("dashboard",
        "dashboard",
        ["dashboard"],
        "iot",
        "a screen that shows key measurements and trends at a glance",
        example="a page showing today's electricity use per building, with a chart for the "
                "last week",
        analogy="it is like the dashboard of a car: the key readings at a glance"),
    _t("predictive-maintenance",
        "predictive maintenance",
        ["predictive maintenance", "failure prediction"],
        "maintenance",
        "using equipment measurements to spot early signs of wear, so repairs can be planned "
        "before a breakdown",
        example="a turbine's vibration slowly changes over weeks, so a technician replaces a "
                "worn part during a planned visit instead of after a breakdown",
        analogy="it is like a car's warning light that comes on before the engine fails, not "
                "after"),
    _t("vibration",
        "vibration analysis",
        ["vibration measurements", "vibration analysis", "vibration data", "vibration"],
        "maintenance",
        "measuring how a machine shakes; a change in the vibration pattern can reveal damaged "
        "parts",
        example="a bearing that starts to wear makes the machine shake in a slightly different"
                " rhythm, which sensors can pick up"),
    _t("bearing",
        "bearings and gearboxes",
        ["bearing failure", "bearing", "gearbox"],
        "maintenance",
        "moving parts of rotating machines such as wind turbines: the gearbox changes rotation"
        " speed and bearings let shafts turn smoothly; both wear over time"),
    _t("onboarding",
        "onboarding",
        ["onboarding"],
        "access",
        "registering a new user or organisation and setting up their access"),
    _t("certification",
        "certification",
        ["certification"],
        "access",
        "formal confirmation that a user, device or organisation meets the required standards"),
    _t("role-based-access",
        "role-based access",
        ["role-based data access", "role-based access", "access control"],
        "access",
        "a rule system where what you may see or do depends on your role, so each participant "
        "only sees the data meant for them",
        example="an aggregator can see its own customers' data, while a grid operator sees "
                "only the totals it needs",
        analogy="it is like key cards in an office building: each card opens only the rooms "
                "its holder needs"),
    _t("anonymisation",
        "anonymisation",
        ["anonymised", "anonymized", "anonymisation", "anonymization"],
        "access",
        "removing or masking details that could identify someone, so data can be used without "
        "revealing who it is about",
        example="sharing a neighbourhood's total electricity use without saying which "
                "household used what"),
    _t("audit",
        "audit",
        ["audit", "audit trail"],
        "access",
        "a later check of records to confirm what happened, such as which offers were sent and"
        " when",
        example="months later, checking which offers were submitted on a given day and who "
                "submitted them"),
    _t("container-image",
        "container image",
        ["container image", "container"],
        "software",
        "a packaged copy of software, with everything it needs, that can be installed and run "
        "on a server",
        analogy="it is like a ready-packed moving box with everything the software needs inside"),
    _t("hosted-service",
        "hosted service",
        ["external service", "hosted service", "public URL", "deployed instance"],
        "software",
        "software that runs on the provider's servers; you use it through a web address "
        "instead of installing it yourself",
        analogy="it is like using webmail instead of installing an email program"),
    _t("simulation",
        "simulation",
        ["simulation"],
        "software",
        "running something in a test setting with artificial data instead of the real system, "
        "so it can be tried out safely",
        example="testing how offers would be combined using made-up data, without sending "
                "anything to a real market",
        analogy="it is like a flight simulator: realistic practice without a real plane"),
    _t("pilot",
        "pilot",
        ["pilot"],
        "software",
        "a limited real-world trial before wider use"),
)


def _pattern(alias: str, acronym: bool) -> re.Pattern:
    words = [re.escape(w) for w in re.split(r"[\s-]+", alias)]
    body = r"[\s-]?".join(words)
    exact = acronym and alias.isupper()  # "LV" is an acronym; "lv" is not
    plural = "" if exact else r"(?:s|es)?"
    return re.compile(rf"(?<![\w-]){body}{plural}(?![\w-])", 0 if exact else re.I)


TERMS = tuple(Term(**{**t.__dict__, "patterns": tuple(_pattern(a, t.acronym) for a in t.aliases)})
              for t in TERMS)
BY_ID = {t.id: t for t in TERMS}
_LONGEST_FIRST = sorted(((t.id, p) for t in TERMS for p in t.patterns),
                        key=lambda c: -len(c[1].pattern))


@lru_cache(maxsize=2048)
def find(text: str) -> tuple[tuple[str, int, int], ...]:
    """Non-overlapping concept mentions, longest alias first, in text order."""
    spans: list[tuple[int, int, str]] = []
    for term_id, pattern in _LONGEST_FIRST:
        for match in pattern.finditer(text):
            if not any(match.start() < end and start < match.end() for start, end, _ in spans):
                spans.append((match.start(), match.end(), term_id))
    return tuple((term_id, start, end) for start, end, term_id in sorted(spans))


def mentioned(text: str) -> list[str]:
    """Distinct term ids in order of first mention."""
    return list(dict.fromkeys(term_id for term_id, _, _ in find(text)))


def lookup(phrase: str) -> Term | None:
    """The concept a user asks about ("flexibility bids", "an aggregator", "LV")."""
    phrase = re.sub(r"^(?:an?|the)\s+", "", phrase.strip(" \"'“”‘’?.!"), flags=re.I)
    for term in TERMS:
        if any(p.fullmatch(phrase) for p in term.patterns):
            return term
    return None


def sentence(text: str) -> str:
    return text[0].upper() + text[1:] + ("" if text.endswith((".", "”", "!", "?")) else ".")
