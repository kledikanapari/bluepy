#!/usr/bin/env node
// Local development server for ear (web).
//
// Serves the `res/` folder on http://localhost:<port> (localhost is a secure
// context, which Web Serial requires) and reproduces the URL rewrite used in
// production: `/MainControl_<name>` -> `res/MainControl/MainControl_<name>.html`.
// A plain static server cannot do that rewrite, so connecting a device would
// otherwise land on a 404 page.
//
// Usage: node server.js [--port 8080] [--host 127.0.0.1]   (or: npm start)

const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "res");

function argValue(name, fallback) {
    const i = process.argv.indexOf(name);
    return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const PORT = parseInt(argValue("--port", process.env.PORT || "8080"), 10);
const HOST = argValue("--host", process.env.HOST || "127.0.0.1");

const MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".otf": "font/otf",
    ".ttf": "font/ttf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
};

function resolvePath(urlPath) {
    let decoded;
    try {
        decoded = decodeURIComponent(urlPath);
    } catch (e) {
        return null;
    }
    if (decoded === "/" || decoded === "") {
        decoded = "/index.html";
    }
    // Production rewrite: /MainControl_one -> /MainControl/MainControl_one.html
    const rewrite = decoded.match(/^\/(MainControl_[A-Za-z0-9_]+)(\.html)?$/);
    if (rewrite) {
        decoded = "/MainControl/" + rewrite[1] + ".html";
    }
    const filePath = path.normalize(path.join(ROOT, decoded));
    if (filePath !== ROOT && !filePath.startsWith(ROOT + path.sep)) {
        return null;
    }
    return filePath;
}

const server = http.createServer((req, res) => {
    if (req.method !== "GET" && req.method !== "HEAD") {
        res.writeHead(405, { Allow: "GET, HEAD" });
        res.end();
        return;
    }
    const urlPath = new URL(req.url, "http://localhost").pathname;
    const filePath = resolvePath(urlPath);
    if (!filePath) {
        res.writeHead(400);
        res.end("Bad request");
        return;
    }
    fs.stat(filePath, (err, stats) => {
        if (err || !stats.isFile()) {
            res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
            res.end("Not found: " + urlPath);
            console.warn("404 " + urlPath);
            return;
        }
        res.writeHead(200, {
            "Content-Type": MIME_TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream",
            "Content-Length": stats.size,
            "Cache-Control": "no-cache",
        });
        if (req.method === "HEAD") {
            res.end();
            return;
        }
        fs.createReadStream(filePath).pipe(res);
    });
});

server.listen(PORT, HOST, () => {
    const shownHost = HOST === "0.0.0.0" || HOST === "127.0.0.1" ? "localhost" : HOST;
    console.log(`ear (web) running at http://${shownHost}:${PORT}/`);
    console.log("Open it in a Chromium-based browser (Chrome, Edge, Brave) version 117+.");
});
