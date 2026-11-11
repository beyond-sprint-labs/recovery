import React from "react";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export function Modal({ isOpen, onClose, title, children }: ModalProps) {
  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(5, 5, 5, 0.8)',
      backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000, padding: '24px'
    }}>
      <div style={{
        background: 'linear-gradient(145deg, #111111 0%, #0a0a0a 100%)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '24px',
        padding: '40px',
        maxWidth: '480px',
        width: '100%',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5), inset 0 1px 1px rgba(255,255,255,0.1)',
        position: 'relative',
        animation: 'modalIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)'
      }}>
        {/* Close button (X) */}
        <button 
          onClick={onClose}
          style={{
            position: 'absolute', top: '20px', right: '20px',
            background: 'rgba(255,255,255,0.05)', border: 'none',
            color: '#a1a1aa', width: '32px', height: '32px',
            borderRadius: '50%', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'background 0.2s'
          }}
          onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
          onMouseOut={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
        >
          ✕
        </button>

        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <div style={{
            width: '64px', height: '64px', borderRadius: '50%',
            background: 'rgba(0, 112, 186, 0.15)', color: '#38bdf8',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '32px', margin: '0 auto 16px auto',
            border: '1px solid rgba(56, 189, 248, 0.3)'
          }}>
            🔒
          </div>
          <h2 style={{ fontSize: '24px', fontWeight: 800, color: '#ffffff', margin: 0 }}>{title}</h2>
        </div>

        <div style={{ color: '#a1a1aa', fontSize: '16px', lineHeight: 1.6, textAlign: 'center', marginBottom: '32px' }}>
          {children}
        </div>

        <button 
          onClick={onClose}
          style={{
            width: '100%', padding: '16px', borderRadius: '12px',
            background: 'var(--brand-primary)', color: 'white',
            border: 'none', fontSize: '16px', fontWeight: 700,
            cursor: 'pointer', transition: 'transform 0.2s, background 0.2s'
          }}
          onMouseOver={(e) => e.currentTarget.style.transform = 'translateY(-2px)'}
          onMouseOut={(e) => e.currentTarget.style.transform = 'translateY(0)'}
        >
          Understood
        </button>
      </div>

      {/* Injected CSS animation */}
      <style>{`
        @keyframes modalIn {
          from { opacity: 0; transform: scale(0.95) translateY(10px); }
          to { opacity: 1; transform: scale(1) translateY(0); }
        }
      `}</style>
    </div>
  );
}