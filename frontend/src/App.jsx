import { Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import ConnectPage from './pages/ConnectPage.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/connect" element={<ConnectPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
