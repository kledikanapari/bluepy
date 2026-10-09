# ear (web) [unofficial]

![Ear(web) Logo](res/icons/256x256.png)


# Compatibility
This website is compatible with the following devices:
- Nothing ear (1)
- Nothing ear (stick)
- Nothing ear (2)
- CMF Buds Pro
- CMF Buds
- Nothing Ear
- CMF Buds Pro 2


# Usage
1. Use a Chromium-based browser (Chrome, Edge, Brave, etc.) based on version 117+
2. Go to [this link](https://earweb.bttl.xyz/)

## Run locally
Requires [Node.js](https://nodejs.org/) 18+ (no `npm install` needed to run).
```
npm start
```
Then open http://localhost:8080/ in Chrome/Edge/Brave (117+), pair the earbuds with your computer first, and press **Connect**.

- Use `node server.js --port 3000` to change port.
- Use `localhost` (not the LAN IP): Web Serial only works in a secure context, and `http://localhost` counts as one.
- A plain static server (e.g. `python -m http.server`) is not enough: device pages are opened as `/MainControl_<name>`, which `server.js` maps to `res/MainControl/MainControl_<name>.html` like the production server does.
- Add `?debug=1` to a device page URL (e.g. `/MainControl_one?debug=1`) to see protocol logs in the browser console.
- Or double-click `start-windows.bat` (Windows) / `start-mac-linux.command` (macOS, Linux): it starts the server and opens the browser.

## Install as an app
ear (web) is an installable web app (PWA): once installed it has its own icon and window, and works **without the server running**, because every file is stored locally on install.

1. Start the server once (`npm start` or the launcher above) and open http://localhost:8080/ in Chrome or Edge.
2. Click **Install app** under Connect (or the install icon in the address bar).
3. Wait a few seconds so all files (~95 MB) are downloaded, then close the server.

From then on, open "ear (web)" from the Start menu / Applications / desktop like any other app. To update it, run the server again and open the app once: it fetches the new files while the server is running.

After adding, removing or renaming files in `res/`, run `npm run build:precache` and bump `CACHE_NAME` in `res/sw.js`.

## Features
 - Battery percentage                  
 - Equalizer settings with custom Equalizer and Advanced EQ toggle for compatibles devices.
 - Quick Settings (In-Ear Detection, Low Latency Mode, Firmware version), Personalized ANC toggle and Ear Tip Fit Test
 - Bass Enhance and ANC settings
 - Gestures
 - Find my Earbuds 
 - Case Battery Status LED (Ear (1) only)
 
## Development

Chart.js and the Chart.js drag-data plugin are vendored under `res/js/vendor/` (no CDN dependency). Tailwind CSS is compiled to a static stylesheet at `res/tailwind.css` instead of using the Tailwind CDN JIT compiler at runtime.

If you add new Tailwind classes to any file under `res/`, rebuild the stylesheet before committing:
```
npm install
npm run build:css
```
`npm run watch:css` will rebuild on save while developing.

## Credits and Acknowledgements
- RapidZapper for the idea and backend work
- [Bendix](https://www.mrbrickstar.de/) for the frontend work 
- [DerrenGoneDigital](https://twitter.com/DerrenDigital) for the logo

## LEGAL

This application and code is published under the GNU General Public License v3.0. (https://github.com/radiance-project/ear-pc/blob/main/LICENSE)

Nothing Technology Limited or any of its affiliates, subsidiaries, or related entities (collectively, “Nothing Technology”) is a valid licensee and can use this app for any purpose, including commercial purposes, without compensation to the developers of this app. Nothing Technology is not required to comply with the terms of the GNU General Public License v3.0.

This app is developed by RapidZapper and Bendix and is not affiliated with, sponsored by, or endorsed by Nothing Technology. The developers of this app take no responsibility for the accuracy or completeness of the content and materials provided in this app. The content and materials contained in this app, including but not limited to text, graphics, logos, images, and audio/visual materials, are proprietary to Nothing Technology Limited, 80 Cheapside, London EC2V 6EE and are protected by copyright, trademark, and other intellectual property laws. These materials may not be used without the express written permission of Nothing Technology. Nothing Technology reserves all rights.
