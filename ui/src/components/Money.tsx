import type { Money as MoneyString } from "../types/api";

const MONEY_RE = /^(-?)(0|[1-9][0-9]{0,11})\.([0-9]{2})$/;
const THOUSANDS_RE = /\B(?=([0-9]{3})+(?![0-9]))/g;

/** Formats a contract Money string without ever converting it to a number. */
export function formatMoney(value: MoneyString | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const match = MONEY_RE.exec(value);
  if (match === null) return "—";
  const [, sign, integerPart, fraction] = match;
  return `${sign}$${integerPart.replace(THOUSANDS_RE, ",")}.${fraction}`;
}

export function Money({ value }: { value: MoneyString | null | undefined }) {
  return <span className="money">{formatMoney(value)}</span>;
}