import type { Building } from './types'

const STATES: Record<string, string> = {
  NSW: '新南威尔士州（NSW）', VIC: '维多利亚州（VIC）', QLD: '昆士兰州（QLD）',
  SA: '南澳大利亚州（SA）', WA: '西澳大利亚州（WA）', TAS: '塔斯马尼亚州（TAS）',
  ACT: '首都领地（ACT）', NT: '北领地（NT）',
}
const TIMEZONE_REGIONS: Record<string, string> = {
  'Australia/Sydney': STATES.NSW, 'Australia/Melbourne': STATES.VIC,
  'Australia/Brisbane': STATES.QLD, 'Australia/Adelaide': STATES.SA,
  'Australia/Perth': STATES.WA, 'Australia/Hobart': STATES.TAS,
  'Australia/Darwin': STATES.NT,
}

export function assignedRegions(buildings: readonly Building[]): string[] {
  return [...new Set(buildings.map((building) => {
    const state = building.address.toUpperCase().match(/\b(NSW|VIC|QLD|SA|WA|TAS|ACT|NT)\b/)?.[1]
    return state ? STATES[state] : TIMEZONE_REGIONS[building.timezone ?? ''] || building.address || building.name
  }))].sort((left, right) => left.localeCompare(right, 'zh-CN'))
}
