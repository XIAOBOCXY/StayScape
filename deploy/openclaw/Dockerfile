ARG OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:2026.6.6
FROM ${OPENCLAW_IMAGE}

USER root
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

COPY skills /opt/stayscape/skills
COPY deploy/openclaw/entrypoint.sh /opt/stayscape/entrypoint.sh
RUN chmod +x /opt/stayscape/entrypoint.sh \
    && mkdir -p /home/node/.openclaw/workspace/skills \
    && chown -R node:node /opt/stayscape /home/node/.openclaw

USER node
WORKDIR /app
ENTRYPOINT ["/opt/stayscape/entrypoint.sh"]
