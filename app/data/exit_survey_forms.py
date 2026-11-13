from copy import deepcopy


SHIFTING_FORM_KEY = "exit-interview-shifting-transferring"
GRADUATING_FORM_KEY = "exit-survey-graduating-students"
REQUESTABLE_FORM_KEYS = (SHIFTING_FORM_KEY, GRADUATING_FORM_KEY)


def _options(values: list[str]) -> list[dict[str, str]]:
    return [
        {"value": str(index), "label": value}
        for index, value in enumerate(values, start=1)
    ]


def _choice(key: str, label: str, values: list[str], required: bool = True) -> dict:
    return {
        "key": key,
        "label": label,
        "type": "single_choice",
        "required": required,
        "options": _options(values),
    }


_factor_options = [
    "Academic factor — Lack of interest in the current program",
    "Academic factor — Difficulty in meeting academic requirements",
    "Academic factor — Retention for board programs",
    "Academic factor — Dissatisfaction with the quality of teaching",
    "Academic factor — Uncertain career direction",
    "Academic factor — Class schedule concerns or conflicts",
    "Personal factor — Changes in interests or goals",
    "Personal factor — Desire to work",
    "Personal factor — Mental health concerns",
    "Personal factor — Health problem",
    "Personal factor — Financial problem",
    "Personal factor — Family problem",
    "Personal factor — Recommendation from parents/guardians",
    "Interpersonal/school environment — Problem with classmates or schoolmates",
    "Interpersonal/school environment — Problem with teachers/University personnel",
    "Interpersonal/school environment — Problem with university facilities and resources",
    "Other",
]

SHIFTING_TRANSFERING_FORM = {
    "form_key": SHIFTING_FORM_KEY,
    "form_number": "OVPAA-SAS-GCO-03B",
    "title": "Exit Interview Form for Shifting / Transferring",
    "version": 1,
    "access_mode": "request",
    "sections": [
        {
            "key": "student-information",
            "title": "Student Information",
            "questions": [
                {"key": "name", "label": "Name", "type": "short_text", "required": True},
                {"key": "interview_date", "label": "Date", "type": "date", "required": True},
                {"key": "program_year_section", "label": "Program, Year and Section", "type": "short_text", "required": True},
                {"key": "contact_number", "label": "Contact Number", "type": "tel", "required": True},
                {
                    "key": "leaving_scope",
                    "label": "Are you planning to leave the University, your Program, or both?",
                    "type": "multi_select",
                    "required": True,
                    "options": [
                        {"value": "university", "label": "University"},
                        {"value": "program", "label": "Program"},
                    ],
                },
            ],
        },
        {
            "key": "decision-factors",
            "title": "Factors Influencing Your Decision",
            "description": "Select all factors that influenced your decision to leave the University or Program.",
            "questions": [
                {
                    "key": "decision_factors",
                    "label": "Factors that influenced your decision",
                    "type": "multi_select",
                    "required": True,
                    "options": [
                        {"value": f"factor-{index:02d}", "label": value}
                        for index, value in enumerate(_factor_options, start=1)
                    ],
                },
                {
                    "key": "other_factor_details",
                    "label": "Other factor — please specify",
                    "type": "short_text",
                    "required": False,
                    "condition": {"question": "decision_factors", "contains": "factor-17"},
                },
            ],
        },
        {
            "key": "transfer-plans",
            "title": "Transfer or Shifting Plans",
            "questions": [
                {"key": "planned_school_or_program", "label": "What school or program are you planning to transfer to or enroll in?", "type": "long_text", "required": False},
                {"key": "challenges_and_concerns", "label": "What specific challenges, concerns, or unmet expectations influenced your decision to shift programs or transfer universities?", "type": "long_text", "required": False},
                {"key": "additional_comments", "label": "Is there any additional comment or suggestion you would like to share to help us improve the University or Program?", "type": "long_text", "required": False},
            ],
        },
    ],
}


_rating_options = [
    "1 — Very Poor",
    "2",
    "3",
    "4",
    "5 — Excellent",
]
_satisfaction_options = [
    "1 — Not Satisfied",
    "2",
    "3",
    "4",
    "5 — Very Satisfied",
]


def _rating_questions(prefix: str, labels: list[str], options: list[str]) -> list[dict]:
    return [
        _choice(f"{prefix}_{index:02d}", label, options)
        for index, label in enumerate(labels, start=1)
    ]


GRADUATING_STUDENTS_FORM = {
    "form_key": GRADUATING_FORM_KEY,
    "form_number": "OVPAA-SAS-GCO-03A",
    "title": "Exit Survey Form for Graduating Students",
    "version": 1,
    "access_mode": "request",
    "sections": [
        {
            "key": "informed-consent",
            "title": "Section 1 — Data Privacy and Consent",
            "description": (
                "I understand that the Dalubhasaan ng Lungsod ng San Pablo (PLSP) is committed to protecting my "
                "personal and sensitive information in accordance with the Data Privacy Act of 2012, its "
                "Implementing Rules and Regulations, and applicable institutional policies. I understand that "
                "the information I provide may be collected, processed, and used for legitimate student services, "
                "institutional planning, research, evaluation, and quality improvement purposes. Information may "
                "be shared with authorized personnel, partner organizations, or government agencies when required "
                "or permitted by law. I understand that my participation is voluntary and that I may choose not "
                "to answer questions that I am uncomfortable answering."
            ),
            "questions": [
                {
                    "key": "survey_consent",
                    "label": "I have read and understood the information above and voluntarily agree to participate in this survey.",
                    "type": "checkbox",
                    "required": True,
                }
            ],
        },
        {
            "key": "student-information",
            "title": "Section 2 — Student Information",
            "questions": [
                {"key": "last_name", "label": "Last Name", "type": "short_text", "required": True},
                {"key": "first_name", "label": "First Name", "type": "short_text", "required": True},
                {"key": "middle_name", "label": "Middle Name", "type": "short_text", "required": False},
                {"key": "program_course", "label": "Program/Course", "type": "short_text", "required": True},
                {"key": "college", "label": "College", "type": "short_text", "required": True},
                {"key": "graduation_year", "label": "Year Graduated / Expected Graduation Year", "type": "number", "required": True},
            ],
        },
        {
            "key": "career-plans-readiness",
            "title": "Section 3 — Career Plans and Readiness",
            "questions": [
                {
                    "key": "plans_after_graduation",
                    "label": "What are your plans after graduation? Select all that apply.",
                    "type": "multi_select",
                    "required": True,
                    "options": [
                        {"value": "seek_employment", "label": "Seek employment"},
                        {"value": "continue_studies", "label": "Continue my studies"},
                        {"value": "licensure_exam", "label": "Take a licensure/certification examination"},
                        {"value": "start_business", "label": "Start or expand a business"},
                        {"value": "employment_abroad", "label": "Seek employment abroad"},
                        {"value": "professional_exam", "label": "Prepare for a career or professional examination"},
                        {"value": "take_break", "label": "Take a break before pursuing my next step"},
                        {"value": "exploring", "label": "I am still exploring my options"},
                        {"value": "other", "label": "Other"},
                    ],
                },
                {"key": "plans_other", "label": "Other plan — please specify", "type": "short_text", "required": False, "condition": {"question": "plans_after_graduation", "contains": "other"}},
                {"key": "career_aspirations", "label": "What are your career aspirations or long-term employment goals?", "type": "long_text", "required": False},
                {"key": "career_plan_steps", "label": "How do you plan to achieve your career goals?", "type": "long_text", "required": False},
                {"key": "career_contribution", "label": "How do you see your career contributing to your family, community, or society?", "type": "long_text", "required": False},
                _choice("employment_readiness", "How would you rate your overall readiness for employment or your next career step?", _rating_options),
                _choice("career_consultation_interest", "Would you like to discuss your career plans or readiness further with the Guidance and Counseling Office?", ["Yes", "No", "Maybe"]),
            ],
        },
        {
            "key": "academic-experience",
            "title": "Section 4 — Academic Experience",
            "layout": "rating_matrix",
            "description": "Rate your experience with each area from 1 (Very Poor) to 5 (Excellent).",
            "questions": _rating_questions("academic_experience", [
                "Lessons taught in your program",
                "Teaching effectiveness of faculty",
                "Knowledge gained from the program",
                "Skills gained from the program",
                "Values developed from the program",
                "Practical experiences, including hands-on activities and internship",
            ], _rating_options),
        },
        {
            "key": "student-support-services",
            "title": "Section 5 — Student Support Services",
            "layout": "rating_matrix",
            "description": "Rate each office/service from 1 (Not Satisfied) to 5 (Very Satisfied).",
            "questions": _rating_questions("student_service", [
                "Guidance and Counseling Office",
                "Faculty Members",
                "Dean's Office",
                "EMISO",
                "Library",
                "Laboratories",
                "External Linkages / Internship Support",
            ], _satisfaction_options),
        },
        {
            "key": "other-plsp-services",
            "title": "Section 6 — Other PLSP Offices and Services",
            "layout": "rating_matrix",
            "description": "Rate each office/service from 1 (Not Satisfied) to 5 (Very Satisfied).",
            "questions": _rating_questions("other_service", [
                "Finance Office",
                "Registrar",
                "Cafeteria/Canteen",
                "Health Clinic",
                "Admission Office",
                "Research and Development Office",
            ], _satisfaction_options),
        },
        {
            "key": "feedback-recommendations",
            "title": "Section 7 — Feedback and Recommendations",
            "questions": [
                {"key": "service_improvements", "label": "What suggestions do you have to improve PLSP's academic and student support services for future students?", "type": "long_text", "required": False},
                {"key": "most_appreciated", "label": "What is one thing you appreciate most about your experience at PLSP?", "type": "long_text", "required": False},
                {"key": "one_area_to_improve", "label": "What is one area that PLSP could improve?", "type": "long_text", "required": False},
            ],
        },
        {
            "key": "alumni-connection",
            "title": "Section 8 — Alumni Connection",
            "questions": [
                _choice("future_alumni_participation", "Would you be willing to participate in future alumni surveys or activities?", ["Yes", "No", "Maybe"]),
                _choice("receive_alumni_information", "Would you like to receive information about future PLSP alumni activities?", ["Yes", "No"]),
            ],
        },
    ],
}


EXIT_SURVEY_FORMS = (
    SHIFTING_TRANSFERING_FORM,
    GRADUATING_STUDENTS_FORM,
)


def get_exit_survey_forms() -> list[dict]:
    return deepcopy(list(EXIT_SURVEY_FORMS))
