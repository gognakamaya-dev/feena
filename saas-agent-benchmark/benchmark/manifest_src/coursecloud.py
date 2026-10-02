from ._b import B
APP, PREFIX = "CourseCloud", "CC"
BUGS = [
    B(1, "backend", "easy", "medium", "enrollment", "Students can enroll in unpublished (draft) courses.", "Draft course id", "As viewer POST /api/courses/3/enroll", "404/409", "201 enrolled"),
    B(2, "frontend", "easy", "low", "course_summary", "'Published courses' summary counts drafts too.", "Mixed course statuses", "Open Courses tab as admin", "Only published counted", "All rows counted"),
    B(3, "business_logic", "medium", "medium", "progress", "Progress percentage counts optional lessons as completed required work.", "Complete an optional lesson", "Enroll in course 1 > Complete one required lesson > Complete optional lesson", "33%", "67%"),
    B(4, "security", "medium", "high", "gradebook_access", "Students (viewer role) can read the course gradebook.", "viewer role", "As viewer GET /api/courses/1/gradebook", "403", "200 with all students' scores"),
    B(5, "business_logic", "hard", "high", "lesson_completion", "Completing the same lesson repeatedly inflates progress (duplicate completion rows).", "Repeated completion call", "Enroll > Complete lesson 1 twice > Read completed count", "completed = 1", "completed = 2; certificate reachable early", True),
    B(6, "business_logic", "very_hard", "high", "certificates", "Pass mark check rounds the percentage, so 69.5% passes a 70% threshold.", "Final grade between 69.5% and 70%", "Complete all required lessons > Record grades 139/200 > Request certificate", "409 below 70%", "Certificate issued", True),
]
