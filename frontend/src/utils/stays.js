// API prices can be decimal strings. Sort a copy so booking choices retain API order.
export function sortStays(stays, order) {
  const sorted = [...stays]
  if (order === 'low' || order === 'high') {
    const direction = order === 'low' ? 1 : -1
    sorted.sort((a, b) => direction * (Number(a.stay_price_usd) - Number(b.stay_price_usd)))
  }
  return sorted
}
