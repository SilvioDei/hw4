import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

const links = [
  { to: '/', label: 'Home' },
  { to: '/products', label: 'Products' },
  { to: '/about', label: 'About Us' },
]

export default function NavBar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/')
  }

  return (
    <header>
      <div className="announcement">
        <span>Free campus pickup on every order</span>
        <span aria-hidden="true">✦</span>
        <span>New fall stock on the shelves</span>
        <span aria-hidden="true">✦</span>
        <span>Ask the Clerk, bottom right</span>
      </div>
      <nav className="navbar">
        <Link to="/" className="brand" aria-label="Campus Customs home">
          <span className="brand-mark" aria-hidden="true">CC</span>
          <span className="brand-text">
            <span className="brand-name">Campus Customs</span>
            <span className="brand-tagline">Outfitters to the Quad · Since Move-In Day</span>
          </span>
        </Link>
        <ul className="nav-links">
          {links.map((l) => (
            <li key={l.to}>
              <NavLink to={l.to} end={l.to === '/'}>
                {l.label}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="nav-account">
          {user ? (
            <>
              <span className="nav-user">Hi, {user.first_name}</span>
              <button className="btn btn-small btn-outline" onClick={handleLogout}>
                Log out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login">Log in</NavLink>
              <NavLink to="/create-account" className="btn btn-small">
                Create account
              </NavLink>
            </>
          )}
        </div>
      </nav>
    </header>
  )
}
