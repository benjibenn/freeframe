/** What to show for a user everywhere in the app: their admin-set nickname
 *  when there is one, else their account name, else their email. */
export function displayName(user?: { nickname?: string | null; name?: string | null; email?: string | null } | null): string {
  if (!user) return ''
  return user.nickname || user.name || user.email || ''
}
