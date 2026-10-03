// Presentation only. Scores/differences are calculated with Decimal on the server.
export function marks(value: string) {
  return value.replace(/\.00$/, "");
}

export function difference(value: string) {
  return `${Number(value) > 0 ? "+" : ""}${marks(value)}`;
}
