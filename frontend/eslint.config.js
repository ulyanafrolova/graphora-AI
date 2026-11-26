import js from "@eslint/js";
import importPlugin from "eslint-plugin-import";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

// specs/019-frontend research R2: graph facts come from the service, never from Cytoscape traversal
const TRAVERSAL = [
  "bfs",
  "breadthFirstSearch",
  "dfs",
  "depthFirstSearch",
  "dijkstra",
  "aStar",
  "floydWarshall",
  "bellmanFord",
  "kruskal",
  "pageRank",
  "predecessors",
  "successors",
  "degreeCentrality",
  "degreeCentralityNormalized",
  "closenessCentrality",
  "closenessCentralityNormalized",
  "betweennessCentrality",
  "markovClustering",
  "kMeans",
  "hierarchicalClustering",
];

export default tseslint.config(
  { ignores: ["dist", "node_modules", "playwright-report", "test-results", "src/api/graph.gen.ts"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    settings: { react: { version: "detect" } },
    plugins: { react, "react-hooks": reactHooks, import: importPlugin },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs["jsx-runtime"].rules,
      ...reactHooks.configs.recommended.rules,
      "react/no-danger": "error",
      "react/no-danger-with-children": "error",
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "no-restricted-properties": [
        "error",
        ...TRAVERSAL.map((property) => ({ property, message: "graph facts come from the Graphora service (research R2)" })),
      ],
      "no-restricted-syntax": [
        "error",
        { selector: "MemberExpression[property.name='innerHTML']", message: "render text, never HTML (research R12)" },
        { selector: "MemberExpression[property.name='outerHTML']", message: "render text, never HTML (research R12)" },
      ],
      "import/order": [
        "error",
        {
          "newlines-between": "always",
          alphabetize: { order: "asc" },
          pathGroups: [{ pattern: "@/**", group: "internal" }],
          pathGroupsExcludedImportTypes: ["builtin"],
        },
      ],
    },
  },
);
