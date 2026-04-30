export function EventStudyPanel({ eventStudy }: { eventStudy: { event_count?: number } }) {
  return <div className="empty-state">EventStudyPanel compatibility wrapper ({eventStudy.event_count ?? 0} events).</div>;
}
