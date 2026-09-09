import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>
const base = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

export const BuildingIcon = (props: IconProps) => <svg viewBox="0 0 24 24" aria-hidden="true" {...props}><path {...base} d="M4 21V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v16M8 7h2m3 0h1M8 11h2m3 0h1M8 15h2m3 0h1M2 21h20m-10 0v-3H9v3" /></svg>
export const OrdersIcon = (props: IconProps) => <svg viewBox="0 0 24 24" aria-hidden="true" {...props}><path {...base} d="M7 3h10a2 2 0 0 1 2 2v16l-3-2-4 2-4-2-3 2V5a2 2 0 0 1 2-2Zm2 5h6m-6 4h6" /></svg>
export const WrenchIcon = (props: IconProps) => <svg viewBox="0 0 24 24" aria-hidden="true" {...props}><path {...base} d="m14.5 6.5 3-3a5 5 0 0 1-6 6L5 16a2.1 2.1 0 0 0 3 3l6.5-6.5a5 5 0 0 0 6-6l-3 3-3-1-1-3Z" /></svg>
export const UsersIcon = (props: IconProps) => <svg viewBox="0 0 24 24" aria-hidden="true" {...props}><path {...base} d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m7-10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></svg>
export const SparkIcon = (props: IconProps) => <svg viewBox="0 0 24 24" aria-hidden="true" {...props}><path {...base} d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Zm7 13 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" /></svg>
export const ChevronIcon = (props: IconProps) => <svg viewBox="0 0 24 24" aria-hidden="true" {...props}><path {...base} d="m9 18 6-6-6-6" /></svg>
export const LogoutIcon = (props: IconProps) => <svg viewBox="0 0 24 24" aria-hidden="true" {...props}><path {...base} d="M10 17l5-5-5-5m5 5H3m11-9h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" /></svg>
export const SearchIcon = (props: IconProps) => <svg viewBox="0 0 24 24" aria-hidden="true" {...props}><circle {...base} cx="11" cy="11" r="7" /><path {...base} d="m20 20-4-4" /></svg>
export const BellIcon = (props: IconProps) => <svg viewBox="0 0 24 24" aria-hidden="true" {...props}><path {...base} d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 13h4" /></svg>
