"""Store operation grammars and reviewed Turkish query vocabulary.

This normalizes requests, never translates or enriches Store metadata. It is not
an open-ended translator; unsupported wording remains unverified by suitability.
"""

import re


def control_words(message: str) -> str:
    """Token view for closed control grammars, never for identity or evidence.

    Punctuation, casing and spacing cannot change a control's meaning. All words
    must still be consumed: unknown functions and constraints do not disappear.
    """
    return " ".join(re.findall(r"\w+", message.casefold()))


_CATALOGUE = re.compile(
    r"(?:(?:can|could|would) you )?(?:please )?"
    r"(?:show(?: me)?|list|browse|display|what|which)"
    r"(?: (?:all|the|available|published|currently|store|hedge))*"
    r" (?:apps?|applications?|catalog(?:ue)?)"
    r"(?: (?:are|do|you|have|available|published|currently|in|the|store|hedge|catalog(?:ue)?))*"
    r"\b"
)


def catalogue_question(message: str) -> bool:
    """A catalogue operation, optionally composed with inspection of each entry.

    This is a closed operation grammar, not a functional-query classifier. A
    trailing requirement, filter or extra operation keeps the entire utterance
    on discovery/interpretation; it cannot become an unrestricted listing.
    """
    # Parse operations before composing them. In particular, "explain <question>"
    # contains a metadata question, not an App named "what they do". The same
    # field grammar handles direct questions and embedded question complements.
    # Consume every token; a partial parse can never discard a constraint.
    clauses = re.split(r"\b(?:and(?: then)?|then)\b", control_words(message))
    operations = []
    for clause in clauses:
        clause = re.sub(r"^(?:(?:can|could|would) you )?(?:please )?", "", clause.strip())
        listing = _CATALOGUE.match(clause)
        if listing:
            operations.append("browse")
            clause = clause[listing.end():].strip()
            if not clause:
                continue
        target = inspection_target(clause)
        # Unwrap an imperative once, then resolve its metadata operand. Do not
        # recursively remove arbitrary words or infer missing functional terms.
        operand = target or re.sub(r"^tell me ", "", clause)
        field = factual_question(operand, embedded=True)
        if field:
            if field[0] != "purpose":
                return False
            operand = field[1]
        elif not target:
            return False
        if not re.fullmatch(
            r"(?:(?:each|every)(?: (?:app|application|one))?|they|them|their purposes?)", operand
        ):
            return False
        operations.append("purpose")
    return operations.count("browse") == 1


def inspection_target(message: str) -> str | None:
    """Extract an inspection operand; callers must resolve the *whole* target.

    An unknown operand may be a functional question ("explain how …"), so it
    must not become a metadata read simply because it begins with an imperative.
    """
    match = re.fullmatch(
        r"(?:(?:can|could|would) you )?(?:please )?"
        r"(?:tell me (?:more )?about|describe|explain) (.+?)(?:,? please)?",
        " ".join(message.split()).rstrip("?!.,"), re.I,
    )
    return match[1] if match else None


_TR = {
    "ortak": "shared",
    "farklı": "different",
    "ekiplerin": "teams",
    "aynı": "shared",
    "veriyi": "data",
    "şekilde": "way",
    "tanımlamasını": "model",
    "ne": "what",
    "yönetmek": "manage",
    "yönetimi": "management",
    "yayımlamak": "publish",
    "yayınlamak": "publish",
    "eşlemeleri": "mappings",
    "birleştirmek": "combine",
    "tekliflerini": "bids",
    "teklifleri": "bids",
    "toplayıcının": "aggregators",
    "toplayıcıların": "aggregators",
    "birkaç": "multiple",
    "agregatörün": "aggregators",
    "agregatörlerin": "aggregators",
    "istiyoruz": "want",
    "istiyorum": "want",
    "hangisi": "which",
    "işimize": "useful",
    "yarar": "help",
    "önerirsin": "recommend",
    "gönderir": "send",
    "olduğunda": "when",
    "bu": "this",
    "bunu": "it",
    "bunun": "its",
    "peki": "",
    "enerji": "energy",
    "izleme": "monitoring",
    "izlemek": "monitoring",
    "veri": "data",
    "verileri": "data",
    "modelleri": "models",
    "modeli": "model",
    "modellerini": "models",
    "paylaşılan": "shared",
    "paylaşılmış": "shared",
    "anlamsal": "semantic",
    "tüketim": "consumption",
    "sayaç": "meter",
    "okumaları": "readings",
    "ölçümleri": "readings",
    "deprem": "earthquake",
    "uyarıları": "warnings",
    "uyarı": "warning",
    "üretimde": "production",
    "üretim": "production",
    "destekleyen": "supports",
    "destekliyor": "supports",
    "uygulama": "app",
    "uygulamalar": "apps",
    "uygulamaları": "apps",
    "için": "for",
    "bul": "find",
    "ara": "search",
    "öner": "recommend",
    "lütfen": "please",
    "ve": "and",
    "mu": "does",
    "mi": "does",
    "mı": "does",
    "mü": "does",
    "veya": "or",
    "sadece": "only",
    "yalnızca": "only",
    "olmadan": "without",
    "hariç": "except",
    "ücretsiz": "free",
    "değil": "not",
    "desteklemeyen": "not supporting",
    "desteklemiyor": "does not support",
}


def search_language(query: str, locale: str) -> str:
    query = re.sub(r"^(?:bir de|peki)[, ]+", "", query, flags=re.I)
    query = re.sub(r"\bbirden fazla\b", "multiple", query, flags=re.I)
    # Separate an explicit question from generic narrative background. Retain
    # every earlier sentence with technical words or requirements; e.g. "We
    # need offline access" or "Our teams use MQTT" must not be dropped.
    sentences = re.split(r"(?<=[.!?])\s+", query.strip())
    background = set("our the teams team partners people colleagues departments use have "
                     "different names labels for same data their and we us".split())
    if (len(sentences) > 1 and re.match(r"(?:is there|can you|could you|which|what)\b",
                                       sentences[-1], re.I)
            and all(set(re.findall(r"\w+", s.casefold())) <= background
                    for s in sentences[:-1])):
        query = sentences[-1]
    # A quoted native name/ID remains opaque and case-sensitive.
    def token(m):
        value = m[0]
        if value.startswith('"'):
            return value
        return (
            _TR.get(value.replace("İ", "i").replace("I", "ı").lower(), value)
            if locale == "tr"
            else value
        )

    normalized = re.sub(
        r'"[^"\n]*"|[^\W_]+',
        token,
        query,
    )
    # Lexical equivalents, not inferred capabilities. Qualifiers and unknown
    # words remain in the request and still reach the same source assessor.
    def aliases(text):
        text = re.sub(r"\bwhich one\b", "which", text, flags=re.I)
        text = re.sub(r"\bseveral\b", "multiple", text, flags=re.I)
        text = re.sub(r"\bcommon (?=data models?\b|vocabulary\b)", "shared ", text, flags=re.I)
        text = re.sub(r"\b(?:data dictionaries|data dictionary|vocabulary)\b",
                      "data models", text, flags=re.I)
        text = re.sub(r"\b(?:managing|management)\b", "manage", text, flags=re.I)
        return re.sub(r"\bpublishing\b", "publish", text, flags=re.I)

    return "".join(part if part.startswith('"') else aliases(part)
                   for part in re.split(r'("[^"\n]*")', normalized))


def factual_question(message: str, *, embedded: bool = False) -> tuple[str, str] | None:
    """Closed metadata questions; the dialogue must still resolve the exact target.

    Never treat the rest of a functional requirement as an App reference. Targets
    are validated against current names/IDs and existing conversational bindings.
    """
    clean = " ".join(message.split()).rstrip("?!.,")
    patterns = [
        ("provider", r"(?:who|which (?:company|organisation|organization)) "
                     r"(?:provides|supplies) (.+)"),
        ("provider", r"(?:who|what) is (?:the )?provider(?: (?:of|for) (.+))?"),
        ("provider", r"who (?:is|are) (.+) (?:provided|supplied) by"),
        ("provider", r"what is (.+?)[’']s provider"),
        ("purpose", r"what (?:is|are) (.+?) (?:used for|useful for|for)"),
        ("purpose", r"what (?:does|do) (.+) do"),
    ]
    if embedded:
        # Embedded questions use subject-before-verb order. Admit these only
        # inside operation complements; otherwise a modal question such as
        # "What can <App> do?" could become a source read of "can <App>".
        patterns += [
            ("purpose", r"what (.+?) (?:is|are) (?:used for|useful for|for)"),
            ("purpose", r"what (.+) (?:does|do)"),
            ("purpose", r"(?:the )?purposes? of (.+)"),
        ]
    for field, pattern in patterns:
        match = re.fullmatch(pattern, clean, re.I)
        if match:
            return field, match[1] or "it"
    return None


def dialogue_language(message: str, locale: str) -> str:
    """A closed grammar for common Turkish controls; constraints do not disappear."""
    clean = message.strip().rstrip("?!.,")
    # Conversation controls carry no capability requirement. Match their whole
    # shape so constraints (free, offline, a protocol, etc.) cannot disappear.
    if re.fullmatch(r"(?:even |much )?(?:simpler|less technical)(?:,? please)?", clean, re.I):
        return "Explain it simply"
    if re.fullmatch(r"how (?:does|would) (?:it|that|this|that app|this app) "
                    r"(?:actually )?work(?: in practice)?", clean, re.I):
        return "How does it work?"
    if re.fullmatch(
        r"what (?:have you got|do you have)(?: in (?:the )?(?:store|catalogue))?", clean, re.I
    ):
        return "Show me all available apps"
    if re.fullmatch(
        r"which(?: (?:one|app))? (?:(?:is|would be) (?:better|best)|"
        r"(?:would|should) (?:you|i|we) (?:choose|pick|use))|hangisi daha iyi", clean, re.I,
    ):
        return "Compare both"
    if re.fullmatch(r"what (?:is|are) the (?:main )?differences? between (?:them|these|those)",
                    clean, re.I):
        return "Compare both"
    if re.fullmatch(
        r"(?:(?:can|could|would) you )?(?:please )?(?:"
        r"(?:explain|describe|put) (?:that|it|this) "
        r"(?:in (?:simpler terms|simple terms|plain English|plain language)|more simply)|"
        r"make (?:that|it|this) (?:(?:even |much |a bit )?simpler|less technical))|"
        r"(?:bunu )?daha (?:basit|sade) (?:anlat|açıkla)(?:ır mısın|r mısın)?|"
        r"(?:bunu )?(?:basitleştir|sadeleştir)", clean, re.I,
    ):
        return "Explain it simply"
    if re.fullmatch(
        r"how (?:are|do) (?:those|these|they|the) (?:two |apps? )?(?:different|differ)|"
        r"(?:bunların|ikisinin|aralarındaki) farkı (?:ne|nedir)|"
        r"(?:ikisi|bunlar) arasındaki (?:fark|farklar) (?:ne|nedir)",
        clean,
        re.I,
    ):
        return "Compare both"
    if re.fullmatch(r"(?:hangi |ne tür )?uygulamalar (?:var|mevcut)", clean, re.I):
        return "Show me all available apps"
    if re.fullmatch(r"(?:tell me more about |more about )(?:that|this) one", clean, re.I):
        return "Tell me about it"
    if re.fullmatch(
        r"(?:peki[, ]+)?(?:bunu|bunun|bu uygulamayı) (?:anlat|açıkla|ne işe yarıyor)", clean, re.I
    ):
        return "Tell me about it"
    if re.fullmatch(
        r"(?:peki[, ]+)?(?:bunu )?nasıl "
        r"(?:kullanmaya başlayabilirim|kullanmaya başlayabiliriz|kullanırım|kullanabiliriz)",
        clean,
        re.I,
    ):
        return "How do I get started with it?"
    if re.fullmatch(
        r"(?:how|where) (?:do|should|can) (?:i|we) (?:get started|start|begin) "
        r"(?:with |using )?(?:it|this app|that app|this one|that one)", clean, re.I,
    ):
        return "How do I get started with it?"
    if re.fullmatch(r"(?:is (?:it|this app|that app)|are (?:they|these apps)) (?:free|paid)|"
                    r"does (?:it|this app|that app) cost anything", clean, re.I):
        return "How much does it cost?"
    if re.fullmatch(
        r"(?:ücretli|ücretsiz) mi|(?:bunun )?(?:ücreti|fiyatı) (?:ne|nedir|ne kadar)", clean, re.I
    ):
        return "How much does it cost?"
    if re.fullmatch(
        r"(?:bir de |peki[, ]+)?(?:diğerini|diğeri)(?: anlat| ne yapıyor| ne işe yarıyor)?",
        clean,
        re.I,
    ):
        return "Tell me about the other app"
    if re.fullmatch(r"(?:how (?:does|would) (?:it|that|this) work|"
                    r"(?:bu|bunu) nasıl (?:çalışır|çalışıyor))", clean, re.I):
        return "Explain how it works"
    if re.fullmatch(r"(?:kurulum|konteyner kurulumu) yapmadan kullanabilir miyiz", clean, re.I):
        return "Can we use it without installing a container?"
    if locale != "tr":
        return message
    if re.fullmatch(r"(?:tüm |bütün )?uygulamaları (?:göster|listele)", clean, re.I):
        return "Show me all available apps"
    match = re.fullmatch(
        r"(ilk|birinci|ikinci|üçüncü|dördüncü|beşinci) uygulamayı (?:açıkla|anlat)", clean, re.I
    )
    if match:
        ordinal = {
            "ilk": "first",
            "birinci": "first",
            "ikinci": "second",
            "üçüncü": "third",
            "dördüncü": "fourth",
            "beşinci": "fifth",
        }
        return "Tell me about the " + ordinal[match[1].replace("İ", "i").lower()] + " app"
    if re.fullmatch(r"(?:ilk )?ikisini karşılaştır", clean, re.I):
        return "Compare the first two apps" if clean.lower().startswith("ilk ") else "Compare both"
    match = re.fullmatch(r"(.+?) (?:ile|ve) (.+?) (?:uygulamalarını )?karşılaştır", clean, re.I)
    if match:
        return f"Compare {match[1]} and {match[2]}"
    match = re.fullmatch(r"(.+?) (?:ne yapar|hakkında bilgi ver)", clean, re.I)
    if match:
        return "Tell me about " + match[1]
    match = re.fullmatch(r"(.+?) (?:fiyatı ne kadar|ücreti nedir)", clean, re.I)
    if match:
        return "How much does " + match[1] + " cost"
    return message


_PROSE_TR = {
    "App IDs are case-sensitive. Please use the exact ID or the App's name.": (
        "Uygulama kimliklerinde büyük/küçük harf önemlidir. "
        "Tam kimliği veya uygulama adını kullanın."
    ),
    "Multiple Apps have that name. Please use the exact native App ID.": (
        "Birden fazla uygulama bu adı kullanıyor. Tam mağaza uygulama kimliğini belirtin."
    ),
    (
        "Choose a currently published App by exact name/native ID or an existing reference; "
        "source-field reads do not apply additional constraints."
    ): (
        "Yayımlanmış bir uygulamayı tam adı, kimliği veya mevcut referansıyla seçin; "
        "kaynak alanlarını görüntülemek ek koşulları uygulamaz."
    ),
    ("Supplied source fields only; missing metadata cannot be confirmed."): (
        "Yalnızca sağlanan kaynak alanları gösteriliyor; eksik bilgiler doğrulanamaz."
    ),
    ("Source-field comparison only; no superiority or suitability is inferred."): (
        "Kaynak alanları karşılaştırılıyor; üstünlük veya uygunluk sonucu çıkarılmıyor."
    ),
    ("References use the observed catalogue order shown on this page."): (
        "Referanslar bu sayfada gösterilen katalog sırasını kullanıyor."
    ),
    (
        "I cannot resolve those references to currently published Apps. Search for "
        "Apps or provide their names; comparison needs at least two."
    ): (
        "Bu referansları yayımlanmış uygulamalarla eşleştiremedim. Uygulamaları arayın "
        "veya adlarını belirtin; karşılaştırma için en az iki uygulama gerekir."
    ),
    (
        "The supplied Store fields do not verify that capability, metadata or filter. "
        "I cannot confirm support or suitability. I can describe an App's supplied "
        "fields or compare the source descriptions."
    ): (
        "Mağaza alanları bu özelliği veya filtreyi doğrulamıyor. Desteği ya da "
        "uygunluğu doğrulayamıyorum. Sağlanan alanları açıklayabilir veya kaynak "
        "açıklamalarını karşılaştırabilirim."
    ),
    (
        "This snapshot has no verified price information. I cannot confirm what it "
        "costs. I can describe an App's supplied fields or compare the source "
        "descriptions."
    ): (
        "Bu katalogda doğrulanmış fiyat bilgisi yok. Ücreti doğrulayamıyorum. Sağlanan "
        "alanları açıklayabilir veya kaynak açıklamalarını karşılaştırabilirim."
    ),
    ("Supplied Store source values only; these do not establish suitability or compatibility."): (
        "Sağlanan mağaza değerleri gösteriliyor; bunlar uygunluğu veya uyumluluğu kanıtlamaz."
    ),
    (
        "Currency, billing period, taxes and licence terms are unspecified. "
        "billable=false or price=0 does not establish that an App is free."
    ): (
        "Para birimi, fatura dönemi, vergiler ve lisans koşulları belirtilmemiş. "
        "billable=false veya price=0, uygulamanın ücretsiz olduğunu kanıtlamaz."
    ),
    ("Versions are in source order; no current or latest version is inferred."): (
        "Sürümler kaynak sırasındadır; güncel veya en son sürüm sonucu çıkarılmaz."
    ),
    ("Retrieved source records; order does not establish suitability."): (
        "Kaynak kayıtları bulundu; sıralama uygunluğu kanıtlamaz."
    ),
}


def localize_prose(message: str, locale: str) -> str:
    if locale != "tr":
        return message
    lines = []
    for line in message.split("\n"):
        # Source quotations are rendered on their own '- App ...' lines. Never
        # replace substrings within metadata or pretend to translate quotations.
        if (
            line.startswith("Showing ")
            and "currently eligible Apps from this isolated snapshot" in line
        ):
            count = re.match(r"Showing (\d+)", line)[1]
            line = (
                f"Bu yerel katalogdan {count} yayımlanmış uygulama gösteriliyor (en fazla 5). "
                "Katalog eksik olabilir; tüm mağazayı kapsadığı doğrulanmamıştır. "
                "Liste sırası uygunluk sırası değildir."
            )
        else:
            line = _PROSE_TR.get(line, line)
        lines.append(line)
    return "\n".join(lines)
