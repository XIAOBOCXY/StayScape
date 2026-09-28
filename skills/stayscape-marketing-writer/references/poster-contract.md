# Poster contract

The poster brief has a factual visual layer and a server-rendered text layer.

- Visual layer: named formal experience, supplied room cue, crowd, time,
  weather, and an explicit text-safe area.
- Text layer: only validated title, short subtitle, formal inclusions, selling
  price, sellable quantity, crowd, and CTA.
- Never create readable text, logos, QR codes, tickets, prices, fake reviews,
  or non-existent facilities in the image layer.
- If image generation is unavailable, return poster_style and visual_brief as
  an honest planning fallback. The product remains valid; only the image is
  absent.
