import { Navigate, useParams } from "react-router-dom";

export function ComparePage() {
  const { runId = "" } = useParams();
  return <Navigate to={`/runs/${runId}?tab=sensitivity`} replace />;
}
