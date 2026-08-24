import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/** Shown until an org sets its own name. Deliberately generic — the product
 *  ships unbranded and every tenant supplies its own name and logo. */
export const DEFAULT_ORG_NAME = 'Workspace'

interface BrandingState {
  orgName: string
  /** Logo for dark theme (shown on dark backgrounds) */
  orgLogoDark: string | null
  /** Logo for light theme (shown on light backgrounds) */
  orgLogoLight: string | null
  setOrgName: (name: string) => void
  setOrgLogoDark: (url: string | null) => void
  setOrgLogoLight: (url: string | null) => void
  resetAll: () => void
}

export const useBrandingStore = create<BrandingState>()(
  persist(
    (set) => ({
      orgName: DEFAULT_ORG_NAME,
      orgLogoDark: null,
      orgLogoLight: null,
      setOrgName: (name) => set({ orgName: name }),
      setOrgLogoDark: (url) => set({ orgLogoDark: url }),
      setOrgLogoLight: (url) => set({ orgLogoLight: url }),
      resetAll: () => set({ orgName: DEFAULT_ORG_NAME, orgLogoDark: null, orgLogoLight: null }),
    }),
    {
      name: 'ff-branding',
      version: 3,
      // v3 drops the FreeFrame default. Only the stale default is rewritten —
      // an org that already picked its own name or logos keeps them, so the
      // de-branding is invisible to anyone who had customised.
      migrate: (persisted) => {
        const prev = persisted as Partial<BrandingState> | undefined
        return {
          orgName:
            prev?.orgName && prev.orgName !== 'FreeFrame'
              ? prev.orgName
              : DEFAULT_ORG_NAME,
          orgLogoDark: prev?.orgLogoDark ?? null,
          orgLogoLight: prev?.orgLogoLight ?? null,
        }
      },
    },
  ),
)
