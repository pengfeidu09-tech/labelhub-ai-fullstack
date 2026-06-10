import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import HomePage from './pages/HomePage';
import MainLayout from './layouts/MainLayout';
import OwnerDashboard from './pages/owner/OwnerDashboard';
import TaskListPage from './pages/owner/TaskListPage';
import TaskDetailPage from './pages/owner/TaskDetailPage';
import TemplatePage from './pages/owner/TemplatePage';
import TemplateDesignerPage from './pages/owner/TemplateDesignerPage';
import DatasetPage from './pages/owner/DatasetPage';
import ExportPage from './pages/owner/ExportPage';
import AuditLogPage from './pages/owner/AuditLogPage';
import AnnotationPage from './pages/owner/AnnotationPage';
import RubricLibraryPage from './pages/owner/RubricLibraryPage';
import TaskResultsPage from './pages/owner/TaskResultsPage';
import AgentPage from './pages/owner/AgentPage';
import TaskMarketPage from './pages/labeler/TaskMarketPage';
import LabelWorkbenchPage from './pages/labeler/LabelWorkbenchPage';
import MySubmissionsPage from './pages/labeler/MySubmissionsPage';
import WorkReportPage from './pages/labeler/WorkReportPage';
import ReviewQueuePage from './pages/reviewer/ReviewQueuePage';
import ReviewDetailPage from './pages/reviewer/ReviewDetailPage';
import NotFound from './components/common/NotFound';

function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/owner" element={<MainLayout />}>
            <Route index element={<OwnerDashboard />} />
            <Route path="tasks" element={<TaskListPage />} />
            <Route path="tasks/:taskId" element={<TaskDetailPage />} />
            <Route path="tasks/:taskId/results" element={<TaskResultsPage />} />
            <Route path="templates" element={<TemplatePage />} />
            <Route path="templates/designer/:templateId" element={<TemplateDesignerPage />} />
            <Route path="templates/:templateId/designer" element={<TemplateDesignerPage />} />
            <Route path="datasets" element={<DatasetPage />} />
            <Route path="exports" element={<ExportPage />} />
            <Route path="annotations" element={<AnnotationPage />} />
            <Route path="audit-logs" element={<AuditLogPage />} />
            <Route path="rubrics" element={<RubricLibraryPage />} />
            <Route path="agent" element={<AgentPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
          <Route path="/labeler" element={<MainLayout />}>
            <Route index element={<TaskMarketPage />} />
            <Route path="tasks" element={<TaskMarketPage />} />
            <Route path="workbench" element={<LabelWorkbenchPage />} />
            <Route path="submissions" element={<MySubmissionsPage />} />
            <Route path="reports" element={<WorkReportPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
          <Route path="/reviewer" element={<MainLayout />}>
            <Route index element={<ReviewQueuePage />} />
            <Route path="queue" element={<ReviewQueuePage />} />
            <Route path="reviews/:submissionId" element={<ReviewDetailPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
