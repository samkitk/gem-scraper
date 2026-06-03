# GeM Scraper Deployment & Updates Guide

This repository contains the Selenium scraper for Event/Seminar/Workshop tenders on the Indian Government e-Marketplace (GeM) portal, along with a Flask web dashboard.

---

## 🚀 How to Deploy a New Version (Step-by-Step)

Follow these steps when you make changes to the code and want to deploy the updates to your TrueNAS server:

### Step 1: Push Changes to GitHub
Commit and push your local changes to the `master` branch:
```bash
git add .
git commit -m "feat: your feature description"
git push origin master
```

### Step 2: Create and Push a Version Tag
To tag a release and build semantic docker tags (e.g., `1.0.1` and `latest`), run:
```bash
# 1. Create a version tag (always format as vX.Y.Z)
git tag v1.0.1

# 2. Push the tag to GitHub
git push origin v1.0.1
```
*Note: GitHub Actions will automatically start building the Docker image. It will build and push the following tags to `ghcr.io`:*
* `ghcr.io/samkitk/gem-scraper:1.0.1` *(the leading 'v' is stripped automatically)*
* `ghcr.io/samkitk/gem-scraper:1.0`
* `ghcr.io/samkitk/gem-scraper:latest`

---

## 🛠 How to Update TrueNAS SCALE

Depending on how you have configured your image in `app.yaml`:

### Option A: If using Explicit Version Tags (Recommended)
If your `app.yaml` uses a version number:
```yaml
image: ghcr.io/samkitk/gem-scraper:1.0.0
```
1. Open the TrueNAS SCALE UI, go to **Apps** -> **Installed Apps**.
2. Click **Edit** on `gem-scraper`.
3. Change the image tag to the new version (e.g., `1.0.1`):
   ```yaml
   image: ghcr.io/samkitk/gem-scraper:1.0.1
   ```
4. Click **Save**. TrueNAS will recognize the tag change, pull the new image from GHCR, and restart the containers automatically.

### Option B: If using the `:latest` Tag
If your `app.yaml` uses:
```yaml
image: ghcr.io/samkitk/gem-scraper:latest
```
Docker caches the image locally. Even if you push version `2.0.0` to GitHub, TrueNAS won't download it automatically because the tag text `:latest` did not change. To force TrueNAS to download the new update:

#### 1. Via TrueNAS UI (Always Pull option)
* In the App Edit screen, look for **Image Pull Policy** and set it to **Always**.
* Click **Save**. Now, simply restarting/re-saving the app will always check and download any new `:latest` image from GHCR.

#### 2. Via SSH (Manual Pull)
* SSH into TrueNAS and run:
  ```bash
  docker compose -f /path/to/app.yaml pull
  docker compose -f /path/to/app.yaml up -d
  ```
  *(Or if running plain docker: `docker pull ghcr.io/samkitk/gem-scraper:latest`)*
