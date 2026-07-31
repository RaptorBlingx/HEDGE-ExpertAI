#!/usr/bin/env python3
"""Generate provisional v2 labels without presenting them as HEDGE approval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
CATALOGUE = ROOT / "services/mock-api/app/data/apps-v2.json"
OUTPUT = ROOT / "evaluation/test_queries.json"

PATTERNS = {
    "en": ["Find an IoT application that can {}", "I need software to {}", "Which catalogue app can {}", "Recommend a solution to {}", "Search for tools that {}"],
    "de": ["Finde eine IoT-Anwendung, die {} kann", "Ich brauche Software für {}", "Welche Katalog-App kann {}", "Empfiehl eine Lösung für {}", "Suche Werkzeuge für {}"],
    "fr": ["Trouve une application IoT pour {}", "J'ai besoin d'un logiciel pour {}", "Quelle application du catalogue peut {}", "Recommande une solution pour {}", "Cherche des outils pour {}"],
    "es": ["Busca una aplicación IoT para {}", "Necesito software para {}", "Qué aplicación del catálogo puede {}", "Recomienda una solución para {}", "Busca herramientas para {}"],
    "it": ["Trova un'applicazione IoT per {}", "Mi serve un software per {}", "Quale applicazione del catalogo può {}", "Consiglia una soluzione per {}", "Cerca strumenti per {}"],
    "nl": ["Vind een IoT-app om {}", "Ik heb software nodig om {}", "Welke catalogus-app kan {}", "Raad een oplossing aan om {}", "Zoek hulpmiddelen om {}"],
    "pt": ["Encontra uma aplicação IoT para {}", "Preciso de software para {}", "Que aplicação do catálogo pode {}", "Recomenda uma solução para {}", "Pesquisa ferramentas para {}"],
    "tr": ["{} için bir IoT uygulaması bul", "{} için yazılıma ihtiyacım var", "Hangi katalog uygulaması {} yapabilir", "{} için bir çözüm öner", "{} araçlarını ara"],
}


def render() -> str:
    apps = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    queries = []
    for index, app in enumerate(apps[:60]):
        capability = app["capabilities"][0]
        queries.append(
            {
                "query_id": f"primary-en-{index + 1:03d}",
                "query": PATTERNS["en"][index % 5].format(capability),
                "locale": "en",
                "expected_apps": [app["id"]],
                "category": app["domains"][0],
                "label_status": "provisional_internal",
                "label_source": "deterministic catalogue capability; independent review required",
            }
        )
    for locale in ("de", "fr", "es", "it", "nl", "pt", "tr"):
        for index, app in enumerate(apps[:20]):
            capability = app["capabilities"][0]
            queries.append(
                {
                    "query_id": f"provisional-{locale}-{index + 1:03d}",
                    "query": PATTERNS[locale][index % 5].format(capability),
                    "locale": locale,
                    "expected_apps": [app["id"]],
                    "category": app["domains"][0],
                    "label_status": "provisional_internal_machine_authored",
                    "label_source": "not a native-speaker held-out label; review required",
                }
            )
    return json.dumps(queries, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != content:
            raise SystemExit("evaluation/test_queries.json is stale")
        print("validated 200 visibly provisional evaluation queries")
        return
    OUTPUT.write_text(content, encoding="utf-8")
    print("generated 200 visibly provisional evaluation queries")


if __name__ == "__main__":
    main()
