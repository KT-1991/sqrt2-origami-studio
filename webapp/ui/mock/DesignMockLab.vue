<script setup lang="ts">
import { computed, ref } from "vue";

type VariantId =
  | "atelier"
  | "draftboard"
  | "paper"
  | "workbench"
  | "workbench-midnight"
  | "workbench-glass"
  | "workbench-sand"
  | "workbench-crt"
  | "workbench-schematic"
  | "workbench-cadlight";

interface VariantOption {
  id: VariantId;
  label: string;
  subtitle: string;
  note: string;
}

const variants: VariantOption[] = [
  {
    id: "atelier",
    label: "Atelier",
    subtitle: "Warm craft mood",
    note: "Tool-like with warm accent and soft panel depth.",
  },
  {
    id: "draftboard",
    label: "Draftboard",
    subtitle: "Technical dense",
    note: "Information-heavy light technical board.",
  },
  {
    id: "paper",
    label: "Rice Paper",
    subtitle: "Calm gallery",
    note: "Quiet presentation style with low visual noise.",
  },
  {
    id: "workbench",
    label: "Workbench",
    subtitle: "VSCode-like",
    note: "Desktop IDE style with rails, tabs, split editor, and terminal.",
  },
  {
    id: "workbench-midnight",
    label: "Workbench Midnight",
    subtitle: "High contrast dark",
    note: "Sharper contrast and brighter syntax-like accents.",
  },
  {
    id: "workbench-glass",
    label: "Workbench Glass",
    subtitle: "Cool translucent",
    note: "Frosted translucent desktop style with cool blues.",
  },
  {
    id: "workbench-sand",
    label: "Workbench Sand",
    subtitle: "Warm retro terminal",
    note: "Warm beige terminal vibe while preserving tool layout.",
  },
  {
    id: "workbench-crt",
    label: "Workbench CRT",
    subtitle: "Phosphor terminal",
    note: "Green phosphor monitor vibe with scanline-like contrast.",
  },
  {
    id: "workbench-schematic",
    label: "Workbench Schematic",
    subtitle: "Wiring diagram",
    note: "Blueprint-like cyan lines and technical signal colors.",
  },
  {
    id: "workbench-cadlight",
    label: "Workbench CAD Light",
    subtitle: "White drafting",
    note: "Minimal white CAD board with crisp monochrome hierarchy.",
  },
];

const active = ref<VariantId>("workbench");
const activeMeta = computed(() => variants.find((v) => v.id === active.value) ?? variants[0]);
const isWorkbench = computed(() => active.value.startsWith("workbench"));

const sampleRows = [
  { name: "tiling seed", value: "42" },
  { name: "alpha steps", value: "18" },
  { name: "budget depth", value: "8" },
  { name: "budget nodes", value: "1200" },
];

const wbTabs = ["paper.canvas", "generation.config", "preview.fold"];
const wbTree = [
  "project/",
  "  ui/App.vue",
  "  engine/creasegen.ts",
  "  presets/balanced.json",
  "  output/latest.cp",
];
</script>

<template>
  <main class="mock-lab" :class="`variant-${active}`">
    <header class="mock-head">
      <div>
        <p class="eyebrow">UI Pattern Mock</p>
        <h1>Origami Tool Skin Lab</h1>
        <p class="note">
          Visual-only experiments. Engine behavior is unchanged.
        </p>
      </div>
      <div class="variant-switch">
        <button
          v-for="v in variants"
          :key="v.id"
          class="chip"
          :class="{ active: active === v.id }"
          type="button"
          @click="active = v.id"
        >
          <span>{{ v.label }}</span>
          <small>{{ v.subtitle }}</small>
        </button>
      </div>
    </header>

    <section v-if="!isWorkbench" class="mock-grid">
      <aside class="mock-panel stack">
        <h2>Run Deck</h2>
        <button class="run-btn primary" type="button">Run crease generation</button>
        <button class="run-btn" type="button">Run tiling optimization</button>
        <button class="run-btn" type="button">Run fold preview</button>
        <p class="tip">active skin: {{ activeMeta.label }} / {{ activeMeta.note }}</p>
      </aside>

      <section class="mock-panel canvas-panel">
        <h2>Paper Canvas</h2>
        <svg viewBox="0 0 400 400" class="canvas">
          <rect x="30" y="30" width="340" height="340" class="paper" />
          <line x1="30" y1="370" x2="370" y2="30" class="axis" />
          <circle cx="120" cy="120" r="8" class="pt axis-pt" />
          <circle cx="188" cy="148" r="8" class="pt side-pt" />
          <circle cx="252" cy="212" r="8" class="pt mirror-pt" />
          <circle cx="148" cy="240" r="8" class="pt side-pt" />
          <line x1="120" y1="120" x2="188" y2="148" class="seed-edge" />
          <line x1="188" y1="148" x2="148" y2="240" class="seed-edge" />
        </svg>
      </section>

      <aside class="mock-panel stack">
        <h2>Generation Summary</h2>
        <div class="kv" v-for="r in sampleRows" :key="r.name">
          <span>{{ r.name }}</span>
          <strong>{{ r.value }}</strong>
        </div>
        <div class="block">
          <p>corner count</p>
          <h3>14</h3>
        </div>
        <div class="block">
          <p>seed edges</p>
          <h3>9</h3>
        </div>
      </aside>

      <section class="mock-panel preview-panel">
        <h2>Crease / Fold Preview</h2>
        <div class="preview-grid">
          <svg viewBox="0 0 300 300" class="mini">
            <rect x="24" y="24" width="252" height="252" class="mini-bg" />
            <line x1="24" y1="24" x2="276" y2="276" class="mini-edge" />
            <line x1="24" y1="276" x2="276" y2="24" class="mini-edge" />
            <line x1="150" y1="24" x2="150" y2="276" class="mini-edge2" />
            <line x1="24" y1="150" x2="276" y2="150" class="mini-edge2" />
          </svg>
          <svg viewBox="0 0 300 300" class="mini">
            <rect x="24" y="24" width="252" height="252" class="mini-bg" />
            <polygon points="42,42 188,60 160,178 64,164" class="face f1" />
            <polygon points="160,178 258,110 242,246 144,250" class="face f2" />
            <polygon points="64,164 144,250 42,250" class="face f3" />
          </svg>
        </div>
      </section>
    </section>

    <section v-else class="workbench-shell">
      <nav class="wb-activity">
        <button class="wb-icon active" type="button">F</button>
        <button class="wb-icon" type="button">S</button>
        <button class="wb-icon" type="button">R</button>
        <button class="wb-icon" type="button">G</button>
      </nav>

      <aside class="wb-sidebar">
        <h2>Explorer</h2>
        <ul class="wb-tree">
          <li v-for="item in wbTree" :key="item">{{ item }}</li>
        </ul>
        <div class="wb-side-actions">
          <button class="wb-side-btn primary" type="button">Run</button>
          <button class="wb-side-btn" type="button">Tiling</button>
          <button class="wb-side-btn" type="button">Preview</button>
        </div>
      </aside>

      <section class="wb-main">
        <div class="wb-tabs">
          <button
            v-for="(tab, idx) in wbTabs"
            :key="tab"
            class="wb-tab"
            :class="{ active: idx === 0 }"
            type="button"
          >
            {{ tab }}
          </button>
        </div>

        <div class="wb-editor-area">
          <section class="wb-editor-canvas">
            <h3>paper.canvas</h3>
            <svg viewBox="0 0 420 320" class="wb-svg">
              <rect x="54" y="20" width="312" height="280" class="wb-paper" />
              <line x1="54" y1="300" x2="366" y2="20" class="wb-axis" />
              <circle cx="132" cy="86" r="7" class="wb-pt-a" />
              <circle cx="186" cy="124" r="7" class="wb-pt-b" />
              <circle cx="240" cy="170" r="7" class="wb-pt-b" />
              <line x1="132" y1="86" x2="186" y2="124" class="wb-seed" />
              <line x1="186" y1="124" x2="240" y2="170" class="wb-seed" />
            </svg>
          </section>

          <aside class="wb-inspector">
            <h3>Inspector</h3>
            <div class="wb-kv" v-for="r in sampleRows" :key="r.name">
              <span>{{ r.name }}</span>
              <strong>{{ r.value }}</strong>
            </div>
            <div class="wb-kv">
              <span>profile</span>
              <strong>balanced</strong>
            </div>
            <div class="wb-kv">
              <span>status</span>
              <strong>ready</strong>
            </div>
          </aside>
        </div>

        <div class="wb-terminal">
          <p>$ npm run origami --profile balanced</p>
          <p>[tiling] alpha=0.842 ok</p>
          <p>[creasegen] nodes=641 violations=0</p>
          <p>[preview] faces=38 done</p>
        </div>
      </section>
    </section>

    <footer class="mock-foot">
      <span>
        Open this lab with <code>?mode=ui-mock</code>. Current variant: <strong>{{ activeMeta.label }}</strong>.
      </span>
    </footer>
  </main>
</template>
