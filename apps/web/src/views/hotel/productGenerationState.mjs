export function primaryFromCandidate(candidate) {
  const product = candidate.raw?.product || {}
  return { ...product, product_id: candidate.product_id, product_name: candidate.name, price: candidate.price, crowd: product.target_crowd || product.crowd, crowd_label: candidate.crowd_label, party_size: candidate.party, target_date: candidate.date, max_sellable: candidate.quantity }
}

export function promoteCandidate(primary, candidates, key) {
  const selected = candidates.find((item) => item.key === key)
  if (!selected) return { primary, candidates }
  const outgoing = {
    key: `primary-${Date.now()}`, source: 'primary-snapshot', product_id: primary.product_id,
    name: primary.product_name || '当前主推荐', price: primary.price || '',
    crowd_label: primary.crowd_label || '', party: primary.party_size || '',
    date: primary.target_date || '', quantity: primary.max_sellable || '',
    experiences: (primary.experiences || []).map((item) => String(item.name || '')).filter(Boolean),
    raw: { product: primary },
  }
  return { primary: primaryFromCandidate(selected), candidates: [...candidates.filter((item) => item.key !== key), outgoing] }
}

export function validationChangeNote(validationError, fallback = '') {
  const message = String(validationError?.message || '').trim()
  if (!message) return fallback
  const dates = Array.isArray(validationError?.available_dates)
    ? validationError.available_dates.map((item) => String(item || '')).filter(Boolean)
    : []
  return dates.length ? `${message}；可选日期：${dates.join('、')}` : message
}

export function prepareAdvisorResponse(currentAdvisor, previousPrimary, nextAdvisor) {
  const validationNote = validationChangeNote(nextAdvisor?.validation_error)
  const primary = nextAdvisor?.primary || null
  if (!validationNote || primary || !previousPrimary) {
    return { advisor: nextAdvisor, primary, validationNote }
  }

  const nextJudgement = nextAdvisor?.judgement || {}
  const oldJudgement = currentAdvisor?.judgement || {}
  const hasNewDirections = Array.isArray(nextJudgement.plans) && nextJudgement.plans.length > 0
  return {
    advisor: {
      ...(currentAdvisor || {}),
      ...(nextAdvisor || {}),
      primary: previousPrimary,
      judgement: hasNewDirections ? nextJudgement : oldJudgement,
    },
    primary: previousPrimary,
    validationNote,
  }
}

function asPercent(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return ''
  return number <= 1 ? Number((number * 100).toFixed(1)) : number
}

function resourceWindow(row) {
  const start = String(row?.start_time || '').slice(0, 5)
  const end = String(row?.end_time || '').slice(0, 5)
  return start && end ? `${start}–${end}` : ''
}

export function primaryFromRefinedProduct(product, previousPrimary = {}) {
  const rows = Array.isArray(product?.resources) ? product.resources : []
  const mapRow = (row) => ({
    id: row.resource_id || row.id,
    name: row.resource_name || '',
    address: row.address || '',
    window: resourceWindow(row),
    quantity: row.quantity_per_package,
    settlement_price: row.unit_cost,
  })
  const room = rows.find((row) => row.resource_type === 'ROOM')
  const experiences = rows.filter((row) => row.resource_type === 'PARTNER_RESOURCE').map(mapRow)
  const services = rows.filter((row) => row.resource_type === 'HOTEL_SERVICE').map(mapRow)
  return {
    ...previousPrimary,
    product_id: product?.id || previousPrimary.product_id,
    product_name: product?.product_name || previousPrimary.product_name,
    target_date: product?.target_date || previousPrimary.target_date,
    crowd: product?.target_crowd || previousPrimary.crowd,
    party_size: product?.party_size ?? previousPrimary.party_size,
    room_type: room?.resource_name || previousPrimary.room_type,
    experiences,
    services,
    price: product?.suggested_price ?? previousPrimary.price,
    cost: product?.unit_cost ?? previousPrimary.cost,
    floor_price: product?.minimum_allowed_price ?? previousPrimary.floor_price,
    max_sellable: product?.sale_quantity ?? previousPrimary.max_sellable,
    margin: asPercent(product?.gross_margin ?? previousPrimary.margin),
    itinerary_days: Array.isArray(product?.day_plan) && product.day_plan.length ? product.day_plan : previousPrimary.itinerary_days,
    route_plan: Array.isArray(product?.route_plan) && product.route_plan.length ? product.route_plan : previousPrimary.route_plan,
  }
}
