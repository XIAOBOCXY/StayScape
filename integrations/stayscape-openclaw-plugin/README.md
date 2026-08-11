# StayScape OpenClaw Tool Plugin

This is the only business Tool Plugin installed in the single `stayscape-main`
Agent. It calls three fixed FastAPI routes over the private Docker network and
never exposes SQL, shell, arbitrary HTTP, inventory mutation, price mutation or
product publication.

Build and validate with a pinned OpenClaw CLI:

```bash
npm install
npm run plugin:build
npm run plugin:validate
```

The `token`, `hotelId` and Feishu sender allowlist are runtime configuration;
no credential belongs in this package or in the browser.
