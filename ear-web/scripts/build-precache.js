#!/usr/bin/env node
// Writes res/precache.json: every file the installed app needs to work offline.
// The service worker downloads them all when the app is installed.
// Re-run (npm run build:precache) after adding, removing or renaming files in res/.

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "res");
const SKIP = new Set(["sw.js", "precache.json"]);

function walk(dir) {
    let files = [];
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            files = files.concat(walk(full));
        } else if (!entry.name.startsWith(".")) {
            files.push(full);
        }
    }
    return files;
}

const urls = walk(ROOT)
    .map(file => "/" + path.relative(ROOT, file).split(path.sep).join("/"))
    .filter(url => !SKIP.has(url.slice(1)))
    .sort();

fs.writeFileSync(path.join(ROOT, "precache.json"), JSON.stringify(urls, null, 1) + "\n");
console.log(`res/precache.json: ${urls.length} files`);
