import { Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import EmpresaPage from './pages/EmpresaPage.jsx'
import NuevaEmpresaPage from './pages/NuevaEmpresaPage.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      {/* URL directa a la sección Arquitectura del dashboard */}
      <Route path="/dashboard/arquitectura" element={<Navigate to="/dashboard?arquitectura=1" replace />} />
      <Route path="/empresa" element={<EmpresaPage />} />
      <Route path="/empresa/:botId" element={<EmpresaPage />} />
      <Route path="/empresa/nueva" element={<NuevaEmpresaPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
