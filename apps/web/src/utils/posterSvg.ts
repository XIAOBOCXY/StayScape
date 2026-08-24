export function posterSvgDataUri(svg?: string | null): string {
  const source = String(svg || "").trim()
  if (!/^<svg[\s>]/i.test(source)) return ""
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(source)
}
