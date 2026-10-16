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
    if (status.managed_workspace) {
      document.getElementById("catalogue").textContent = "Actual Store records from an authorized observation. See refresh state and timestamp; these are not authored fixtures.";
      document.getElementById("managed").hidden = false;
      let offset = 0;
      let next = null;
      const showState = state => {
        document.getElementById("sync-status").textContent = "Refresh: " + state.state +
          " · Snapshot observed: " + (state.snapshot_at || "never") + " (" + (state.timestamp_basis || "local") + ")" +
          " · Index pending: " + (state.index_pending ?? "unknown") +
          ". Complete/current upstream catalogue coverage is unverified.";
      };
      const loadPage = async () => {
        const response = await fetch("/api/v2/catalogue?offset=" + offset + "&limit=25");
        if (!response.ok) throw new Error("Catalogue unavailable");
        const page = await response.json();
        next = page.next_offset;
        document.getElementById("catalogue-count").textContent = page.total + " locally available Apps · native ID order · page " + (1 + offset / 25);
        const target = document.getElementById("catalogue-apps");
        target.replaceChildren();
        page.apps.forEach(record => {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = record.name || record.app_id;
          button.addEventListener("click", () => {
            window.storeEvaluation.open();
            window.storeEvaluation.textarea.value = "Tell me about " + record.app_id;
            window.storeEvaluation.textarea.focus();
          });
          target.appendChild(button);
        });
        document.getElementById("catalogue-previous").disabled = offset === 0;
        document.getElementById("catalogue-next").disabled = next === null;
      };
      showState(status.synchronization);
      document.getElementById("refresh-store").addEventListener("click", async event => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          const response = await fetch("/evaluation/refresh", { method: "POST" });
          if (!response.ok) throw new Error("Refresh failed");
          const result = await response.json();
          showState(result.synchronization);
          offset = 0;
          await loadPage();
        } catch (_) {
          document.getElementById("sync-status").textContent = "Refresh failed. Retained snapshot may be stale; retry required.";
        } finally { button.disabled = false; }
      });
      const catalogueFailure = () => {
        document.getElementById("catalogue-count").textContent = "Catalogue unavailable; retry required.";
        document.getElementById("catalogue-apps").replaceChildren();
      };
      document.getElementById("catalogue-next").addEventListener("click", () => { offset = next ?? offset; loadPage().catch(catalogueFailure); });
      document.getElementById("catalogue-previous").addEventListener("click", () => { offset = Math.max(0, offset - 25); loadPage().catch(catalogueFailure); });
      await loadPage().catch(catalogueFailure);
    }
    const suggestions = metadataDemo
      ? ["Find apps for district heat measurements", "Find apps for vocabulary review", "Show me all available applications"]
      : status.source === "authored-fixtures"
      ? ["Show me EdgeConnect and Semantic Treehouse", "Find apps for sensor readings", "Find apps for semantic data models"]
      : [names.length ? "Show me " + names.join(" and ") : "Find apps", "Tell me about the first app", "Compare the first two apps"];
    window.storeEvaluation = new window.HedgeExpertWidget({
      title: "ExpertAI · App assistant",
      subtitle: status.source === "authored-fixtures" ? "Authored fixtures · source quotations only" : "Private Store · grounded conversation",
      width: "min(560px, calc(100vw - 420px))",
      height: "min(650px, 75vh)",
      restoreHistory: true,
      suggestions: suggestions,
      welcomeText: "Browse the observed catalogue, ask about an App by name, then use first, second or it to explore and compare. Open Source evidence for complete projected fields. I cannot verify suitability or undocumented terms.",
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
    document.getElementById("pipeline").textContent = status.managed_workspace
      ? "Durable PostgreSQL catalogue · real E5/Qdrant · " + status.synchronization.available +
        " locally available records · " + status.synchronization.index_pending + " index operations pending"
      : pipeline.eligible_records === undefined
      ? "Pipeline receipts unavailable."
      : pipeline.eligible_records + " eligible records persisted · " + pipeline.vector_points + " vector points · " + pipeline.vector_mode;

  } catch (_) {
    document.getElementById("components").textContent = "Offline backend unavailable. Check the isolated runner logs.";
  }
});
