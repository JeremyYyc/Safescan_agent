export const CITY_LABELS: Record<string, string> = {
  sydney: '悉尼', melbourne: '墨尔本', brisbane: '布里斯班',
  adelaide: '阿德莱德', perth: '珀斯', canberra: '堪培拉', hobart: '霍巴特', darwin: '达尔文',
}
export const STAFF_CITIES: Record<string, string> = {
  LC001: 'sydney', LC002: 'melbourne', LC003: 'brisbane', LC004: 'adelaide',
  PM001: 'sydney', PM002: 'melbourne', PM003: 'brisbane', PM004: 'adelaide',
  MT001: 'sydney', MT002: 'brisbane', MT003: 'melbourne',
  LC005: 'perth', PM005: 'perth', MT004: 'adelaide', MT005: 'perth',
}
export function cityLabel(city?: string, admin = false) {
  return city ? CITY_LABELS[city] ?? city : admin ? '全部城市' : '待设置'
}
