import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { LandingPage } from "./pages/LandingPage";
import { InvoicesPage } from "./pages/InvoicesPage";
import { ProposalPage } from "./pages/ProposalPage";
import { CustomerPage } from "./pages/CustomerPage";
import { AuditPage } from "./pages/AuditPage";

export function App() {
  return (
    <Routes>
      {/* 1. Public Landing Page */}
      <Route path="/" element={<LandingPage />} />

      {/* 2. Protected Dashboard (Under /app) */}
      <Route path="/app" element={<Layout />}>
        <Route index element={<InvoicesPage />} />
        <Route path="proposal/:id" element={<ProposalPage />} />
        <Route path="audit" element={<AuditPage />} />
      </Route>

      {/* 3. Client Portal (Public) */}
      <Route path="/customer/:token" element={<CustomerPage />} />
    </Routes>
  );
}