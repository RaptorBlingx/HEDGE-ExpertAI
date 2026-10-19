"""Small reviewed Turkish query vocabulary; unknown requirements survive intact.

This normalizes requests, never translates or enriches Store metadata. It is not
an open-ended translator; unsupported wording remains unverified by suitability.
"""

import re

_TR = {
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
    if locale != "tr":
        return query
    # A quoted native name/ID remains opaque and case-sensitive.
    def token(m):
        value = m[0]
        if value.startswith('"'):
            return value
        return _TR.get(value.replace("İ", "i").replace("I", "ı").lower(), value)

    return re.sub(
        r'"[^"\n]*"|[^\W_]+',
        token,
        query,
    )


def dialogue_language(message: str, locale: str) -> str:
    """A closed grammar for common Turkish controls; constraints do not disappear."""
    if locale != "tr":
        return message
    clean = message.strip().rstrip("?!.,")
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
    "App IDs are case-sensitive. Please use the exact ID or the App's name.":
        ("Uygulama kimliklerinde büyük/küçük harf önemlidir. "
         "Tam kimliği veya uygulama adını kullanın."),
    "Multiple Apps have that name. Please use the exact native App ID.":
        "Birden fazla uygulama bu adı kullanıyor. Tam mağaza uygulama kimliğini belirtin.",
    ("Choose a currently published App by exact name/native ID or an existing reference; "
     "source-field reads do not apply additional constraints."):
        ("Yayımlanmış bir uygulamayı tam adı, kimliği veya mevcut referansıyla seçin; "
         "kaynak alanlarını görüntülemek ek koşulları uygulamaz."),
    (
        "Supplied source fields only; missing metadata cannot be confirmed."
    ): (
        "Yalnızca sağlanan kaynak alanları gösteriliyor; eksik bilgiler doğrulanamaz."
    ),
    (
        "Source-field comparison only; no superiority or suitability is inferred."
    ): (
        "Kaynak alanları karşılaştırılıyor; üstünlük veya uygunluk sonucu "
        "çıkarılmıyor."
    ),
    (
        "References use the observed catalogue order shown on this page."
    ): (
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
    (
        "Supplied Store source values only; these do not establish suitability or "
        "compatibility."
    ): (
        "Sağlanan mağaza değerleri gösteriliyor; bunlar uygunluğu veya uyumluluğu "
        "kanıtlamaz."
    ),
    (
        "Currency, billing period, taxes and licence terms are unspecified. "
        "billable=false or price=0 does not establish that an App is free."
    ): (
        "Para birimi, fatura dönemi, vergiler ve lisans koşulları belirtilmemiş. "
        "billable=false veya price=0, uygulamanın ücretsiz olduğunu kanıtlamaz."
    ),
    (
        "Versions are in source order; no current or latest version is inferred."
    ): (
        "Sürümler kaynak sırasındadır; güncel veya en son sürüm sonucu çıkarılmaz."
    ),
    (
        "Retrieved source records; order does not establish suitability."
    ): (
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
            line = (f"Bu yerel katalogdan {count} yayımlanmış uygulama gösteriliyor (en fazla 5). "
                    "Katalog eksik olabilir; tüm mağazayı kapsadığı doğrulanmamıştır. "
                    "Liste sırası uygunluk sırası değildir.")
        else:
            line = _PROSE_TR.get(line, line)
        lines.append(line)
    return "\n".join(lines)
