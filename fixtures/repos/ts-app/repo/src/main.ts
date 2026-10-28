import { helper } from "./util.js";
import { lib } from "./lib";
import * as models from "@app/models";
import "./polyfill";
import type { Config } from "@lib";
import { type Shape, area } from "./shapes";
import fs = require("fs");
import { readFile } from "node:fs";
import { stat } from "fs/promises";
import { deep } from "@scope/pkg/deep";
import React from "react";
import "./styles.css";
import data from "./data.json";
import logo from "./logo.svg";
import { gone } from "./missing";
import { nope } from "@app/missing";
import { settings } from "src/config";

export function main(config: Config, shape: Shape): void {
  helper(lib, models, area(shape), fs, readFile, stat, deep, React, data, logo, gone, nope, settings, config);
}
