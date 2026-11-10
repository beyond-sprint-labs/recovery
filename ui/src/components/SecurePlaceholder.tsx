interface SecurePlaceholderProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function SecurePlaceholder({ title, description, actionLabel, onAction }: SecurePlaceholderProps) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '70vh', padding: '40px 24px',
      background: 'radial-gradient(circle at 50% 50%, var(--brand-light) 0%, var(--bg-app) 100%)'
    }}>
      <div style={{
        background: 'var(--bg-surface)',
        border: '1px solid rgba(226, 232, 240, 0.8)',
        borderRadius: '32px', 
        padding: '56px 48px',
        maxWidth: '520px',
        width: '100%',
        textAlign: 'center',
        boxShadow: '0 20px 40px -10px rgba(0,0,0,0.1), inset 0 1px 1px rgba(255,255,255,1)',
        position: 'relative',
        overflow: 'hidden'
      }}>
        {/* Top-edge gradient effect (Glassmorphism) */}
        <div style={{ 
          position: 'absolute', top: 0, left: 0, right: 0, height: '6px', 
          background: 'linear-gradient(90deg, #0070ba, #38bdf8, #0070ba)' 
        }} />

        {/* Icon with focus ring */}
        <div style={{
          width: '80px', height: '80px', borderRadius: '24px', 
          background: 'linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%)', 
          color: '#0070ba',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '36px', margin: '0 auto 32px auto',
          boxShadow: 'inset 0 2px 4px rgba(255,255,255,0.5), 0 4px 6px rgba(0,0,0,0.05)',
          border: '1px solid #bae6fd'
        }}>
          🛡️ {/* A shield looks more secure than a padlock. */}
        </div>

        <h2 style={{ 
          fontSize: '28px', 
          fontWeight: 800, 
          color: 'var(--text-primary)', 
          marginBottom: '16px',
          letterSpacing: '-0.5px'
        }}>
          {title}
        </h2>
        
        <p style={{ 
          color: 'var(--text-secondary)', 
          fontSize: '16px', 
          lineHeight: 1.6, 
          marginBottom: '40px',
          maxWidth: '400px',
          margin: '0 auto 40px auto'
        }}>
          {description}
        </p>

        {actionLabel && onAction && (
          <button 
            onClick={onAction}
            className="btn"
            style={{ 
              width: '100%', 
              padding: '16px', 
              fontSize: '16px', 
              fontWeight: 700,
              background: 'var(--text-primary)', 
              color: '#ffffff',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              transition: 'transform 0.2s, background 0.2s',
              boxShadow: '0 4px 12px rgba(0,0,0,0.15)'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.background = '#1e293b';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.background = 'var(--text-primary)';
            }}
          >
            {actionLabel}
          </button>
        )}

        {/* Security footer */}
        <div style={{ 
          display: 'flex', alignItems: 'center', justifyContent: 'center', 
          gap: '8px', marginTop: '32px', color: 'var(--text-tertiary)', fontSize: '13px' 
        }}>
          <span>🔒</span> End-to-end encrypted
        </div>
      </div>
    </div>
  );
}