from ._b import B
APP, PREFIX = "AssetManager", "AM"
BUGS = [
    B(1, "backend", "easy", "medium", "upload_validation", "Upload size limit (50 MB) is not enforced.", "size_bytes > 50 MiB", "POST /api/assets with size 62914560", "400", "201"),
    B(2, "frontend", "easy", "low", "size_summary", "Total size summary divides by 1,000,000 instead of 1,048,576.", "Any size", "Open Assets tab with a 5 MiB asset", "Total: 5.0 MB", "Total: 5.2 MB"),
    B(3, "database", "medium", "medium", "storage_usage", "Storage usage still counts soft-deleted assets.", "Deleted asset", "GET /api/storage > DELETE asset 4 > GET /api/storage", "used decreases by asset size", "used unchanged", True),
    B(4, "security", "medium", "high", "share_links", "Revoked share links keep working until they expire.", "Revoked share", "Create share > Revoke > GET public link", "404", "200 with asset metadata", True),
    B(5, "business_logic", "hard", "medium", "folder_move", "Moving an asset skips the unique-name check within the destination folder.", "Same filename in two folders", "Upload dup.png to folders 1 and 2 > Move second into folder 1", "409", "200 duplicate names", True),
    B(6, "security", "very_hard", "high", "share_links", "A deleted asset remains reachable through an existing public share link.", "Share link created before deletion", "Create share > Delete asset > GET public link", "404", "200", True),
]
