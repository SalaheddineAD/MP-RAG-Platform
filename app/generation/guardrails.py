import re
from typing import Dict, Tuple


class Guardrails:
    """Input/output safety and cost controls."""
    
    # Manufacturing-specific blocklist
    BLOCKLIST = {"proprietary", "confidential", "trade secret", "internal only"}
    
    PII_PATTERNS = [
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b\d{16}\b',  # Credit card
    ]
    
    @staticmethod
    def check_input(text: str) -> Tuple[bool, str]:
        """Return (is_safe, reason)."""
        text_lower = text.lower()
        
        # Check blocklist
        for term in Guardrails.BLOCKLIST:
            if term in text_lower:
                return False, f"Input contains blocked term: {term}"
        
        # Check PII
        for pattern in Guardrails.PII_PATTERNS:
            if re.search(pattern, text):
                return False, "Input may contain PII"
        
        # Cost guardrail: extremely long queries
        if len(text) > 10000:
            return False, "Query exceeds maximum length"
        
        return True, ""
    
    @staticmethod
    def check_output(text: str) -> Tuple[bool, str]:
        """Basic output filtering."""
        if len(text) < 10:
            return False, "Output too short, likely an error"
        
        # Check for refusal patterns that indicate hallucination
        refusal_phrases = ["i don't have sufficient information", "not mentioned in"]
        if any(p in text.lower() for p in refusal_phrases):
            # This is actually good — means it didn't hallucinate
            pass
        
        return True, ""