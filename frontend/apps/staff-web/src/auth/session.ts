import type { BootstrapData, Session } from '../types'

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function isSubjectIdentifier(value: string, subjectId: string): boolean {
  return value === subjectId || UUID_PATTERN.test(value)
}

export function mergeBootstrap(session: Session, bootstrap: BootstrapData): Session {
  const bootstrapUsername = bootstrap.staff.username.trim()
  const username = bootstrapUsername && !isSubjectIdentifier(bootstrapUsername, bootstrap.staff.id)
    ? bootstrapUsername
    : session.staff.username
  const bootstrapDisplayName = bootstrap.staff.displayName.trim()
  const displayName = bootstrapDisplayName && !isSubjectIdentifier(bootstrapDisplayName, bootstrap.staff.id)
    ? bootstrapDisplayName
    : session.staff.displayName

  return {
    ...session,
    permissions: bootstrap.permissions,
    staff: {
      ...session.staff,
      ...bootstrap.staff,
      id: bootstrap.staff.id || session.staff.id,
      username: username || displayName,
      displayName: displayName || username,
      email: bootstrap.staff.email || session.staff.email,
      staffCode: bootstrap.staff.staffCode || session.staff.staffCode,
    },
  }
}
