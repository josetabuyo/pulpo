import { Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import BotPage from './pages/BotPage.jsx'
import NewBotPage from './pages/NewBotPage.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      {/* URL directa a la sección Arquitectura del dashboard */}
      <Route path="/dashboard/arquitectura" element={<Navigate to="/dashboard?arquitectura=1" replace />} />
      <Route path="/bot" element={<BotPage />} />
      <Route path="/bot/:botId" element={<BotPage />} />
      <Route path="/bot/nueva" element={<NewBotPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
