# The offsim render brain, portable: any machine or cloud runner with Docker can produce the films.
#   docker build -t offsim .
#   docker run --rm -v "$PWD/out:/app/out" -v "$PWD/data:/app/data" -e MUSE_AI_KEY offsim \
#       python -m offsim film offsim/papers/demo-oslofjord-supply/storyboard.yaml --muse unlisted
# CPU only (SwiftShader); a GPU host renders faster but is not required.
FROM python:3.12-slim
RUN apt-get update -q && apt-get install -y -q --no-install-recommends \
      ffmpeg curl gnupg ca-certificates unzip git \
      libegl1 libgl1 libfontconfig1 fonts-dejavu-core gh \
      libpango1.0-dev dvisvgm texlive-latex-base texlive-latex-extra texlive-fonts-recommended \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y -q --no-install-recommends google-chrome-stable nodejs \
    && rm -rf /var/lib/apt/lists/*
ENV HYPERFRAMES_BROWSER_PATH=/usr/bin/google-chrome CHROME=/usr/bin/google-chrome
WORKDIR /app
COPY requirements*.txt ./
# every extra the machine uses: one environment for CI, Codespaces and any agent (see docs/MACHINE.md)
RUN pip install --no-cache-dir -r requirements-motion.txt -r requirements-render.txt -r requirements-weather.txt \
      -r requirements-engines.txt -r requirements-gis.txt -r requirements-physics.txt -r requirements-graphics.txt \
      -r requirements-intake.txt -r requirements-cad.txt pytest-timeout mcp \
    && pip install --no-cache-dir --force-reinstall --no-deps cadquery-ocp==7.9.3.1.1 \
    && python -c "import skia, cadquery, OCP, openclsim, pyvrp"
RUN python -m playwright install-deps chromium || true
COPY offsim/render_deck/package*.json offsim/render_deck/
COPY offsim/motion/package*.json offsim/motion/
RUN npm ci --prefix offsim/render_deck && (npm ci --prefix offsim/motion || npm install --prefix offsim/motion)
COPY . .
CMD ["python", "-m", "offsim", "--help"]
