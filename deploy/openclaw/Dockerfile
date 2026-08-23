ARG OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:2026.6.9-slim
ARG OPENCLAW_RUNTIME_VERSION=2026.6.9
ARG OPENCLAW_INSTALL_METHOD=image
ARG OPENCLAW_QWEN_PROVIDER_VERSION=2026.6.9
ARG OPENCLAW_FEISHU_VERSION=2026.6.9
FROM ${OPENCLAW_IMAGE}

ARG OPENCLAW_RUNTIME_VERSION=2026.6.9
ARG OPENCLAW_INSTALL_METHOD=image
ARG OPENCLAW_QWEN_PROVIDER_VERSION=2026.6.9
ARG OPENCLAW_FEISHU_VERSION=2026.6.9

USER root

# The normal production path uses the official OpenClaw image.  On hosts that
# cannot reach GHCR/Docker Hub package images, the official npm package can
# bootstrap the same pinned Gateway runtime on a Node 22 base image.
RUN case "$OPENCLAW_INSTALL_METHOD" in \
      image) ;; \
      npm) node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major < 22 || (major === 22 && minor < 19)) { console.error("OpenClaw requires Node >= 22.19"); process.exit(1); }' \
        && npm install -g --omit=dev --no-audit --no-fund "openclaw@${OPENCLAW_RUNTIME_VERSION}" \
        && rm -rf /app \
        && ln -s /usr/local/lib/node_modules/openclaw /app ;; \
      *) echo "OPENCLAW_INSTALL_METHOD must be image or npm" >&2; exit 2 ;; \
    esac
WORKDIR /opt/stayscape/openclaw-plugin

# The base image is the official OpenClaw image.  The plugin is installed as a
# normal Node package so its runtime dependency (typebox) is present after a
# container rebuild.
COPY integrations/stayscape-openclaw-plugin/package.json ./package.json
COPY integrations/stayscape-openclaw-plugin/dist ./dist
COPY integrations/stayscape-openclaw-plugin/openclaw.plugin.json ./openclaw.plugin.json
COPY integrations/stayscape-openclaw-plugin/README.md ./README.md
RUN npm install --omit=dev --ignore-scripts --no-audit --no-fund --legacy-peer-deps

# The official image owns the OpenClaw runtime package.  Link its SDK into the
# plugin package when the image layout exposes it there; this keeps the plugin
# compatible with both the current official image layout and its loader's peer
# dependency contract without installing a second Gateway runtime.
RUN mkdir -p /opt/stayscape/openclaw-plugin/node_modules \
    && if [ -d /app/node_modules/openclaw ] && [ ! -e /opt/stayscape/openclaw-plugin/node_modules/openclaw ]; then ln -s /app/node_modules/openclaw /opt/stayscape/openclaw-plugin/node_modules/openclaw; fi \
    && if [ -d /usr/local/lib/node_modules/openclaw ] && [ ! -e /opt/stayscape/openclaw-plugin/node_modules/openclaw ]; then ln -s /usr/local/lib/node_modules/openclaw /opt/stayscape/openclaw-plugin/node_modules/openclaw; fi

# Official OpenClaw external plugins. Versions are pinned to the Gateway
# runtime so a rebuild cannot silently change the provider/channel contract.
# QWEN_API_KEY is injected at runtime by Compose; it is never baked here.
RUN mkdir -p /opt/stayscape/runtime-plugins \
    && npm install --prefix /opt/stayscape/runtime-plugins --omit=dev --omit=peer --no-audit --no-fund \
      "@openclaw/qwen-provider@${OPENCLAW_QWEN_PROVIDER_VERSION}" \
      "@openclaw/feishu@${OPENCLAW_FEISHU_VERSION}" \
    && mkdir -p /opt/stayscape/runtime-plugins/node_modules \
    && if [ -d /app/node_modules/openclaw ] && [ ! -e /opt/stayscape/runtime-plugins/node_modules/openclaw ]; then ln -s /app/node_modules/openclaw /opt/stayscape/runtime-plugins/node_modules/openclaw; fi \
    && if [ -d /usr/local/lib/node_modules/openclaw ] && [ ! -e /opt/stayscape/runtime-plugins/node_modules/openclaw ]; then ln -s /usr/local/lib/node_modules/openclaw /opt/stayscape/runtime-plugins/node_modules/openclaw; fi

COPY skills /opt/stayscape/skills
COPY deploy/openclaw/entrypoint.sh /opt/stayscape/entrypoint.sh
RUN chmod +x /opt/stayscape/entrypoint.sh \
    && mkdir -p /home/node/.openclaw/workspace/skills \
    && chown -R node:node /opt/stayscape /home/node/.openclaw

USER node
WORKDIR /app
ENTRYPOINT ["/opt/stayscape/entrypoint.sh"]
