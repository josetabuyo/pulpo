/**
 * ChatPage — página pública/allowlist standalone de UN chat puntual de un
 * bot, estilo ChatGPT. Ruta SIN RequireAuth (precedente: /embed/flow/:botId
 * ya es pública en el SPA, ver App.jsx) -- PulpoChatWidget decide sola si
 * hace falta login, pidiendo GET /api/chat/{botId}/{chatId}/config primero
 * (siempre público) y dejando que las rutas de conversaciones devuelvan 401
 * login_required si hace falta.
 *
 * 2026-07-23: wrapper fino -- toda la lógica vive en PulpoChatWidget
 * (compartida con el uso embebido en ChatsTab.jsx). Este componente solo
 * resuelve :chatId/:conversationId de la URL y los sincroniza con el
 * widget vía navigate().
 */
import { useNavigate, useParams } from 'react-router-dom'
import PulpoChatWidget from '../components/chat/PulpoChatWidget.jsx'

export default function ChatPage() {
  const { botId, chatId, conversationId } = useParams()
  const navigate = useNavigate()

  return (
    <PulpoChatWidget
      botId={botId}
      chatId={chatId}
      initialConversationId={conversationId ?? null}
      onConversationChange={id => {
        if (id) navigate(`/chat/${botId}/${chatId}/c/${id}`, { replace: true })
      }}
      fullscreen
    />
  )
}
