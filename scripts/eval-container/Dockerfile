FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392

# Нужна архитектура Docker runtime: эмуляция не доказывает работу seccomp.
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global \
    PATH=/usr/local/share/npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/home/agent \
    SHELL=/bin/bash

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash bubblewrap ca-certificates git python3 socat \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash agent \
    && npm install --global --no-audit --no-fund @anthropic-ai/claude-code@2.1.286 \
    && python3 -c 'import pathlib, platform; p = pathlib.Path("/usr/local/share/npm-global/bin/claude").resolve(); h = p.read_bytes()[:20]; assert h[:6] == b"\x7fELF\x02\x01", "Claude must be native ELF"; assert int.from_bytes(h[18:20], "little") == {"x86_64": 62, "aarch64": 183}[platform.machine()], "Claude ELF architecture mismatch"' \
    && test "$(claude --version)" = '2.1.286 (Claude Code)' \
    && python3 -c 'import re, subprocess; v = re.match(r"git version (\d+)\.(\d+)", subprocess.check_output(["git", "--version"], text=True)); assert v and tuple(map(int, v.groups())) >= (2, 31), "Git >= 2.31 required"'

# Контекст ограничен тестовой средой: настройки хоста и секреты в образ не попадают.
COPY preflight.py /usr/local/lib/claude-eval/preflight.py
COPY bwrap-cap-probe.py /usr/local/bin/bwrap-cap-probe
COPY keep-cli.sh /usr/local/bin/claude-eval-keep
RUN chmod 755 /usr/local/bin/bwrap-cap-probe /usr/local/bin/claude-eval-keep

WORKDIR /workspace
CMD ["python3", "/usr/local/lib/claude-eval/preflight.py"]
