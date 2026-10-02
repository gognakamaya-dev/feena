from ._b import B
APP, PREFIX = "RecruitFlow", "RF"
BUGS = [
    B(1, "backend", "easy", "medium", "application_validation", "Candidates can apply to closed jobs.", "Job status closed", "POST public apply on job 3", "409", "201"),
    B(2, "frontend", "easy", "low", "candidate_summary", "'Active candidates' count includes hired and rejected candidates.", "Mixed stages", "Open Candidates tab", "Only in-progress counted", "All rows counted"),
    B(3, "business_logic", "medium", "high", "stage_machine", "Pipeline stages can be skipped (applied -> offer).", "Jump over stages", "Apply > POST stage 'offer'", "409", "200"),
    B(4, "security", "medium", "critical", "application_access", "Application detail is not scoped to organization.", "Foreign application id", "As Acme admin GET /api/applications/7", "404", "200"),
    B(5, "business_logic", "hard", "high", "hiring", "Hiring a candidate does not close the job.", "Application reaches hired", "Apply > screen > interview > offer > hired > GET pipeline", "Job closed", "Job still open", True),
    B(6, "business_logic", "hard", "medium", "interview_scores", "Average score treats unscored interviews as 0.", "Scheduled interview without feedback", "Schedule two interviews > Feedback 5 on one > GET application", "average_score 5", "average_score 2.5", True),
]
