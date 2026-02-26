FROM python:3.12-slim

# ── Install Chrome + dependencies ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg2 unzip curl \
    # Chrome deps
    fonts-liberation libappindicator3-1 libasound2 libatk-bridge2.0-0 \
    libatk1.0-0 libcups2 libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 \
    libnspr4 libnss3 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 \
    xdg-utils libxss1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome stable
RUN wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && dpkg -i /tmp/chrome.deb || apt-get -fy install \
    && rm /tmp/chrome.deb

# ── App setup ──
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data dirs
RUN mkdir -p data/tenders data/pdfs logs

# Default: run the web dashboard
EXPOSE 5050
CMD ["python", "web.py"]
