# Install guide

A step-by-step walkthrough for setting up flickrfinder on a fresh machine. Aimed at people who can open a Terminal but aren't full-time developers.

If anything goes wrong, jump to **[Troubleshooting](#troubleshooting)** at the bottom.

## What you'll end up with

A web app running on your computer (and reachable from other devices on your home network if you want) that lets you search your Flickr photos by EXIF data — focal length, ISO, camera, lens, anything Flickr exposes.

## Before you start

You need four things installed on your computer:

| Tool | What it does | Installer |
|---|---|---|
| **git** | Downloads the source code | macOS: `xcode-select --install` · Linux: `sudo apt install git` or `sudo dnf install git` |
| **Python 3.11+** | Runs the backend + CLI | macOS: comes with the OS, or `brew install python` · Linux: `sudo apt install python3` |
| **uv** | Installs the Python packages | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Bun** | Builds the web UI | `curl -fsSL https://bun.sh/install \| bash` |

Run each installer in your Terminal. After they finish, close and reopen Terminal so the new commands are recognised.

To check everything is installed, type these one at a time and confirm a version number prints:

```bash
git --version
python3 --version
uv --version
bun --version
```

> **Windows users:** the easiest path is WSL (Windows Subsystem for Linux). Install WSL, then follow the Linux instructions inside the WSL terminal.

## Step 1 — Get a Flickr API key

The app talks to Flickr on your behalf; for that, Flickr needs to know who's asking.

1. Open https://www.flickr.com/services/apps/create/ in your browser (sign in if needed).
2. Click **Apply for a Non-Commercial Key** and fill in the short form (the app's name and a one-line description are enough).
3. Flickr will show you two long strings: a **Key** and a **Secret**. Copy both somewhere safe for a minute — you'll paste them into a file in Step 4.

These two strings act like a username and password for the app. Don't share them publicly.

## Step 2 — Download the code

In Terminal, pick a folder to put it in (this command puts it in your home folder):

```bash
cd ~
git clone <repo-url>
cd flickrfinder
```

Replace `<repo-url>` with the address from the project's GitHub page (looks like `https://github.com/<owner>/<repo>.git`).

## Step 3 — Create the local data folder

The app stores your photo metadata and any downloaded originals in a `data/` folder it makes for itself. This step just creates it ahead of time:

```bash
mkdir -p data
```

## Step 4 — Add your Flickr key and secret

Make a configuration file by copying the example:

```bash
cp .env.example .env
```

Then open `.env` in any text editor (TextEdit, Nano, VS Code — anything). It looks like:

```
FLICKR_API_KEY=your_key_here
FLICKR_API_SECRET=your_secret_here
```

Replace `your_key_here` and `your_secret_here` with the two strings Flickr gave you in Step 1. Save the file and close it.

> The `.env` file is automatically ignored by Git — your keys won't end up published if you push the repo somewhere.

## Step 5 — Install the Python packages

```bash
uv sync
```

This downloads everything the backend needs into a `.venv/` folder. Takes 30–60 seconds the first time. You should see a list of packages installed.

## Step 6 — Build the web UI

```bash
cd web
bun install
bun run build
cd ..
```

`bun install` downloads the React + Vite packages (~80 MB). `bun run build` turns the source code into the small, fast bundle the server will hand to your browser. Together this takes about a minute.

## Step 7 — Sign into Flickr (one time)

```bash
uv run flickrfinder auth
```

The app will print a long URL. Copy it, paste it into your browser, sign into Flickr, and click **Authorize**. Flickr will show you a 9-digit code (e.g. `123-456-789`). Copy it, switch back to Terminal, paste it at the prompt, and hit Enter.

You should see `Authenticated as <yourFlickrName>`. The login is remembered — you only do this once.

## Step 8 — Confirm it can see your photos

```bash
uv run flickrfinder whoami
```

It should print your Flickr username and the total number of photos in your account. If you see that, the connection works.

## Step 9 — Pull your photo metadata into the local database

```bash
uv run flickrfinder sync
```

This goes through every photo in your account and copies the metadata (titles, dates, EXIF) into the local database. **It can take a long time** — about one second per photo, so 10,000 photos is roughly three hours.

You can leave it running in this Terminal window. If you stop it (Ctrl-C) or your computer reboots, just run the same command again — it picks up where it left off. You can also peek at progress from another Terminal window with:

```bash
uv run flickrfinder db stats
```

> No actual photos (JPEGs) are downloaded by `sync` — only the small EXIF/metadata records. Original-size images are only fetched when you click "Download original" later, and even then only one photo at a time.

## Step 10 — Start the web app

```bash
uv run flickrfinder serve
```

The Terminal will say something like `Uvicorn running on http://127.0.0.1:8765`. Leave this Terminal window open — closing it stops the server.

Open `http://127.0.0.1:8765` in your browser. You should see the search interface. While `sync` is still running in the other window, results will appear here as soon as the first batch lands; you don't have to wait for the full sync to finish.

## Step 11 (optional, macOS only) — Keep it always running

If you want the server to start automatically when you log in and stay alive in the background:

```bash
./deploy/install-launchd.sh
```

This makes the server reachable from any device on your home network at `http://<your-mac-name>.local:8765`. macOS will pop up a prompt the first time another device connects, asking you to allow incoming connections — click **Allow**.

> **Heads up:** the server has no password. Anyone on your home network can use it. That's normally fine for a home Mac, but don't run it on a network you don't trust (e.g., a coffee shop).

To stop the always-on service later:

```bash
launchctl bootout gui/$(id -u)/com.flickrfinder.server
```

## Done!

Day-to-day after this, you only ever need:

```bash
uv run flickrfinder serve     # start the web app (or skip if you did Step 11)
uv run flickrfinder sync      # pull any new Flickr photos when you want fresh data
```

## Troubleshooting

**`command not found: uv` (or `bun`, `git`, `python3`)**
The Terminal can't find the tool you just installed. Close Terminal completely and reopen it. If it still can't, the installer told you what file to edit so the command is found — re-read its output.

**Step 7 says "No saved Flickr token" after I authenticated**
The verifier code from Step 7 expired or was mistyped. Run `uv run flickrfinder logout` then `uv run flickrfinder auth` again and paste the new code faster.

**Step 9 errors with "the Flickr API service is not currently available"**
Flickr had a hiccup; just run `uv run flickrfinder sync` again. It'll skip everything already done and pick up the remaining photos.

**Web UI loads but says "No SPA built"**
You skipped Step 6. Run it (`cd web && bun install && bun run build && cd ..`) and refresh the browser.

**Port 8765 already in use**
Something else is using the port. Either stop that other thing, or pick a different port: `FLICKRFINDER_PORT=9876 uv run flickrfinder serve` and open `http://127.0.0.1:9876` instead.

**I want to start over from scratch**
Delete the `data/` folder (loses the local database and any downloaded originals — won't touch anything on Flickr), then re-run Step 9. Or `uv run flickrfinder logout` if you want to re-do the Flickr login too.
