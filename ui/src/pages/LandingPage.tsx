import { useNavigate } from "react-router-dom";
import { isMockMode } from "../api/client";
import { useState, useEffect, useRef } from "react";
import { Modal } from "../components/Modal";

export function LandingPage() {
  const navigate = useNavigate();
  const [isModalOpen, setIsModalOpen] = useState(false);

  
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setIsVisible(true);
            observer.unobserve(entry.target); 
          }
        });
      },
      { threshold: 0.3 } 
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => {
      if (sectionRef.current) observer.unobserve(sectionRef.current);
    };
  }, []);

  return (
    <div style={{ 
      minHeight: '100vh', 
      background: '#050505', 
      color: '#ffffff', 
      fontFamily: "'Inter', sans-serif",
      display: 'flex',
      flexDirection: 'column',
      overflowX: 'hidden',
      position: 'relative'
    }}>
      
      {/* --- 1. MINIMALIST HEADER--- */}
      <header style={{ padding: '24px 48px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', position: 'relative', zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ 
            background: '#ffffff', padding: '8px', borderRadius: '12px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)'
          }}>
            <img 
              src="/logo.png" alt="DueGuide" style={{ height: '32px', objectFit: 'contain' }} 
              onError={(e) => {
                e.currentTarget.style.display = 'none';
                e.currentTarget.parentElement!.innerHTML = '<strong style="font-size:16px; color:#0f172a;">DG</strong>';
              }}
            />
          </div>
          <strong style={{ fontSize: '20px', letterSpacing: '-0.5px' }}>DueGuide</strong>
        </div>
        
        <div style={{ display: 'flex', gap: '24px', alignItems: 'center', fontSize: '14px', fontWeight: 500 }}>
          <span style={{ color: '#a1a1aa' }}>PayPal AI Hackathon 2026</span>
          <button 
            onClick={() => navigate('/app')}
            style={{ 
              background: '#ffffff', color: '#0a0a0a', border: 'none', 
              padding: '10px 24px', borderRadius: '100px', cursor: 'pointer',
              fontWeight: 700, transition: 'transform 0.2s, opacity 0.2s'
            }}
            onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.05)'}
            onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
          >
            Launch App ↗
          </button>
        </div>
      </header>

      {/* --- 2. THE PROLOGUE (The Story) --- */}
      <section style={{ 
        padding: '80px 24px 40px 24px', 
        textAlign: 'center', 
        position: 'relative',
        zIndex: 1
      }}>
        <div style={{
          position: 'absolute', top: '0', left: '50%', transform: 'translateX(-50%)',
          width: '800px', height: '400px',
          background: 'radial-gradient(ellipse, rgba(0,112,186,0.1) 0%, transparent 70%)',
          zIndex: -1, pointerEvents: 'none'
        }} />

        <div style={{ fontSize: '12px', fontWeight: 800, color: '#0070ba', letterSpacing: '4px', textTransform: 'uppercase', marginBottom: '24px' }}>
          The Origin
        </div>

        <h2 style={{ 
          fontSize: 'clamp(28px, 4vw, 48px)', 
          fontWeight: 900, 
          lineHeight: 1.1, 
          letterSpacing: '-1.5px',
          marginBottom: '24px',
          textTransform: 'uppercase'
        }}>
          When the LLM appeared, <br />
          <span style={{ color: '#a1a1aa' }}>they knew they would hallucinate.</span>
        </h2>

        <p style={{ 
          fontSize: '16px', 
          color: '#d4d4d8', 
          lineHeight: 1.7, 
          maxWidth: '650px', 
          margin: '0 auto',
          fontStyle: 'italic'
        }}>
          "Before DueGuide, financial agents were reckless. They created invoices out of thin air and promised discounts that didn't exist. The Creator tasked Python with building a deterministic engine, a place where numbers are immutable and strict."
        </p>
      </section>

      {/* --- 3. HERO CARD (Compact) --- */}
      <main style={{ padding: '0 24px 80px 24px', display: 'flex', justifyContent: 'center', position: 'relative', zIndex: 1 }}>
        
        <div style={{
          background: 'linear-gradient(135deg, #0070ba 0%, #001a3a 100%)',
          width: '100%',
          maxWidth: '1200px',
          borderRadius: '32px',
          position: 'relative',
          padding: '48px',
          display: 'flex',
          alignItems: 'center',
          boxShadow: '0 30px 60px -12px rgba(0, 112, 186, 0.3), inset 0 1px 1px rgba(255,255,255,0.2)',
          overflow: 'hidden',
          minHeight: '500px'
        }}>
          
          <div style={{ flex: 1, zIndex: 2, paddingRight: '32px' }}>
            <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
              <span style={{ background: 'rgba(255,255,255,0.1)', backdropFilter: 'blur(10px)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '6px 14px', borderRadius: '100px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px' }}>
                🏆 Winner Candidate
              </span>
              <span style={{ background: 'rgba(255,255,255,0.1)', backdropFilter: 'blur(10px)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '6px 14px', borderRadius: '100px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px' }}>
                ⚡ AI + PayPal
              </span>
            </div>

            <h1 style={{ fontSize: 'clamp(40px, 5vw, 64px)', fontWeight: 800, letterSpacing: '-2px', lineHeight: 1.05, margin: '0 0 20px 0', color: '#ffffff' }}>
              Turn overdue <br />
              invoices into <br />
              <span style={{ color: '#7dd3fc' }}>active deals.</span>
            </h1>

            <p style={{ fontSize: '18px', color: '#e0f2fe', maxWidth: '450px', lineHeight: 1.6, marginBottom: '32px', fontWeight: 400 }}>
              DueGuide is an AI-powered recovery engine. We don't just send reminders; we negotiate, compute risk-free financial alternatives, and execute them seamlessly via PayPal.
            </p>

            <div style={{ display: 'flex', gap: '16px' }}>
              <button 
                onClick={() => navigate('/app')}
                style={{ 
                  background: '#ffffff', color: '#0a0a0a', border: 'none', 
                  padding: '16px 28px', borderRadius: '12px', cursor: 'pointer',
                  fontSize: '15px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px',
                  transition: 'transform 0.2s', boxShadow: '0 10px 20px rgba(0,0,0,0.2)'
                }}
                onMouseOver={(e) => e.currentTarget.style.transform = 'translateY(-2px)'}
                onMouseOut={(e) => e.currentTarget.style.transform = 'translateY(0)'}
              >
                Open Merchant Dashboard
              </button>
              
              {/* BUTTON TO OPEN THE MODAL */}
              <button 
                onClick={() => setIsModalOpen(true)}
                style={{ 
                  background: 'transparent', color: '#ffffff', border: '1px solid rgba(255,255,255,0.3)', 
                  padding: '16px 28px', borderRadius: '12px', cursor: 'pointer',
                  fontSize: '15px', fontWeight: 600, backdropFilter: 'blur(10px)',
                  transition: 'background 0.2s'
                }}
                onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
                onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
              >
                View Customer Portal
              </button>
            </div>
          </div>

          {/* Right-hand Mockup */}
          <div style={{ 
            flex: 1, 
            position: 'relative', 
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            zIndex: 1,
            perspective: '1200px'
          }}>
            <div style={{
              background: '#ffffff',
              width: '105%', 
              height: '360px',
              borderRadius: '16px',
              boxShadow: '-20px 30px 60px rgba(0,0,0,0.4), 0 0 0 1px rgba(0,0,0,0.05)',
              transform: 'rotateY(-10deg) rotateX(3deg)',
              animation: 'float 6s ease-in-out infinite',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column'
            }}>
              <div style={{ height: '36px', background: '#f8fafc', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', padding: '0 16px', gap: '8px' }}>
                <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#ef4444' }}></div>
                <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#f59e0b' }}></div>
                <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#10b981' }}></div>
              </div>
              
              <div style={{ padding: '20px', flex: 1, background: '#f4f7f9', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontWeight: 800, color: '#0f172a', fontSize: '16px' }}>Live Audit Trail</div>
                  <div style={{ background: '#10b981', color: 'white', padding: '4px 10px', borderRadius: '100px', fontSize: '10px', fontWeight: 700 }}>AG Grid</div>
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                  <div style={{ background: '#fff', padding: '12px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '9px', color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>Total Events</div>
                    <div style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a' }}>1,248</div>
                  </div>
                  <div style={{ background: '#fef2f2', padding: '12px', borderRadius: '8px', border: '1px solid #fecaca' }}>
                    <div style={{ fontSize: '9px', color: '#ef4444', fontWeight: 600, textTransform: 'uppercase' }}>Blocked</div>
                    <div style={{ fontSize: '20px', fontWeight: 800, color: '#ef4444' }}>12</div>
                  </div>
                  <div style={{ background: '#fff', padding: '12px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '9px', color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>Freq</div>
                    <div style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a' }}>~2.0s</div>
                  </div>
                </div>

                <div style={{ background: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', flex: 1, padding: '12px' }}>
                  <div style={{ display: 'flex', gap: '12px', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px', marginBottom: '8px', fontSize: '10px', color: '#64748b', fontWeight: 600 }}>
                    <span style={{ width: '30px' }}>SEQ</span>
                    <span style={{ flex: 1 }}>ACTION</span>
                    <span style={{ width: '60px' }}>SEVERITY</span>
                  </div>
                  <div style={{ display: 'flex', gap: '12px', fontSize: '11px', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}>
                    <span style={{ width: '30px', color: '#94a3b8' }}>12</span>
                    <span style={{ flex: 1, fontWeight: 600, color: '#0070ba' }}>PAYMENT_CONFIRMED</span>
                    <span style={{ width: '60px' }}><span style={{ background: '#dcfce7', color: '#166534', padding: '2px 6px', borderRadius: '4px', fontSize: '9px', fontWeight: 700 }}>INFO</span></span>
                  </div>
                  <div style={{ display: 'flex', gap: '12px', fontSize: '11px', padding: '6px 0', background: '#fef2f2', margin: '0 -12px', paddingLeft: '12px', paddingRight: '12px' }}>
                    <span style={{ width: '30px', color: '#94a3b8' }}>11</span>
                    <span style={{ flex: 1, fontWeight: 600, color: '#ef4444' }}>PROPOSAL_BLOCKED</span>
                    <span style={{ width: '60px' }}><span style={{ background: '#fecaca', color: '#991b1b', padding: '2px 6px', borderRadius: '4px', fontSize: '9px', fontWeight: 700 }}>CRITICAL</span></span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* --- 4. PROBLEM AND SOLUTION --- */}
      <section style={{ maxWidth: '1200px', margin: '120px auto', padding: '0 24px' }}>
        <style>{`
          .comparison-card {
            padding: 48px; border-radius: 32px;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative; overflow: hidden;
          }
          .comparison-card.old-way { background: #0a0a0a; border: 1px solid #27272a; filter: grayscale(0.8); }
          .comparison-card.old-way:hover { filter: grayscale(0); border-color: #ef4444; transform: translateY(-5px); }
          .comparison-card.old-way::before { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 4px; background: linear-gradient(90deg, #ef4444, transparent); opacity: 0; transition: opacity 0.3s; }
          .comparison-card.old-way:hover::before { opacity: 1; }
          
          .comparison-card.new-way { background: linear-gradient(145deg, #0f172a 0%, #001a3a 100%); border: 1px solid #0070ba; box-shadow: 0 0 40px rgba(0, 112, 186, 0.1); }
          .comparison-card.new-way:hover { border-color: #38bdf8; box-shadow: 0 0 60px rgba(0, 112, 186, 0.3), inset 0 0 20px rgba(0,112,186,0.1); transform: translateY(-5px) scale(1.02); }
        `}</style>
        
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '32px' }}>
          <div className="comparison-card old-way">
            <div style={{ fontSize: '48px', marginBottom: '24px' }}>🚫</div>
            <h2 style={{ fontSize: '32px', fontWeight: 800, marginBottom: '16px', color: '#f87171', letterSpacing: '-1px' }}>The Old Way</h2>
            <p style={{ color: '#a1a1aa', fontSize: '17px', lineHeight: 1.7 }}>
              Traditional collections are rigid. If a customer can't pay the full invoice, merchants lose money or spend hours negotiating manually. Standard AI chatbots <strong style={{color: '#fca5a5'}}>hallucinate numbers</strong>, which is unacceptable in finance.
            </p>
          </div>

          <div className="comparison-card new-way">
            <div style={{ fontSize: '48px', marginBottom: '24px' }}>🚀</div>
            <h2 style={{ fontSize: '32px', fontWeight: 800, marginBottom: '16px', color: '#7dd3fc', letterSpacing: '-1px' }}>The DueGuide Way</h2>
            <p style={{ color: '#e0f2fe', fontSize: '17px', lineHeight: 1.7 }}>
              An AI agent interprets the customer's intent, but a strict deterministic Python engine calculates the financial terms. <strong style={{color: '#fff'}}>Zero hallucinations.</strong> If the AI goes out of policy, it is instantly blocked and audited.
            </p>
          </div>
        </div>
      </section>

      {/* --- 5. INTERACTIVE WORKFLOW --- */}
      <section style={{ maxWidth: '1200px', margin: '120px auto', padding: '0 24px', textAlign: 'center', position: 'relative' }}>
        <style>{`
          .workflow-card {
            background: #111111; border: 1px solid #27272a; border-radius: 20px;
            padding: 40px 32px; text-align: left; position: relative; overflow: hidden;
            transition: all 0.3s ease; cursor: default;
          }
          .workflow-card:hover { border-color: #0070ba; background: #161616; transform: translateY(-8px); }
          .workflow-number {
            position: absolute; top: -20px; right: -10px; font-size: 120px; font-weight: 900;
            color: rgba(255,255,255,0.03); line-height: 1; transition: color 0.3s, transform 0.3s;
            font-family: 'Inter', monospace;
          }
          .workflow-card:hover .workflow-number { color: rgba(0,112,186,0.15); transform: translate(-5px, 5px) scale(1.1); }
        `}</style>
        
        <h2 style={{ fontSize: '48px', fontWeight: 800, letterSpacing: '-2px', marginBottom: '16px' }}>
          Human-in-the-loop <span style={{ color: '#0070ba' }}>Workflow</span>
        </h2>
        <p style={{ color: '#a1a1aa', fontSize: '18px', maxWidth: '600px', margin: '0 auto 64px auto' }}>
          How we turn a blocked payment into an executed PayPal invoice in seconds.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '24px', position: 'relative', zIndex: 1 }}>
          {[
            { step: '01', title: 'AI Intent', desc: 'The customer replies: "I can only pay $300 today". The AI extracts the intent.' },
            { step: '02', title: 'Financial Engine', desc: 'Python calculates two strict, policy-compliant schedules using Decimal precision.' },
            { step: '03', title: 'Merchant Approval', desc: 'The merchant reviews the alternatives in the UI and approves one.' },
            { step: '04', title: 'PayPal Execution', desc: 'The old invoice is cancelled and a new one is sent via PayPal Sandbox.' },
          ].map((item, i) => (
            <div key={i} className="workflow-card">
              <div className="workflow-number">{item.step}</div>
              <div style={{ color: '#38bdf8', fontWeight: 800, marginBottom: '16px', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '1px' }}>Step {item.step}</div>
              <h3 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '12px', color: '#fff' }}>{item.title}</h3>
              <p style={{ color: '#a1a1aa', fontSize: '15px', lineHeight: 1.6 }}>{item.desc}</p>
            </div>
          ))}
        </div>
      </section> 

      {/* --- 6. TECHNICAL STACK --- */}
      <section style={{ maxWidth: '1200px', margin: '120px auto', padding: '0 24px' }}>
        <style>{`
          .tech-pill {
            background: #111; border: 1px solid #333; border-radius: 100px;
            padding: 14px 28px; font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 10px;
            transition: all 0.3s ease; cursor: default;
          }
          .tech-pill:hover { background: #0f172a; border-color: #0070ba; transform: translateY(-4px); box-shadow: 0 10px 20px rgba(0, 112, 186, 0.2); }
        `}</style>
        
        <div style={{ background: 'linear-gradient(180deg, #111111 0%, #050505 100%)', border: '1px solid #27272a', borderRadius: '40px', padding: '80px 40px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', top: '-50%', left: '50%', transform: 'translateX(-50%)', width: '600px', height: '600px', background: 'radial-gradient(circle, rgba(0,112,186,0.1) 0%, transparent 70%)', pointerEvents: 'none' }} />

          <h2 style={{ fontSize: '40px', fontWeight: 800, marginBottom: '16px', letterSpacing: '-1px', position: 'relative', zIndex: 1 }}>Built for Scale & Security</h2>
          <p style={{ color: '#a1a1aa', fontSize: '17px', maxWidth: '600px', marginBottom: '56px', position: 'relative', zIndex: 1 }}>
            No shortcuts. We use an enterprise-grade stack to ensure transactional integrity, strict typing, and a beautiful user experience.
          </p>
          
          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', justifyContent: 'center', position: 'relative', zIndex: 1 }}>
            {[
              { name: 'React + Vite', icon: '⚛️' },
              { name: 'TypeScript', icon: '📘' },
              { name: 'FastAPI', icon: '⚡' },
              { name: 'Python / Decimal', icon: '🐍' },
              { name: 'AG Grid 31', icon: '📊' },
              { name: 'PayPal API v2', icon: '💳' },
              { name: 'SQLite / WAL', icon: '🗄️' },
            ].map((tech, i) => (
              <div key={i} className="tech-pill">
                <span style={{ fontSize: '18px' }}>{tech.icon}</span> {tech.name}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* --- 7. AI EFFECT (ACTIVADO POR SCROLL) --- */}
      <section 
        ref={sectionRef}
        style={{ 
          maxWidth: '900px', 
          margin: '120px auto 160px auto', 
          padding: '0 24px', 
          textAlign: 'center', 
          position: 'relative',
          overflow: 'hidden'
        }}>
        <style>{`
          /* Animación del botón */
          .cta-button {
            background: linear-gradient(135deg, #0070ba, #0099ff);
            color: #ffffff; border: none; 
            padding: 22px 56px; border-radius: 16px; cursor: pointer;
            font-size: 20px; font-weight: 700; 
            transition: all 0.3s ease;
            position: relative;
            z-index: 10;
            box-shadow: 0 10px 20px rgba(0, 112, 186, 0.3);
          }
          .cta-button:hover {
            transform: translateY(-4px) scale(1.02);
            box-shadow: 0 20px 40px rgba(0, 112, 186, 0.6), 0 0 20px rgba(56, 189, 248, 0.4);
          }

          /* Efecto Typewriter (solo se activa si isVisible) */
          .typewriter-active {
            overflow: hidden; 
            border-right: .15em solid #38bdf8; 
            white-space: nowrap; 
            margin: 0 auto; 
            letter-spacing: -.05em; 
            animation: 
              typing 2s steps(40, end),
              blink-caret .75s step-end infinite;
          }
          
          /* En móvil desactivamos el nowrap para que el texto no se corte */
          @media (max-width: 768px) {
            .typewriter-active { white-space: normal; animation: none; border: none; }
          }

          @keyframes typing {
            from { width: 0 }
            to { width: 100% }
          }

          @keyframes blink-caret {
            from, to { border-color: transparent }
            50% { border-color: #38bdf8; }
          }

          /* Efecto de respiración (Glow) para el logo */
          .neural-glow {
            animation: pulse-glow 3s infinite;
          }
          @keyframes pulse-glow {
            0% { box-shadow: 0 0 20px rgba(56, 189, 248, 0.2); }
            50% { box-shadow: 0 0 40px rgba(56, 189, 248, 0.6), 0 0 60px rgba(0, 112, 186, 0.4); }
            100% { box-shadow: 0 0 20px rgba(56, 189, 248, 0.2); }
          }

          /* Partículas flotantes */
          .particles {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            overflow: hidden;
            z-index: 0;
            pointer-events: none;
          }
          .particle {
            position: absolute;
            display: block;
            list-style: none;
            width: 6px;
            height: 6px;
            background: rgba(56, 189, 248, 0.4);
            animation: animate 15s linear infinite;
            bottom: -50px;
            border-radius: 50%;
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.8);
          }
          .particle:nth-child(1) { left: 10%; width: 8px; height: 8px; animation-duration: 12s; animation-delay: 0s; }
          .particle:nth-child(2) { left: 30%; width: 4px; height: 4px; animation-duration: 15s; animation-delay: 2s; }
          .particle:nth-child(3) { left: 50%; width: 6px; height: 6px; animation-duration: 18s; animation-delay: 4s; }
          .particle:nth-child(4) { left: 70%; width: 10px; height: 10px; animation-duration: 14s; animation-delay: 0s; }
          .particle:nth-child(5) { left: 90%; width: 5px; height: 5px; animation-duration: 16s; animation-delay: 3s; }

          @keyframes animate {
            0% { transform: translateY(0) rotate(0deg); opacity: 1; border-radius: 50%; }
            100% { transform: translateY(-1000px) rotate(720deg); opacity: 0; border-radius: 0; }
          }
        `}</style>

        {/* Floating Particles */}
        <ul className="particles">
          <li className="particle"></li>
          <li className="particle"></li>
          <li className="particle"></li>
          <li className="particle"></li>
          <li className="particle"></li>
        </ul>

        {/* Central background glow */}
        <div style={{
          position: 'absolute', top: '10%', left: '50%', transform: 'translateX(-50%)',
          width: '800px', height: '400px',
          background: 'radial-gradient(ellipse, rgba(0,112,186,0.15) 0%, transparent 70%)',
          zIndex: 0, pointerEvents: 'none'
        }} />

        {/* THE NEURAL EFFECT LOGO */}
        <div style={{ 
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px',
          marginBottom: '48px', position: 'relative', zIndex: 1
        }}>
          <div className="neural-glow" style={{
            background: '#ffffff', padding: '12px', borderRadius: '20px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: '1px solid rgba(56, 189, 248, 0.5)', transition: 'all 0.3s'
          }}>
            <img src="/logo.png" alt="DueGuide Shield" style={{ height: '64px', width: '64px', objectFit: 'cover', objectPosition: 'top' }} />
          </div>
          
          <div style={{ textAlign: 'left' }}>
            <div style={{ fontSize: '36px', fontWeight: 800, letterSpacing: '-1px', color: '#ffffff', lineHeight: 1 }}>
              DueGuide
            </div>
            <div style={{ fontSize: '14px', fontWeight: 600, color: '#0070ba', letterSpacing: '2px', textTransform: 'uppercase', marginTop: '4px' }}>
              AI Collections
            </div>
          </div>
        </div>

        {/* TEXTO CON TYPEWRITER ACTIVADO POR SCROLL */}
        <div style={{ position: 'relative', zIndex: 1, marginBottom: '24px', minHeight: '60px' }}>
          <h2 
            className={isVisible ? "typewriter-active" : ""} 
            style={{ 
              fontSize: 'clamp(28px, 4vw, 48px)', 
              fontWeight: 800, 
              letterSpacing: '-1.5px', 
              lineHeight: 1.1, 
              display: 'inline-block',
              opacity: isVisible ? 1 : 0 
            }}
          >
            Ready to see the <span style={{ color: '#38bdf8' }}>AI Guardrail</span> in action?
          </h2>
        </div>
        
        <p style={{ 
          color: '#a1a1aa', fontSize: '20px', maxWidth: '600px', margin: '0 auto 48px auto', 
          position: 'relative', zIndex: 1,
          opacity: isVisible ? 1 : 0, 
          transition: 'opacity 1s ease-in 1s' 
        }}>
          Enter the merchant dashboard and try to propose a 40% discount. Watch how the system blocks the AI before it can touch PayPal.
        </p>
        
        <button 
          className="cta-button"
          onClick={() => navigate('/app')}
          style={{ 
            opacity: isVisible ? 1 : 0,
            transform: isVisible ? 'translateY(0)' : 'translateY(20px)',
            transition: 'all 0.6s ease-out 1.5s' 
          }}
        >
          Launch Live Demo →
        </button>
      </section>

      {/* --- 8. FOOTER --- */}
      <footer style={{ padding: '32px 48px', display: 'flex', justifyContent: 'space-between', fontSize: '14px', color: '#71717a', borderTop: '1px solid #27272a', position: 'relative', zIndex: 10 }}>
        <span>© 2026 DueGuide. Built for PayPal AI Hackathon.</span>
        <span>Mode: {isMockMode() ? "Mock Data (Sandbox)" : "Live API"}</span>
      </footer>

      <style>{`
        @keyframes float {
          0% { transform: translateY(0px) rotateY(-10deg) rotateX(3deg); }
          50% { transform: translateY(-10px) rotateY(-10deg) rotateX(3deg); }
          100% { transform: translateY(0px) rotateY(-10deg) rotateX(3deg); }
        }
      `}</style>

      {/* --- 9. MODAL --- */}
      <Modal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)}
        title="Secure Customer Portal"
      >
        For security reasons, customer links are generated dynamically with a one-time token. 
        <br /><br />
        To view the client experience, please open the <strong>Merchant Dashboard</strong>, generate a proposal, and click <strong>"Open customer view"</strong>.
      </Modal>
    </div>
  );
}