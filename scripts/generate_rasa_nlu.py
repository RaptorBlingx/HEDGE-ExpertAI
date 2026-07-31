#!/usr/bin/env python3
"""Generate the reviewed-shape multilingual Rasa NLU training corpus.

The application owns dialogue policy. Rasa only classifies the eight supported
intents, so every intent/language pair gets exactly 25 deterministic examples.
The generator keeps the coverage requirement auditable and prevents languages
from silently drifting apart when examples are maintained.
"""

from __future__ import annotations

import argparse
from pathlib import Path

LANGUAGES = ("en", "de", "fr", "es", "it", "nl", "pt", "tr")
INTENTS = ("search", "refine", "compare", "detail", "help", "greeting", "reset", "out_of_scope")

TOPICS = {
    "en": ["energy monitoring", "water quality", "smart buildings", "crop irrigation", "factory maintenance"],
    "de": ["Energieüberwachung", "Wasserqualität", "intelligente Gebäude", "Feldbewässerung", "Fabrikwartung"],
    "fr": ["suivi énergétique", "qualité de l'eau", "bâtiments intelligents", "irrigation agricole", "maintenance industrielle"],
    "es": ["monitorización energética", "calidad del agua", "edificios inteligentes", "riego agrícola", "mantenimiento industrial"],
    "it": ["monitoraggio energetico", "qualità dell'acqua", "edifici intelligenti", "irrigazione agricola", "manutenzione industriale"],
    "nl": ["energiemonitoring", "waterkwaliteit", "slimme gebouwen", "landbouwirrigatie", "fabrieksonderhoud"],
    "pt": ["monitorização de energia", "qualidade da água", "edifícios inteligentes", "irrigação agrícola", "manutenção industrial"],
    "tr": ["enerji izleme", "su kalitesi", "akıllı binalar", "tarımsal sulama", "fabrika bakımı"],
}

TEMPLATES = {
    "search": {
        "en": ["find apps for {}", "show solutions for {}", "I need an application for {}", "recommend IoT tools for {}", "search the catalogue for {}"],
        "de": ["finde Apps für {}", "zeige Lösungen für {}", "ich brauche eine Anwendung für {}", "empfiehl IoT-Werkzeuge für {}", "durchsuche den Katalog nach {}"],
        "fr": ["trouve des applications pour {}", "montre des solutions pour {}", "j'ai besoin d'une application pour {}", "recommande des outils IoT pour {}", "cherche dans le catalogue pour {}"],
        "es": ["busca aplicaciones para {}", "muestra soluciones para {}", "necesito una aplicación para {}", "recomienda herramientas IoT para {}", "busca en el catálogo {}"],
        "it": ["trova applicazioni per {}", "mostra soluzioni per {}", "mi serve un'applicazione per {}", "consiglia strumenti IoT per {}", "cerca nel catalogo {}"],
        "nl": ["vind apps voor {}", "toon oplossingen voor {}", "ik heb een toepassing nodig voor {}", "raad IoT-hulpmiddelen aan voor {}", "zoek in de catalogus naar {}"],
        "pt": ["encontra aplicações para {}", "mostra soluções para {}", "preciso de uma aplicação para {}", "recomenda ferramentas IoT para {}", "pesquisa no catálogo por {}"],
        "tr": ["{} için uygulama bul", "{} için çözümleri göster", "{} için bir uygulamaya ihtiyacım var", "{} için IoT araçları öner", "katalogda {} ara"],
    },
    "refine": {
        "en": ["only open source options for {}", "narrow it to cloud apps for {}", "filter those by MQTT and {}", "show only active products for {}", "limit the results to English apps for {}"],
        "de": ["nur quelloffene Optionen für {}", "grenze auf Cloud-Apps für {} ein", "filtere diese nach MQTT und {}", "zeige nur aktive Produkte für {}", "beschränke die Treffer auf deutsche Apps für {}"],
        "fr": ["uniquement les options libres pour {}", "limite aux applications cloud pour {}", "filtre par MQTT et {}", "montre seulement les produits actifs pour {}", "limite les résultats aux applications françaises pour {}"],
        "es": ["solo opciones de código abierto para {}", "limita a aplicaciones en la nube para {}", "filtra por MQTT y {}", "muestra solo productos activos para {}", "limita los resultados a aplicaciones en español para {}"],
        "it": ["solo opzioni open source per {}", "limita alle applicazioni cloud per {}", "filtra per MQTT e {}", "mostra solo prodotti attivi per {}", "limita i risultati alle applicazioni italiane per {}"],
        "nl": ["alleen opensource-opties voor {}", "beperk tot cloudapps voor {}", "filter op MQTT en {}", "toon alleen actieve producten voor {}", "beperk de resultaten tot Nederlandstalige apps voor {}"],
        "pt": ["apenas opções de código aberto para {}", "limita a aplicações na nuvem para {}", "filtra por MQTT e {}", "mostra apenas produtos ativos para {}", "limita os resultados a aplicações portuguesas para {}"],
        "tr": ["{} için yalnızca açık kaynak seçenekleri", "{} için bulut uygulamalarıyla sınırla", "MQTT ve {} ile filtrele", "{} için yalnızca etkin ürünleri göster", "sonuçları Türkçe {} uygulamalarıyla sınırla"],
    },
    "compare": {
        "en": ["compare the first two for {}", "what differs between the first and second {} results", "compare their protocols for {}", "which recent option is better for {}", "contrast the top three applications for {}"],
        "de": ["vergleiche die ersten beiden für {}", "was unterscheidet den ersten und zweiten Treffer für {}", "vergleiche ihre Protokolle für {}", "welche letzte Option ist besser für {}", "stelle die drei besten Anwendungen für {} gegenüber"],
        "fr": ["compare les deux premiers pour {}", "quelle différence entre le premier et le deuxième résultat pour {}", "compare leurs protocoles pour {}", "quelle option récente est meilleure pour {}", "oppose les trois meilleures applications pour {}"],
        "es": ["compara los dos primeros para {}", "qué diferencia hay entre el primer y segundo resultado de {}", "compara sus protocolos para {}", "qué opción reciente es mejor para {}", "contrasta las tres mejores aplicaciones para {}"],
        "it": ["confronta i primi due per {}", "cosa cambia tra il primo e il secondo risultato per {}", "confronta i protocolli per {}", "quale opzione recente è migliore per {}", "confronta le prime tre applicazioni per {}"],
        "nl": ["vergelijk de eerste twee voor {}", "wat verschilt tussen het eerste en tweede resultaat voor {}", "vergelijk hun protocollen voor {}", "welke recente optie is beter voor {}", "vergelijk de beste drie toepassingen voor {}"],
        "pt": ["compara os dois primeiros para {}", "qual a diferença entre o primeiro e o segundo resultado de {}", "compara os protocolos para {}", "qual opção recente é melhor para {}", "contrasta as três melhores aplicações para {}"],
        "tr": ["{} için ilk ikisini karşılaştır", "{} için birinci ve ikinci sonuç arasındaki fark nedir", "{} için protokollerini karşılaştır", "{} için son seçeneklerden hangisi daha iyi", "{} için ilk üç uygulamayı karşılaştır"],
    },
    "detail": {
        "en": ["tell me more about the first {} result", "explain the second {} app", "show details for app-001 and {}", "what data does the first app use for {}", "describe the top application for {}"],
        "de": ["erzähle mehr über den ersten Treffer für {}", "erkläre die zweite App für {}", "zeige Details zu app-001 und {}", "welche Daten nutzt die erste App für {}", "beschreibe die beste Anwendung für {}"],
        "fr": ["dis-m'en plus sur le premier résultat de {}", "explique la deuxième application de {}", "affiche les détails de app-001 et {}", "quelles données utilise la première application pour {}", "décris la meilleure application pour {}"],
        "es": ["cuéntame más del primer resultado de {}", "explica la segunda aplicación de {}", "muestra detalles de app-001 y {}", "qué datos usa la primera aplicación para {}", "describe la mejor aplicación para {}"],
        "it": ["dimmi di più sul primo risultato per {}", "spiega la seconda applicazione per {}", "mostra i dettagli di app-001 e {}", "quali dati usa la prima applicazione per {}", "descrivi la migliore applicazione per {}"],
        "nl": ["vertel meer over het eerste resultaat voor {}", "leg de tweede app voor {} uit", "toon details voor app-001 en {}", "welke gegevens gebruikt de eerste app voor {}", "beschrijf de beste toepassing voor {}"],
        "pt": ["diz mais sobre o primeiro resultado de {}", "explica a segunda aplicação de {}", "mostra detalhes de app-001 e {}", "que dados usa a primeira aplicação para {}", "descreve a melhor aplicação para {}"],
        "tr": ["{} için ilk sonuç hakkında daha fazla bilgi ver", "{} için ikinci uygulamayı açıkla", "app-001 ve {} ayrıntılarını göster", "ilk uygulama {} için hangi verileri kullanıyor", "{} için en iyi uygulamayı açıkla"],
    },
}

FIXED = {
    "greeting": {
        "en": ["hello", "hi", "good morning", "good afternoon", "good evening"], "de": ["hallo", "guten Morgen", "guten Tag", "guten Abend", "servus"], "fr": ["bonjour", "salut", "bon matin", "bon après-midi", "bonsoir"], "es": ["hola", "buenos días", "buenas tardes", "buenas noches", "qué tal"], "it": ["ciao", "salve", "buongiorno", "buon pomeriggio", "buonasera"], "nl": ["hallo", "hoi", "goedemorgen", "goedemiddag", "goedenavond"], "pt": ["olá", "oi", "bom dia", "boa tarde", "boa noite"], "tr": ["merhaba", "selam", "günaydın", "iyi günler", "iyi akşamlar"],
    },
    "help": {
        "en": ["help me", "what can you do", "how does this work", "show the available commands", "how can I search"], "de": ["hilf mir", "was kannst du", "wie funktioniert das", "zeige die verfügbaren Befehle", "wie kann ich suchen"], "fr": ["aide-moi", "que peux-tu faire", "comment ça marche", "montre les commandes disponibles", "comment puis-je chercher"], "es": ["ayúdame", "qué puedes hacer", "cómo funciona esto", "muestra los comandos disponibles", "cómo puedo buscar"], "it": ["aiutami", "cosa puoi fare", "come funziona", "mostra i comandi disponibili", "come posso cercare"], "nl": ["help me", "wat kun je doen", "hoe werkt dit", "toon de beschikbare opdrachten", "hoe kan ik zoeken"], "pt": ["ajuda-me", "o que podes fazer", "como funciona isto", "mostra os comandos disponíveis", "como posso pesquisar"], "tr": ["yardım et", "ne yapabilirsin", "bu nasıl çalışıyor", "kullanılabilir komutları göster", "nasıl arama yapabilirim"],
    },
    "reset": {
        "en": ["reset", "start over", "clear the search", "forget the previous results", "begin a new topic"], "de": ["zurücksetzen", "von vorn beginnen", "Suche löschen", "vergiss die vorherigen Treffer", "neues Thema beginnen"], "fr": ["réinitialise", "recommence", "efface la recherche", "oublie les résultats précédents", "commence un nouveau sujet"], "es": ["reinicia", "empieza de nuevo", "borra la búsqueda", "olvida los resultados anteriores", "comienza un tema nuevo"], "it": ["reimposta", "ricomincia", "cancella la ricerca", "dimentica i risultati precedenti", "inizia un nuovo argomento"], "nl": ["reset", "begin opnieuw", "wis de zoekopdracht", "vergeet de vorige resultaten", "begin een nieuw onderwerp"], "pt": ["repor", "começa de novo", "limpa a pesquisa", "esquece os resultados anteriores", "inicia um novo tema"], "tr": ["sıfırla", "baştan başla", "aramayı temizle", "önceki sonuçları unut", "yeni bir konu başlat"],
    },
    "out_of_scope": {
        "en": ["write a poem", "book me a flight", "what is the football score", "give medical advice", "solve my tax return"], "de": ["schreibe ein Gedicht", "buche mir einen Flug", "wie steht das Fußballspiel", "gib medizinischen Rat", "erledige meine Steuererklärung"], "fr": ["écris un poème", "réserve-moi un vol", "quel est le score du match", "donne un avis médical", "fais ma déclaration fiscale"], "es": ["escribe un poema", "reserva un vuelo", "cuál es el resultado del fútbol", "da consejos médicos", "haz mi declaración fiscal"], "it": ["scrivi una poesia", "prenotami un volo", "qual è il risultato della partita", "dammi consigli medici", "fai la mia dichiarazione fiscale"], "nl": ["schrijf een gedicht", "boek een vlucht", "wat is de voetbalscore", "geef medisch advies", "doe mijn belastingaangifte"], "pt": ["escreve um poema", "reserva um voo", "qual é o resultado do futebol", "dá aconselhamento médico", "faz a minha declaração fiscal"], "tr": ["şiir yaz", "uçak bileti ayır", "futbol skoru nedir", "tıbbi tavsiye ver", "vergi beyannamemi hazırla"],
    },
}

MODIFIERS = {
    "en": ["", " please", " now", " for me", " if possible"], "de": ["", " bitte", " jetzt", " für mich", " wenn möglich"], "fr": ["", " s'il vous plaît", " maintenant", " pour moi", " si possible"], "es": ["", " por favor", " ahora", " para mí", " si es posible"], "it": ["", " per favore", " adesso", " per me", " se possibile"], "nl": ["", " alstublieft", " nu", " voor mij", " indien mogelijk"], "pt": ["", " por favor", " agora", " para mim", " se possível"], "tr": ["", " lütfen", " şimdi", " benim için", " mümkünse"],
}


def examples(intent: str, language: str) -> list[str]:
    if intent in TEMPLATES:
        return [template.format(topic) for template in TEMPLATES[intent][language] for topic in TOPICS[language]]
    return [phrase + modifier for phrase in FIXED[intent][language] for modifier in MODIFIERS[language]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the committed corpus differs")
    args = parser.parse_args()
    output = ["version: \"3.1\"", "", "# Generated by scripts/generate_rasa_nlu.py; 25 examples per intent/language.", "nlu:"]
    for language in LANGUAGES:
        for intent in INTENTS:
            output.extend([f"  - intent: {intent}", f"    # language: {language}", "    examples: |"])
            output.extend(f"      - {item}" for item in examples(intent, language))
            output.append("")
    destination = Path(__file__).parents[1] / "services" / "rasa" / "data" / "nlu.yml"
    rendered = "\n".join(output)
    if args.check:
        if not destination.exists() or destination.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"{destination} is stale; run scripts/generate_rasa_nlu.py")
        print(f"validated {len(LANGUAGES) * len(INTENTS) * 25} NLU examples")
        return
    destination.write_text(rendered, encoding="utf-8")
    print(f"wrote {destination}: {len(LANGUAGES) * len(INTENTS) * 25} examples")


if __name__ == "__main__":
    main()
