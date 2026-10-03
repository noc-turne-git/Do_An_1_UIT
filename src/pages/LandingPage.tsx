import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDown, ArrowUpRight, Bell, Compass, Heart, Sparkles } from 'lucide-react'
import { LoginModal } from '../features/auth/components/LoginModal'
import './LandingPage.css'

const features = [
  { icon: Heart, title: 'Learns your style.', text: 'From local cafés to outdoor adventures, your assistant gets to know what makes a trip feel like you.', image: 'photo-1476514525535-07fb3b4ae5f1', label: 'A little closer to nature' },
  { icon: Compass, title: 'Works for you.', text: 'Discover your next destination, find beautiful places to stay, and bring all your travel ideas together.', image: 'photo-1516483638261-f4dbaf036963', label: 'Your next great escape' },
  { icon: Bell, title: 'One step ahead.', text: 'Keep your plans, favorite places, and inspiration together, with more time to enjoy the journey.', image: 'photo-1507525428034-b723cf961d3e', label: 'Room to slow down' },
]

export function LandingPage() {
  const [loginOpen, setLoginOpen] = useState(false)
  const loginRef = useRef<HTMLButtonElement>(null)
  return <div className="landing-page">
    <header className="landing-header">
      <Link to="/" className="landing-brand" aria-label="Travelio welcome"><Sparkles fill="currentColor" size={27} />Travelio</Link>
      <div className="landing-header-actions"><button ref={loginRef} type="button" className="landing-login" onClick={() => setLoginOpen(true)}>Login</button><Link to="/home" className="landing-button">Let’s start <ArrowUpRight size={18} /></Link></div>
    </header>
    <main>
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero-copy">
          <span className="landing-eyebrow"><Sparkles size={15} /> YOUR PERSONAL TRAVEL ASSISTANT</span>
          <h1 id="landing-title">Travel<br />that gets<br /><em>you.</em></h1>
          <p>A little inspiration. A world of possibilities. Meet the travel assistant that gets to know you and helps make every journey your own.</p>
          <Link to="/home" className="landing-button landing-hero-cta">Let’s start <ArrowUpRight size={20} /></Link>
          <a href="#your-assistant" className="landing-scroll"><ArrowDown size={16} /> A new way to travel</a>
        </div>
        <div className="landing-hero-photo">
          <img src="https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?auto=format&fit=crop&w=1800&q=85" alt="A peaceful lake surrounded by mountains and a lakeside village" fetchPriority="high" />
          <div className="landing-photo-caption"><span>LESS SEARCHING. MORE DISCOVERING.</span><strong>Somewhere that feels like you.</strong></div>
          <div className="landing-assistant-note"><Sparkles size={26} /><div><strong>Your next adventure starts here.</strong><span>Let’s find a place you’ll love.</span></div></div>
        </div>
      </section>
      <section id="your-assistant" className="landing-features">
        <div className="landing-section-intro"><span className="landing-eyebrow">MADE FOR THE WAY YOU TRAVEL</span><h2>A world of ideas.<br />An assistant of your own.</h2><p>Dream a little bigger. Plan a little easier. Make room for the experiences that matter to you.</p></div>
        <div id="discover" className="landing-feature-grid">{features.map(({ icon: Icon, title, text, image, label }) => <article key={title} className="landing-feature"><div className="landing-feature-photo"><img src={`https://images.unsplash.com/${image}?auto=format&fit=crop&w=800&q=80`} alt={label} loading="lazy" /><span>{label}</span></div><h3><Icon size={23} strokeWidth={1.5} />{title}</h3><p>{text}</p></article>)}</div>
      </section>
      <section className="landing-final-cta"><Sparkles size={38} fill="currentColor" /><h2>Every trip, more you.</h2><p>Your next chapter is out there. Let’s go find it.</p><Link to="/home" className="landing-button">Let’s start <ArrowUpRight size={19} /></Link></section>
    </main>
    <footer className="landing-footer"><Link to="/" className="landing-brand"><Sparkles size={22} fill="currentColor" />Travelio</Link><span>© 2026 Travelio · A world of possibilities.</span><Link to="/home">Start exploring <ArrowUpRight size={16} /></Link></footer>
    {loginOpen && <LoginModal onClose={() => { setLoginOpen(false); loginRef.current?.focus() }} />}
  </div>
}
