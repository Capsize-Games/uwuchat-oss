"""Supported PII entity types and detection threshold."""

SUPPORTED_ENTITIES: tuple[str, ...] = (
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "CREDIT_CARD",
    "IBAN_CODE",
    "LOCATION",
)

MIN_CONFIDENCE = 0.6
# Candidates for future PII detection (require Presidio model support
# and evaluation against false-positive rate on our message corpus):
#   DATE_TIME, IP_ADDRESS, URL, AGE, NRIC, MEDICAL_LICENSE
