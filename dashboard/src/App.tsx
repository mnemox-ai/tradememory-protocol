import { Routes, Route } from 'react-router-dom';
import Nav from './components/layout/Nav';
import OverviewPage from './pages/OverviewPage';
import IntelligencePage from './pages/IntelligencePage';
import StrategiesPage from './pages/StrategiesPage';
import ReflectionsPage from './pages/ReflectionsPage';
import DreamsPage from './pages/DreamsPage';
import EvolutionPage from './pages/EvolutionPage';

export default function App() {
  return (
    <>
      <Nav />
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/intelligence" element={<IntelligencePage />} />
        <Route path="/strategies" element={<StrategiesPage />} />
        <Route path="/reflections" element={<ReflectionsPage />} />
        <Route path="/dreams" element={<DreamsPage />} />
        <Route path="/evolution" element={<EvolutionPage />} />
      </Routes>
    </>
  );
}
