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
