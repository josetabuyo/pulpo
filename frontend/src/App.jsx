import { Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import BotPage from './pages/BotPage.jsx'
import NewBotPage from './pages/NewBotPage.jsx'
import EmbedFlowPage from './pages/EmbedFlowPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import RequireAuth from './components/RequireAuth.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route path="/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
      {/* URL directa a la sección Arquitectura del dashboard */}
      <Route path="/dashboard/arquitectura" element={<Navigate to="/dashboard?arquitectura=1" replace />} />
      <Route path="/bot" element={<RequireAuth><BotPage /></RequireAuth>} />
      <Route path="/bot/:botId" element={<RequireAuth><BotPage /></RequireAuth>} />
      <Route path="/bot/nueva" element={<RequireAuth><NewBotPage /></RequireAuth>} />
      {/* Solo-diagrama, sin login: usada por scripts/generate_e2e_report.py para
          capturar el flow real en vez de un screenshot recortado a mano. */}
      <Route path="/embed/flow/:botId" element={<EmbedFlowPage />} />
      {/* Chat público/allowlist standalone, UN chat puntual de un bot
          (2026-07-23: un bot puede tener N chats) -- ChatPage/PulpoChatWidget
          deciden solos si hace falta login (GET
          /api/chat/{botId}/{chatId}/config es siempre público). No pasa por
          el dashboard. */}
      <Route path="/chat/:botId/:chatId" element={<ChatPage />} />
      <Route path="/chat/:botId/:chatId/c/:conversationId" element={<ChatPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
