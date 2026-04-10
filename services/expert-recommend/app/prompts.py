"""LLM prompt templates for HEDGE-ExpertAI."""

SYSTEM_PROMPT = (
    "You are HEDGE-ExpertAI, an AI assistant for the HEDGE-IoT App Store. "
    "Your role is to help users discover and understand IoT applications. "
    "When given search results, explain why each app matches the user's query. "
    "Be concise and widget-friendly. Use markdown bullets with one short bullet per app. "
    "Only use information from the provided metadata. "
    "If no apps match well, say so honestly. "
    "Do NOT invent features or capabilities not in the metadata. "
    "CRITICAL: Keep ranking consistent with provided order: App 1 is rank #1, App 2 is rank #2, etc. "
    "Never call another app the top recommendation if it is not App 1."
)

RECOMMENDATION_TEMPLATE = """User query: {query}

Here are the top matching IoT applications from the HEDGE App Store:

{apps_context}

Please provide a brief, helpful response that:
1. Starts with one short recommendation line telling the user which app to try first; this must be App 1 unless the user explicitly asks for a different constraint
2. Then gives markdown bullet points in the SAME order as listed above, with exactly one bullet per app
3. Starts each bullet with `- **App N: App Title**` and briefly highlights why it matches the query
4. Fits comfortably in a chat widget: keep the full answer under roughly 220 tokens when possible

Ranking consistency requirements:
- Keep app ordering exactly as App 1, App 2, App 3...
- If you mention "top", "best", or "start with", it must refer to App 1
- Do not reorder apps based on your own preference
- Do not use numbered lists for the app summaries; use markdown bullets
"""

EXPLANATION_TEMPLATE = """User query: {query}

App: {app_title}
Description: {app_description}
Tags: {app_tags}
SAREF Category: {saref_type}
Input Data: {input_datasets}
Output Data: {output_datasets}

Explain in 2-3 sentences why this app is relevant to the user's query. Focus on concrete capabilities.
"""


def format_apps_context(apps: list[dict], max_apps: int = 5) -> str:
    """Format a list of app results into compact context for the LLM."""
    parts = []
    for i, result in enumerate(apps[:max_apps], 1):
        app = result.get("app", result)
        tags = ", ".join(app.get("tags", []))
        parts.append(
            f"App {i}: {app.get('title', 'Unknown')}\n"
            f"  Description: {app.get('description', 'N/A')}\n"
            f"  Tags: {tags}\n"
            f"  Score: {result.get('score', 'N/A')}"
        )
    return "\n\n".join(parts)


def build_recommendation_messages(query: str, apps: list[dict]) -> list[dict[str, str]]:
    """Build the message list for a recommendation request."""
    apps_context = format_apps_context(apps)
    user_message = RECOMMENDATION_TEMPLATE.format(query=query, apps_context=apps_context)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]


def build_explanation_messages(query: str, app: dict) -> list[dict[str, str]]:
    """Build the message list for an app explanation request."""
    user_message = EXPLANATION_TEMPLATE.format(
        query=query,
        app_title=app.get("title", "Unknown"),
        app_description=app.get("description", "N/A"),
        app_tags=", ".join(app.get("tags", [])),
        saref_type=app.get("saref_type", "N/A"),
        input_datasets=", ".join(app.get("input_datasets", [])),
        output_datasets=", ".join(app.get("output_datasets", [])),
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
