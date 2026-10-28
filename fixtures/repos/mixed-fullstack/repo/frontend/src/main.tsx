import React from "react";
import { parse } from "yaml";
import { fetchItems } from "./api";

export function App() {
  return <div>{String(parse("a: 1"))}{fetchItems.name}</div>;
}
