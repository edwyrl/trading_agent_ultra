export function EventStudyDeepPanel({ eventStudy }: { eventStudy: { event_count?: number } }) {
  return <div className="empty-state">EventStudyDeepPanel compatibility wrapper ({eventStudy.event_count ?? 0} events).</div>;
}
