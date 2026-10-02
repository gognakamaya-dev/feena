from ._b import B
APP, PREFIX = "TaskBoard", "TB"
BUGS = [
    B(1, "frontend", "easy", "low", "task_search", "Client-side task search is case-sensitive.", "Search text whose case differs from the title", "Open Tasks > Search 'login' > Observe 'Fix Login bug' missing", "Case-insensitive match", "No match unless case is identical"),
    B(2, "backend", "easy", "medium", "task_update_validation", "PATCH /api/tasks/<id> accepts arbitrary status strings.", "status not in todo/doing/done", "PATCH task with status 'banana'", "400 validation error", "200 and task stored with status 'banana'"),
    B(3, "database", "medium", "medium", "project_stats", "Project stats count soft-deleted tasks in status buckets.", "At least one deleted task", "Create task > Delete it > GET /stats", "Status buckets equal the visible task count", "Deleted task still counted in 'todo'", True),
    B(4, "security", "medium", "high", "task_authorization", "Viewer role can modify tasks through PATCH (role not enforced).", "Logged in as viewer", "Login as viewer@acme.test > PATCH /api/tasks/1 {title}", "403", "200 and title changed"),
    B(5, "business_logic", "hard", "high", "ownership_transfer", "After transferring ownership the previous owner keeps owner rights.", "Transfer ownership then act as old owner", "Create project > Add member > Transfer ownership to member > Old owner archives project", "403 for the former owner", "Archive succeeds for former owner", True),
    B(6, "business_logic", "very_hard", "medium", "subtask_completion", "Parent completion only checks the first subtask, so later open subtasks are ignored.", "Parent with 2+ subtasks, first done, later open", "Create parent > Add two subtasks > Complete first subtask > Complete parent", "409 until all subtasks done", "Parent marked done with open subtask", True),
]
