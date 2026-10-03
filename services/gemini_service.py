import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Using the recommended model for text analysis and generation
GEMINI_MODEL = "gemini-2.5-flash"

class ComplaintCategoryResponse(BaseModel):
    category: str = Field(description="The matching category from the predefined list.")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0.")
    reason: str = Field(description="Reason for selecting this category.")

class ComplaintPriorityResponse(BaseModel):
    priority: str = Field(description="One of: Low, Medium, High, Urgent.")
    reason: str = Field(description="Reason for suggesting this priority.")

class ComplaintDuplicateResponse(BaseModel):
    possible_duplicate: bool = Field(description="Whether the new complaint is a likely duplicate.")
    similar_complaint_id: int | None = Field(description="The ID of the similar complaint, if any.")
    reason: str = Field(description="Explanation of why it is or isn't a duplicate.")

class ComplaintAnalysisResponse(BaseModel):
    category: str = Field(description="The matching category from the predefined list.")
    priority: str = Field(description="One of: Low, Medium, High, Urgent.")
    summary: str = Field(description="A concise professional summary of the complaint.")
    department: str = Field(description="Suggested department to handle this.")
    next_action: str = Field(description="Suggested next action.")
    draft_response: str = Field(description="A professional draft response to the student.")

class GeminiService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"Failed to initialize Gemini client: {e}")

    def is_available(self) -> bool:
        return self.client is not None

    def analyze_category_and_priority(self, text: str, location_type: str, valid_categories: set[str]) -> dict | None:
        """Analyze a new complaint for category and priority."""
        if not self.is_available(): return None
        
        prompt = f"""
        Analyze this complaint text: "{text}"
        Location Type: {location_type}
        
        Valid categories are: {', '.join(valid_categories)}
        
        Return a JSON object with:
        - category (must be exactly one of the valid categories, or 'Other' if none match well)
        - priority (must be one of: Low, Medium, High, Urgent)
        - confidence (float between 0 and 1)
        - reason (brief explanation)
        """
        try:
            # We use a combined schema here to save API calls
            class CombinedResponse(BaseModel):
                category: str
                priority: str
                confidence: float
                reason: str

            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CombinedResponse,
                    temperature=0.1
                )
            )
            data = json.loads(response.text)
            
            # Validation
            if data.get('category') not in valid_categories:
                # Fallback to a safe default if the model hallucinates
                data['category'] = "Other College Issue" if location_type == 'College' else "Other Hostel Issue"
                
            if data.get('priority') not in {'Low', 'Medium', 'High', 'Urgent'}:
                data['priority'] = 'Medium'
                
            return data
        except Exception as e:
            print(f"Gemini API Error (category/priority): {e}")
            return None

    def check_duplicate(self, new_text: str, existing_complaints: list[dict]) -> dict | None:
        """Check if a new complaint is a duplicate of recent existing ones."""
        if not self.is_available() or not existing_complaints: return None
        
        context = "\\n".join([f"ID: {c['id']} | Text: {c['text']}" for c in existing_complaints])
        prompt = f"""
        New Complaint: "{new_text}"
        
        Recent Existing Complaints:
        {context}
        
        Does the new complaint likely describe the exact same specific issue as one of the existing complaints?
        Focus on specific locations and exact problems (e.g. same room number and same leaking tap).
        """
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ComplaintDuplicateResponse,
                    temperature=0.1
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"Gemini API Error (duplicate): {e}")
            return None

    def generate_full_analysis(self, text: str, location_type: str, valid_categories: set[str]) -> dict | None:
        """Generate a complete analysis for staff/admin on demand."""
        if not self.is_available(): return None
        
        prompt = f"""
        Analyze this complaint text: "{text}"
        Location Type: {location_type}
        Valid Categories: {', '.join(valid_categories)}
        
        Provide a detailed analysis including:
        - The most appropriate category from the valid list
        - Recommended priority (Low, Medium, High, Urgent)
        - A concise professional summary of the issue (do not modify the original meaning)
        - The suggested department/team to handle this
        - A suggested next action for staff
        - A professional draft response to the student acknowledging the issue
        """
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ComplaintAnalysisResponse,
                    temperature=0.2
                )
            )
            data = json.loads(response.text)
            
            # Strict validation
            if data.get('category') not in valid_categories:
                data['category'] = "Other College Issue" if location_type == 'College' else "Other Hostel Issue"
            if data.get('priority') not in {'Low', 'Medium', 'High', 'Urgent'}:
                data['priority'] = 'Medium'
                
            return data
        except Exception as e:
            print(f"Gemini API Error (full analysis): {e}")
            return None

# Singleton instance for the application
gemini_service = GeminiService()
