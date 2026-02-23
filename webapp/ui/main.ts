import { createApp } from "vue";
import App from "./App.vue";
import DesignMockLab from "./mock/DesignMockLab.vue";
import "./styles.css";
import "./mock/design_mock_lab.css";

const params = new URLSearchParams(window.location.search);
const mode = params.get("mode");

createApp(mode === "ui-mock" ? DesignMockLab : App).mount("#app");
