(function () {
  "use strict";

  function initializeDemo() {
    var openButton = document.getElementById("open-widget-btn");
    if (!openButton || !window.HedgeExpertWidget) {
      return;
    }

    window._hedgeWidgetInstance = new window.HedgeExpertWidget({
      apiUrl: window.location.origin,
      title: "HEDGE-ExpertAI",
      subtitle: "IoT App Discovery Assistant",
      position: "bottom-right",
      primaryColor: "#0ea5e9",
      width: "400px",
      height: "580px"
    });

    openButton.addEventListener("click", function () {
      window._hedgeWidgetInstance.open();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeDemo, { once: true });
  } else {
    initializeDemo();
  }
})();
