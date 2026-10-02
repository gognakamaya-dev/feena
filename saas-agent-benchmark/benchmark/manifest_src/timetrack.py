from ._b import B
APP, PREFIX = "TimeTrack", "TT"
BUGS = [
    B(1, "backend", "easy", "medium", "entry_validation", "Entries with end before start are accepted.", "end_at < start_at", "POST /api/entries with reversed times", "400", "201 with negative minutes"),
    B(2, "frontend", "easy", "low", "hours_summary", "Total hours is rounded to whole hours.", "Fractional hours", "View entries totalling 150 minutes", "2.5", "3"),
    B(3, "business_logic", "medium", "high", "overlap_detection", "Manual entries can overlap each other (only running timers are checked).", "Overlapping manual entries", "Add 09-11 > Add 10-12 same day", "409", "201 overlapping"),
    B(4, "security", "medium", "high", "timesheet_approval", "Any member can approve timesheets, including their own.", "Member role", "Member submits week > Member approves own timesheet", "403", "200 approved"),
    B(5, "business_logic", "hard", "high", "timesheet_locking", "Entries remain editable after the timesheet week is approved.", "Edit after approval", "Submit week > Admin approves > PUT entry", "409 locked", "200 entry changed", True),
    B(6, "business_logic", "very_hard", "high", "weekly_report", "Overnight entries spanning Sunday->Monday are attributed fully to the starting week instead of being split.", "Entry crossing week boundary", "Add entry Sun 22:00 - Mon 04:00 > GET weekly report for Monday's week", "4 hours in the new week", "0 hours in new week (6h in old week)", True),
]
