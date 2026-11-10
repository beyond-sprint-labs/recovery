import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { isMockMode } from "../api/client";
import { SecurePlaceholder } from "./SecurePlaceholder";

export function Layout() {
  const navigate = useNavigate();
  const [showSecureMsg, setShowSecureMsg] = useState(false);

  const handleCustomerPortalClick = () => {
  
    setShowSecureMsg(true);
  };

  return (
    <div className="app">
      <header className="topbar">
        {/* Clickable logo to return to the landing page */}
        <div className="brand" onClick={() => { navigate('/'); setShowSecureMsg(false); }} style={{ cursor: 'pointer' }}>
          <div 
            className="brand-logo" 
            style={{ 
              background: '#ffffff',
              padding: '4px',
              borderRadius: '8px',
              width: '36px',
              height: '36px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: 'var(--shadow-sm)'
            }}
          >
            <img 
              src="/logo.png" 
              alt="DG" 
              style={{ width: '100%', height: '100%', objectFit: 'contain' }} 
              onError={(e) => {
                e.currentTarget.style.display = 'none';
                if(e.currentTarget.parentElement) {
                  e.currentTarget.parentElement.innerHTML = '<strong style="color:#0f172a; font-weight:800;">D</strong>';
                }
              }}
            />
          </div>
          <div>
            <strong>DueGuide Recovery</strong>
            <span className="sub">PayPal Sandbox & AG Grid Powered</span>
          </div>
        </div>
        
        <nav className="nav-tabs">
          <NavLink to="/app/audit" className="nav-tab" onClick={() => setShowSecureMsg(false)}>
            <span>📊</span> Live Audit Grid
          </NavLink>
          <NavLink to="/app" end className="nav-tab" onClick={() => setShowSecureMsg(false)}>
            <span>📋</span> Overview
          </NavLink>
          
          <button 
            className="nav-tab" 
            onClick={handleCustomerPortalClick}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
          >
            <span>👤</span> Customer Portal
          </button>
        </nav>

        <div className="topbar-actions">
          <span className={`mode-badge ${isMockMode() ? "mock" : "live"}`}>
            <span className="dot"></span> {isMockMode() ? "MOCK DATA ACTIVE" : "LIVE API"}
          </span>
          <span className="mode-badge live" style={{ background: '#ecfdf5', color: '#10b981', border: '1px solid #6ee7b7' }}>
            PayPal Sandbox
          </span>
        </div>
      </header>
      
      <main className="content" style={{ position: 'relative' }}>
        {showSecureMsg ? (
          <SecurePlaceholder 
            title="Customer Link Protected"
            description="For security, customer links are generated dynamically with a one-time token. To view the client experience, please go to the Overview, generate a proposal, and click 'Open customer view'."
            actionLabel="Return to Overview"
            onAction={() => setShowSecureMsg(false)}
          />
        ) : (
          <Outlet />
        )}
      </main>
      
      <footer className="footer">
        <div className="muted" style={{ fontSize: '12px' }}>
          Simulation subject to merchant approval and customer acceptance. Not financial or legal advice.
        </div>
        <div className="muted" style={{ fontSize: '12px' }}>
          DueGuide v1.0 • React + Vite • AG Grid Community
        </div>
      </footer>
    </div>
  );
}