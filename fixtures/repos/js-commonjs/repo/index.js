const path = require("path");
const helpers = require("./lib/helpers");
const config = require("~/config");
const tpl = require(`./lib/template`);
const name = process.env.PLUGIN;
const plugin = require(name);
const lodash = require("lodash");
const test = require("test");
const nodeTest = require("node:test");
const internal = require("#internal");
const remote = require("https://cdn.example.com/x.js");
const outside = require("../../outside");

async function loadPage(n) {
  return import(`./pages/${n}.js`);
}

module.exports = { path, helpers, config, tpl, plugin, lodash, test, nodeTest, internal, remote, outside, loadPage };
