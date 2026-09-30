import { BrowserRouter, Route, Routes } from 'react-router-dom'
import NavBar from './components/NavBar'
import Footer from './components/Footer'
import ChatWidget from './components/ChatWidget'
import ChatResults from './components/ChatResults'
import Home from './pages/Home'
import Products from './pages/Products'
import ProductPage from './pages/ProductPage'
import About from './pages/About'
import Login from './pages/Login'
import CreateAccount from './pages/CreateAccount'
import { AuthProvider } from './auth'
import { ChatResultsProvider } from './chatResults'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ChatResultsProvider>
          <NavBar />
          <ChatResults />
          <main className="page">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/products" element={<Products />} />
              <Route path="/products/:productId" element={<ProductPage />} />
              <Route path="/about" element={<About />} />
              <Route path="/login" element={<Login />} />
              <Route path="/create-account" element={<CreateAccount />} />
              <Route path="*" element={<p className="status">Page not found.</p>} />
            </Routes>
          </main>
          <Footer />
          <ChatWidget />
        </ChatResultsProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
