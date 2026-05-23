// Skill description parsing — extract the args hint and any "Requires …"
// clause from the leading prose of a skill description.

export function parseArgs(desc) {
  if (!desc) return ''
  const m = desc.match(/^`([^`]+)`/)
  return m ? m[1] : ''
}

export function parseRequires(desc) {
  if (!desc) return ''
  const m = desc.match(/Requires[^.]+\./)
  return m ? m[0] : ''
}
