"use strict";

window.addEventListener("DOMContentLoaded", async function () {
  try {
    const response = await fetch("/api/v2/status");
    if (!response.ok) throw new Error("Status unavailable");
    const status = await response.json();
    document.getElementById("catalogue").textContent = status.catalogue;
    document.getElementById("components").textContent = [status.intent, status.embeddings, status.generation].join(" · ");
    document.getElementById("records").textContent = JSON.stringify(status, null, 2);
    const names = status.records.map(record => record.name).filter(Boolean).slice(0, 2);
    const suggestions = status.source === "authored-fixtures"
      ? ["Show me EdgeConnect and Semantic Treehouse", "Find apps for sensor readings", "Find apps for semantic data models"]
      : [names.length ? "Show me " + names.join(" and ") : "Find apps", "Tell me about the first app", "Compare the first two apps"];
    window.storeEvaluation = new window.HedgeExpertWidget({
      title: "Isolated Store Chat Pane",
      subtitle: status.source === "authored-fixtures" ? "Authored fixtures · source quotations only" : "Private snapshot · source quotations only",
      width: "min(560px, calc(100vw - 420px))",
      height: "min(650px, 75vh)",
      restoreHistory: true,
      suggestions: suggestions,
      welcomeText: "Search these supplied evaluation records, ask about recent Apps, or compare their supplied source fields. Product suitability and prices are not established.",
    });
    window.storeEvaluation.open();
  } catch (_) {
    document.getElementById("components").textContent = "Offline backend unavailable. Check the isolated runner logs.";
  }
});
