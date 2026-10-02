// node fe_runner.js <app.js> <hook> <argsJSON> : evaluates a frontend hook headlessly.
const fs = require("fs"), path = require("path");
global.window = {};
eval(fs.readFileSync(path.join(__dirname, "static/ui.js"), "utf8"));
eval(fs.readFileSync(process.argv[2], "utf8"));
window.AppUI.init();
console.log(JSON.stringify(window.AppUI.hooks[process.argv[3]](...JSON.parse(process.argv[4]))));
