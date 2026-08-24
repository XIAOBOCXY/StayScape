const INTERNAL_LANGUAGE = /库存|房量|成本|售价|毛利|规则引擎|容量约束|真实容量|实时余量|固定场次|可直接销售|确定性|履约|供给|产品草稿|酒店服务|实时计算|校验|Demo|Mock|Skill|Agent|trace[_ -]?id/i

export function publicTravelCopy(value: unknown, fallback = ''): string {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text) return fallback
  const segments = text.match(/[^。！？!?]+[。！？!?]?/g) || []
  const safe = segments.filter((segment) => !INTERNAL_LANGUAGE.test(segment)).join('').trim()
  return safe.length >= 6 ? safe : fallback
}
