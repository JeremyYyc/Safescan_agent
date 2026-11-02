import { assignedRegions } from './regions'

describe('assigned regions', () => {
  it('deduplicates buildings across all five states and prioritizes explicit addresses', () => {
    const timezones = ['Australia/Sydney', 'Australia/Melbourne', 'Australia/Brisbane', 'Australia/Adelaide', 'Australia/Perth']
    const buildings = timezones.flatMap((timezone, index) => Array.from({ length: 35 }, (_, copy) => ({ id: `${index}-${copy}`, name: 'Building', address: 'Address withheld', timezone })))
    expect(assignedRegions(buildings)).toHaveLength(5)
    expect(assignedRegions([{ id: 'act', name: 'Canberra', address: 'Canberra ACT', timezone: 'Australia/Sydney' }])).toEqual(['首都领地（ACT）'])
  })
})
