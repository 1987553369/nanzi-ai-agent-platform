export const EMBED_PROTOCOL_VERSION = 1

export const createEmbedHandshakeNonce = (): string => {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
}

const parseWebOrigin = (value: string): string | null => {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null
  } catch {
    return null
  }
}

export const resolveTrustedParentOrigin = (
  referrer: string,
  configuredOrigin: string | null,
): string | null => {
  const referrerOrigin = parseWebOrigin(referrer)
  if (!referrerOrigin) return null

  if (configuredOrigin) {
    const normalizedConfiguredOrigin = parseWebOrigin(configuredOrigin)
    if (!normalizedConfiguredOrigin || normalizedConfiguredOrigin !== referrerOrigin) return null
  }

  return referrerOrigin
}

export const isTrustedEmbedMessage = (
  event: MessageEvent,
  expectedSource: Window | null,
  expectedOrigin: string,
  handshakeNonce: string,
): boolean => {
  const data = event.data
  return Boolean(
    expectedSource &&
      event.source === expectedSource &&
      event.origin === expectedOrigin &&
      data &&
      typeof data === 'object' &&
      data.protocol_version === EMBED_PROTOCOL_VERSION &&
      data.handshake_nonce === handshakeNonce,
  )
}

export const createEmbedMessage = <T extends Record<string, unknown>>(
  payload: T,
  handshakeNonce: string,
): T & { protocol_version: number; handshake_nonce: string } => ({
  ...payload,
  protocol_version: EMBED_PROTOCOL_VERSION,
  handshake_nonce: handshakeNonce,
})
