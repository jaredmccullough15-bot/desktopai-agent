"""
Natural Language Procedure Creation Module

Allows users to describe procedures in plain English and converts them to executable procedures.
"""

import os
import json
import re
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
client: Optional[OpenAI] = OpenAI(api_key=_OPENAI_API_KEY) if _OPENAI_API_KEY else None


class NaturalLanguageProcedureCreator:
    """Converts natural language descriptions into executable procedures."""
    
    def __init__(self):
        """Initialize the NL procedure creator."""
        self.procedures_dir = os.path.join(os.path.dirname(__file__), "..", "data", "procedures")
    
    def create_procedure_from_description(self, name: str, description: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Create a procedure from a natural language description.
        
        Args:
            name: Name for the procedure
            description: Natural language description of what to do
        
        Returns:
            (success, message, procedure_dict)
        """
        if not client:
            return False, "OpenAI API key not configured", None
        
        if not description.strip():
            return False, "Description cannot be empty", None
        
        # Use AI to parse the description into steps
        steps, error = self._parse_description_to_steps(description)
        
        if error:
            return False, f"Failed to parse description: {error}", None
        
        if not steps:
            return False, "Could not extract any steps from description", None
        
        # Convert steps into procedure format
        procedure = self._create_procedure_structure(name, description, steps)
        
        # Save the procedure
        success, msg = self._save_procedure(name, procedure)
        
        if success:
            return True, msg, procedure
        else:
            return False, msg, None
    
    def _parse_description_to_steps(self, description: str) -> Tuple[List[Dict], Optional[str]]:
        """
        Use AI to parse natural language description into structured steps.
        
        Returns:
            (steps_list, error_message)
        """
        system_prompt = """You are an expert at converting natural language task descriptions into step-by-step procedures for desktop automation.

Given a task description, break it down into clear, actionable steps. Each step should be specific and executable.

Return your response as JSON in this format:
{
  "steps": [
    {
      "step_number": 1,
      "action": "open_url" | "click" | "type" | "wait" | "navigate" | "fill_form" | "other",
      "description": "Human-readable description of the step",
      "target": "What to interact with (URL, button name, field name, etc.)",
      "value": "What to type or select (if applicable)"
    }
  ]
}

Action types:
- open_url: Navigate to a website
- click: Click a button, link, or element
- type: Type text into a field
- wait: Wait for something to appear or load
- navigate: Navigate through tabs or sections
- fill_form: Fill out form fields
- other: Any other action

Be specific about targets (button names, field labels, URLs). If the description mentions specific values, include them."""

        user_prompt = f"Task description:\n{description}\n\nConvert this into a step-by-step procedure."
        
        try:
            response = client.responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]}
                ],
                temperature=0.3,
                max_output_tokens=1500
            )
            
            response_text = (response.output_text or "").strip()
            
            # Remove code fences if present
            response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
            response_text = re.sub(r"\s*```$", "", response_text)
            
            # Parse JSON
            data = json.loads(response_text)
            steps = data.get("steps", [])
            
            if not steps:
                return [], "AI returned no steps"
            
            return steps, None
            
        except json.JSONDecodeError as e:
            return [], f"Failed to parse AI response as JSON: {e}"
        except Exception as e:
            return [], f"AI call failed: {e}"
    
    def _create_procedure_structure(self, name: str, description: str, steps: List[Dict]) -> Dict:
        """
        Create the procedure structure from parsed steps.
        
        This creates a simplified procedure format that can be executed.
        """
        procedure = {
            "name": name,
            "type": "natural_language",
            "description": description,
            "created_by": "natural_language_creator",
            "steps": []
        }
        
        for step in steps:
            step_number = step.get("step_number", 0)
            action_type = step.get("action", "other")
            step_description = step.get("description", "")
            target = step.get("target", "")
            value = step.get("value", "")
            
            # Convert to checkpoint format (compatible with existing system)
            checkpoint = {
                "step": step_number,
                "description": step_description,
                "action_type": action_type,
                "target": target,
                "value": value
            }
            
            procedure["steps"].append(checkpoint)
        
        return procedure
    
    def _save_procedure(self, name: str, procedure: Dict) -> Tuple[bool, str]:
        """
        Save the procedure to disk.
        
        Args:
            name: Procedure name
            procedure: Procedure dictionary
        
        Returns:
            (success, message)
        """
        try:
            # Create safe folder name
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
            folder_path = os.path.join(self.procedures_dir, safe_name)
            
            os.makedirs(folder_path, exist_ok=True)
            
            # Save manifest
            manifest_path = os.path.join(folder_path, "manifest.json")
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(procedure, f, indent=2, ensure_ascii=False)
            
            return True, f"Procedure '{name}' created successfully with {len(procedure['steps'])} steps"
            
        except Exception as e:
            return False, f"Failed to save procedure: {e}"
    
    def preview_procedure(self, description: str) -> Tuple[bool, str, Optional[List[Dict]]]:
        """
        Preview what steps would be created from a description without saving.
        
        Args:
            description: Natural language description
        
        Returns:
            (success, message, steps_list)
        """
        steps, error = self._parse_description_to_steps(description)
        
        if error:
            return False, f"Failed to parse description: {error}", None
        
        if not steps:
            return False, "Could not extract any steps from description", None
        
        return True, f"Successfully parsed {len(steps)} steps", steps


# Global instance
_nl_creator = None


def get_nl_procedure_creator() -> NaturalLanguageProcedureCreator:
    """Get the global NL procedure creator instance."""
    global _nl_creator
    if _nl_creator is None:
        _nl_creator = NaturalLanguageProcedureCreator()
    return _nl_creator