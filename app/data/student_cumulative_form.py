from copy import deepcopy


FORM_KEY = "student-cumulative-form"


def _options(labels: list[str]) -> list[dict[str, str]]:
    return [
        {"value": label.lower().replace("/", "_").replace(" ", "_"), "label": label}
        for label in labels
    ]


FORM_DEFINITION = {
    "form_key": FORM_KEY,
    "form_number": "OVPAA-SAS-GCO-04",
    "title": "Student Cumulative Form",
    "version": 1,
    "sections": [
        {
            "key": "privacy-and-certification",
            "title": "Section 1 – Data Privacy and Certification",
            "description": (
                "Pamantasan ng Lungsod ng San Pablo (PLSP) is committed to protecting your personal and "
                "sensitive information in accordance with the Data Privacy Act of 2012, its Implementing "
                "Rules and Regulations, and applicable institutional policies. Your information may be "
                "collected, processed, stored, and shared with authorized persons, partner organizations, "
                "or government agencies when necessary and permitted by law, for legitimate academic, "
                "student services, research, or institutional purposes. Information provided for health, "
                "safety, and support purposes will be handled with appropriate confidentiality and used to "
                "facilitate appropriate assistance, intervention, or referral when necessary."
            ),
            "questions": [
                {"key": "privacy_consent", "label": "I have read and understood the above Privacy Notice and agree to the collection and processing of my information for the stated purposes.", "type": "checkbox", "required": True},
                {"key": "certification", "label": "I certify that the information I provide in this form is true, complete, and accurate to the best of my knowledge.", "type": "checkbox", "required": True},
            ],
        },
        {
            "key": "program-enrolled",
            "title": "Section 2 – Program Enrolled",
            "questions": [
                {"key": "program_course", "label": "Program/Course", "type": "short_text", "required": True},
                {"key": "year_level", "label": "Year Level", "type": "select", "required": True, "options": _options(["1st", "2nd", "3rd", "4th", "5th"])},
            ],
        },
        {
            "key": "personal-and-family-information",
            "title": "Section 3 – Personal and Family Information",
            "questions": [
                {"key": "last_name", "label": "Last Name", "type": "short_text", "required": True},
                {"key": "first_name", "label": "First Name", "type": "short_text", "required": True},
                {"key": "middle_name", "label": "Middle Name", "type": "short_text", "required": True},
                {"key": "date_of_birth", "label": "Date of Birth", "type": "date", "required": True},
                {"key": "age", "label": "Age", "type": "number", "required": True},
                {"key": "sex", "label": "Sex", "type": "short_text", "required": True, "placeholder": "Male/Female"},
                {"key": "civil_status", "label": "Civil Status", "type": "short_text", "required": True},
                {"key": "complete_address", "label": "Complete Address", "type": "long_text", "required": True},
                {"key": "mobile_number", "label": "Mobile Number", "type": "tel", "required": True},
                {"key": "email_address", "label": "Email Address", "type": "email", "required": True, "read_only": True},
                {"key": "father_name", "label": "Name of Father", "type": "short_text", "required": True},
                {"key": "father_occupation", "label": "Father's Occupation", "type": "short_text", "required": True},
                {"key": "father_contact_number", "label": "Father's Contact Number", "type": "tel", "required": True},
                {"key": "mother_name", "label": "Name of Mother", "type": "short_text", "required": True},
                {"key": "mother_occupation", "label": "Mother's Occupation", "type": "short_text", "required": True},
                {"key": "mother_contact_number", "label": "Mother's Contact Number", "type": "tel", "required": True},
                {"key": "siblings_details", "label": "Siblings – Name, Civil Status, and Occupation", "type": "long_text", "required": False, "placeholder": "Optional"},
                {"key": "lives_with_parents", "label": "Do you currently live with your parents?", "type": "yes_no", "required": True, "options": _options(["Yes", "No"])},
            ],
        },
        {
            "key": "guardian",
            "title": "Section 4 – Guardian",
            "questions": [
                {"key": "has_guardian_contact", "label": "Do you have a parent/guardian who should be contacted regarding your welfare or support?", "type": "yes_no", "required": True, "options": _options(["Yes", "No"])},
                {"key": "guardian_name", "label": "Name of Guardian", "type": "short_text", "required": True, "condition": {"question": "has_guardian_contact", "equals": "yes"}},
                {"key": "guardian_relationship", "label": "Relationship to Student", "type": "short_text", "required": True, "condition": {"question": "has_guardian_contact", "equals": "yes"}},
                {"key": "guardian_contact_number", "label": "Guardian Contact Number", "type": "tel", "required": True, "condition": {"question": "has_guardian_contact", "equals": "yes"}},
            ],
        },
        {
            "key": "educational-background",
            "title": "Section 5 – Educational Background",
            "questions": [
                {"key": "senior_high_school", "label": "Senior High School", "type": "short_text", "required": True},
                {"key": "year_graduated", "label": "Year Graduated", "type": "number", "required": True},
                {"key": "academic_awards", "label": "Academic Awards/Recognition, if any", "type": "long_text", "required": False, "placeholder": "Optional"},
                {"key": "is_transferee", "label": "Are you a transferee?", "type": "yes_no", "required": True, "options": _options(["Yes", "No"])},
            ],
        },
        {
            "key": "transfer-student-information",
            "title": "Section 6 – Transfer Student Information",
            "description": "Display only if “Yes” to transferee.",
            "condition": {"question": "is_transferee", "equals": "yes"},
            "questions": [
                {"key": "previous_school", "label": "Previous School", "type": "short_text", "required": True},
                {"key": "previous_program_course", "label": "Program/Course Previously Enrolled", "type": "short_text", "required": True},
                {"key": "last_year_attended", "label": "Last Year Attended", "type": "short_text", "required": True},
            ],
        },
        {
            "key": "health-and-well-being",
            "title": "Section 7 – Health and Well-Being",
            "description": (
                "This information is collected only to help identify appropriate support and "
                "accommodations. You may choose not to disclose details you are uncomfortable sharing."
            ),
            "questions": [
                {"key": "has_health_condition", "label": "Do you have any health, psychological, emotional, physical, or medical condition that may affect your studies or school participation?", "type": "single_choice", "required": True, "options": _options(["Yes", "No", "Prefer not to answer"])},
            ],
        },
        {
            "key": "conditions-and-support-needs",
            "title": "Section 8 – Conditions and Support Needs",
            "description": "Display if “Yes” to the health and well-being question.",
            "condition": {"question": "has_health_condition", "equals": "yes"},
            "questions": [
                {"key": "health_condition_details", "label": "Please specify the condition or concern, if you are comfortable sharing", "type": "long_text", "required": False, "placeholder": "Optional"},
                {"key": "activities_to_avoid", "label": "Are there activities or situations you need to avoid because of a health or safety concern?", "type": "long_text", "required": False, "placeholder": "Optional"},
                {"key": "needs_school_support", "label": "Do you need any specific support or accommodation in school?", "type": "single_choice", "required": True, "options": _options(["No", "Yes", "Not sure", "Prefer not to answer"])},
            ],
        },
        {
            "key": "support-needed",
            "title": "Section 9 – Support Needed",
            "description": "Display if “Yes” or “Not sure” to the support/accommodation question.",
            "condition": {"question": "needs_school_support", "in": ["yes", "not_sure"]},
            "questions": [
                {"key": "support_types", "label": "What support would be helpful to you?", "type": "multi_select", "required": True, "options": _options(["Counseling", "Academic support", "Health/medical support", "Accessibility/accommodation", "Financial or basic-needs support", "Family/social support", "Referral to another professional/service", "Other"])},
                {"key": "support_other", "label": "Other support – please specify", "type": "short_text", "required": True, "condition": {"question": "support_types", "contains": "other"}},
                {"key": "support_additional_information", "label": "Please provide additional information, if you wish", "type": "long_text", "required": False, "placeholder": "Optional"},
            ],
        },
        {
            "key": "allergies",
            "title": "Section 10 – Allergies",
            "questions": [
                {"key": "has_allergies", "label": "Do you have any known food or medication allergies?", "type": "single_choice", "required": True, "options": _options(["Yes", "No", "Prefer not to answer"])},
                {"key": "allergy_details", "label": "If yes, please specify", "type": "short_text", "required": False, "placeholder": "Optional", "condition": {"question": "has_allergies", "equals": "yes"}},
            ],
        },
    ],
}


def get_form_definition() -> dict:
    return deepcopy(FORM_DEFINITION)
