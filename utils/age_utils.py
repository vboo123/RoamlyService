from typing import List

class AgeUtils:
    @staticmethod
    def classify_age(age: int) -> str:
        """
        Classify age into age groups
        Args:
            age: Integer age value
        Returns:
            "young" for ages under 30, "old" for 30 and above
        """
        return "young" if age < 30 else "old" 