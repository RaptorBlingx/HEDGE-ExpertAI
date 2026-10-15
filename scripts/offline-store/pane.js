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
    const metadataDemo = status.simulation_controls === true;
    const suggestions = metadataDemo
      ? ["Find apps for district heat measurements", "Find apps for vocabulary review", "Show me all available applications"]
      : status.source === "authored-fixtures"
      ? ["Show me EdgeConnect and Semantic Treehouse", "Find apps for sensor readings", "Find apps for semantic data models"]
      : [names.length ? "Show me " + names.join(" and ") : "Find apps", "Tell me about the first app", "Compare the first two apps"];
    window.storeEvaluation = new window.HedgeExpertWidget({
      title: "ExpertAI · Store source explorer",
      subtitle: status.source === "authored-fixtures" ? "Authored fixtures · source quotations only" : "Private snapshot · source quotations only",
      width: "min(560px, calc(100vw - 420px))",
      height: "min(650px, 75vh)",
      restoreHistory: true,
      suggestions: suggestions,
      welcomeText: "Discover Apps in this snapshot, inspect their source evidence, and compare supplied fields. Product suitability and billing terms are not established.",
    });
    window.storeEvaluation.open();
    const prompts = metadataDemo ? [
      "Find apps for district heat measurements",
      "Find apps for vocabulary review",
      "Show README for Demo Telemetry Bridge",
      "Show embedded metadata for Demo Telemetry Bridge",
      "Show connector fields for Demo Telemetry Bridge",
      "Show billing fields for Demo Telemetry Bridge",
      "Show versions for Demo Telemetry Bridge",
      "Show README for Demo Long Documentation",
      "Show embedded metadata for Demo Sparse Catalogue",
      "Show me all available applications",
      "Compare the first two apps",
    ] : suggestions.concat(["Show README for the first app", "Show connector fields for the first app", "Show billing fields for the first app"]);
    prompts.forEach(prompt => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = prompt;
      button.addEventListener("click", () => {
        window.storeEvaluation.open();
        window.storeEvaluation.textarea.value = prompt;
        window.storeEvaluation.textarea.focus();
      });
      document.getElementById("scenarios").appendChild(button);
    });
    if (status.simulation_controls) {
      document.getElementById("publisher").hidden = false;
      ["update", "withdraw", "restore"].forEach(action => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = action[0].toUpperCase() + action.slice(1) + " demo App";
        button.addEventListener("click", async () => {
          button.disabled = true;
          const output = document.getElementById("publisher-status");
          output.textContent = "Applying authored source change…";
          try {
            const result = await fetch("/evaluation/scenario/" + action, { method: "POST" });
            if (!result.ok) throw new Error("Scenario failed");
            const receipt = await result.json();
            output.textContent = "Applied " + action + " · revision " + receipt.revision +
              " · " + receipt.pipeline.vector_points + " vector points. Search or request source fields again.";
            document.getElementById("pipeline").textContent = receipt.pipeline.eligible_records +
              " eligible records persisted · " + receipt.pipeline.vector_points + " vector points · " + receipt.pipeline.vector_mode;
          } catch (_) {
            output.textContent = "Source/index update failed. Check this isolated runner; retry before evaluating freshness.";
          } finally { button.disabled = false; }
        });
        document.getElementById("publisher-actions").appendChild(button);
      });
    }
    const pipeline = status.pipeline || {};
    document.getElementById("pipeline").textContent = pipeline.eligible_records === undefined
      ? "Pipeline receipts unavailable."
      : pipeline.eligible_records + " eligible records persisted · " + pipeline.vector_points + " vector points · " + pipeline.vector_mode;

  } catch (_) {
    document.getElementById("components").textContent = "Offline backend unavailable. Check the isolated runner logs.";
  }
});
