from ._b import B
APP, PREFIX = "TeamPulse", "TP"
BUGS = [
    B(1, "backend", "easy", "low", "pulse_validation", "Pulse score range (1-5) is not enforced.", "score 9 or 0", "POST /api/pulse {score:9}", "400", "201"),
    B(2, "frontend", "easy", "low", "headcount_summary", "Headcount summary counts terminated employees.", "Terminated employee in list", "Open Employees tab", "Active employees only", "All rows counted"),
    B(3, "backend", "medium", "medium", "employee_filter", "team_id filter is ignored when a search query is present.", "q and team_id both set", "GET /api/employees?team_id=1&q=Employee", "Only team 1 employees", "Employees from all teams"),
    B(4, "security", "medium", "high", "employee_privacy", "salary_band is exposed to non-admin roles.", "Member lists employees", "Login as member > GET /api/employees", "salary_band omitted", "salary_band present"),
    B(5, "business_logic", "medium", "medium", "engagement_rate", "Response rate denominator includes terminated employees.", "Terminated employees exist", "GET /api/analytics/engagement", "responses / active employees", "Rate computed over all employees"),
    B(6, "business_logic", "hard", "high", "rehire", "Rehiring leaves terminated_on set so headcount analytics keep excluding the employee.", "Terminate then rehire", "GET headcount > Terminate employee > Rehire > GET headcount", "headcount back to original", "headcount remains reduced", True),
]
