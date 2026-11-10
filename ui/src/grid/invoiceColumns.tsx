import type { ColDef } from "ag-grid-community";
import type { Invoice } from "../types/api";
import { formatMoney } from "../components/Money";

export const invoiceColumns: ColDef<Invoice>[] = [
  { field: "id", headerName: "Invoice", width: 130 },
  { field: "customer_name", headerName: "Customer", flex: 1, minWidth: 200 },
  {
    field: "balance",
    headerName: "Balance",
    width: 140,
    type: "rightAligned",
    valueFormatter: (p) => formatMoney(p.value as string),
  },
  { field: "due_date", headerName: "Due date", width: 130 },
  {
    field: "status",
    headerName: "Status",
    width: 130,
    cellStyle: (p) => (p.value === "OVERDUE" ? { color: "#b91c1c", fontWeight: 600 } : null),
  },
  { field: "paypal_invoice_id", headerName: "PayPal ID", width: 200 },
];