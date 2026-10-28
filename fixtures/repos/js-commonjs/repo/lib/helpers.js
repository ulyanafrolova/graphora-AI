const util = require("util");

function helper(x) {
  return util.inspect(x);
}

module.exports = { helper };
