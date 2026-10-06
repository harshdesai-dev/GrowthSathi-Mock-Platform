export function isoToIstDateTimeLocal(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const valueFor = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "00";
  return `${valueFor("year")}-${valueFor("month")}-${valueFor("day")}T${valueFor("hour")}:${valueFor("minute")}:${valueFor("second")}`;
}

export function rupeesToPaise(value: string): number | null {
  const match = value.trim().match(/^(\d+)(?:\.(\d{1,2}))?$/);
  if (!match) return null;
  const paise =
    BigInt(match[1]!) * 100n + BigInt((match[2] ?? "").padEnd(2, "0"));
  if (paise < 1n || paise > 2_147_483_647n) return null;
  return Number(paise);
}


/** Convert a wall-clock IST input to an offset-aware instant for the UTC API. */
export function istDateTimeLocalToIso(value: string): string | null {
  const full = value.length === 16 ? `${value}:00` : value;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(full)) {
    return null;
  }
  const instant = new Date(`${full}+05:30`);
  return Number.isNaN(instant.getTime()) ? null : instant.toISOString();
}
