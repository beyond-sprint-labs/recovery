import type { Money as MoneyString } from "../types/api";

const formatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

/** Renders a Money string. Never calls parseFloat for formatting. */
export function formatMoney(value: MoneyString | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  // Format by string only: split integer / fraction, keep as-is.
  const neg = value.startsWith("-");
  const raw = neg ? value.slice(1) : value;
  const [intPart, fracPart = "00"] = raw.split(".");
  const asNumber = Number(intPart); // safe: integers up to 12 digits per contract
  if (!Number.isFinite(asNumber)) return value;
  const withFrac = `${asNumber}.${fracPart.padEnd(2, "0").slice(0, 2)}`;
  const formatted = formatter.format(Number(withFrac));
  return neg ? `-${formatted}` : formatted;
}

export function Money({ value }: { value: MoneyString | null | undefined }) {
  return <span className="money">{formatMoney(value)}</span>;
}