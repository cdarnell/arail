import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import DashboardClient from './components/DashboardClient';
import NotebookPanel from './components/NotebookPanel';
import JupyterLabPanel from './components/JupyterLabPanel';
import GrafanaEmbed from './components/GrafanaEmbed';
import './theme.css';

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<DashboardClient />} />
        <Route path="/notebook" element={<NotebookPanel />} />
        <Route path="/jupyterlab" element={<JupyterLabPanel />} />
        <Route path="/grafana" element={<GrafanaEmbed />} />
      </Routes>
    </Router>
  );
}
