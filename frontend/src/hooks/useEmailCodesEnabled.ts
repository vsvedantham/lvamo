import { useEffect, useState } from 'react'
import { emailCodesEnabled } from '../api/platform'

/** null while loading, then whether this vertical asks for emailed codes.
 * If the setting can't be read, codes count as off: the backend still
 * insists on a code when they're on, so nothing is skipped. */
export function useEmailCodesEnabled(vertical: string): boolean | null {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  useEffect(() => {
    let live = true
    emailCodesEnabled(vertical).then(v => { if (live) setEnabled(v) })
    return () => { live = false }
  }, [vertical])
  return enabled
}
