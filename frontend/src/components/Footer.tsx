import { Link } from 'react-router-dom'

const YEAR = new Date().getFullYear()

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div>
          <strong>Campus Customs</strong>
          <p>Gear for game days, study nights, and everything in between.</p>
        </div>
        <div className="footer-links">
          <Link to="/products">Shop all</Link>
          <Link to="/about">About Us</Link>
          <Link to="/login">Log in</Link>
        </div>
      </div>
      <p className="footer-note">© {YEAR} Campus Customs · A class project, not affiliated with any official store.</p>
    </footer>
  )
}
