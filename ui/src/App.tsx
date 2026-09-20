import { Routes, Route, Navigate } from 'react-router-dom';
import HomePage from './pages/HomePage';
import ProcessingPage from './pages/ProcessingPage';
import VideoPage from './pages/VideoPage';
import ConversationPage from './pages/ConversationPage';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/videos/:videoId/processing" element={<ProcessingPage />} />
      <Route path="/videos/:videoId" element={<VideoPage />} />
      <Route path="/chats/:conversationId" element={<ConversationPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
