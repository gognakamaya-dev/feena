from ._b import B
APP, PREFIX = "SurveyLab", "SL"
BUGS = [
    B(1, "backend", "easy", "medium", "response_validation", "Rating answers outside the allowed range are accepted.", "Rating value 11", "POST public response with answer 11 to rating question", "400", "201"),
    B(2, "frontend", "easy", "low", "rating_summary", "Average rating is rounded to an integer in the UI summary.", "Non-integer average", "View ratings 4,5,4", "4.33", "4"),
    B(3, "backend", "medium", "medium", "survey_status", "Closed surveys still accept responses.", "Survey status closed", "POST response to survey 3", "403/409/410", "201"),
    B(4, "business_logic", "medium", "medium", "choice_analytics", "Choice percentages use total responses as denominator instead of respondents who answered the question.", "Optional choice question skipped by some respondents", "GET /api/surveys/1/analytics", "Email 50 / Phone 25 / Chat 25", "Email 33 / Phone 17 / Chat 17"),
    B(5, "security", "medium", "critical", "analytics_access", "Analytics endpoint is not scoped to organization.", "Foreign survey id", "As Acme admin GET /api/surveys/4/analytics", "404", "200 with Globex data"),
    B(6, "business_logic", "hard", "medium", "survey_lifecycle", "Required questions can be added to a live survey, making existing responses invalid.", "Add required question to live survey with responses", "Launch survey with responses > POST required question", "409", "201", True),
]
