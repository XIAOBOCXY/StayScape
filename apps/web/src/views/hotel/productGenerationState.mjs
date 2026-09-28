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
