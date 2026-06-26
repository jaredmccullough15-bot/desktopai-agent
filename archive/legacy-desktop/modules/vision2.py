"""
Vision 2.0 - Enhanced UI Element Recognition

Provides advanced visual understanding of UI elements, layout detection,
and intelligent element targeting.
"""

import os
import re
from typing import Dict, List, Optional, Tuple
from PIL import Image
import mss

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    if os.getenv("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
except Exception:
    TESSERACT_AVAILABLE = False


class UIElementRecognizer:
    """Advanced UI element recognition and targeting."""
    
    def __init__(self):
        """Initialize UI element recognizer."""
        self.last_scan = None
        self.cached_elements = []
    
    def scan_ui_elements(self, bbox: Optional[Dict] = None) -> List[Dict]:
        """
        Scan the screen/window and detect UI elements.
        
        Args:
            bbox: Optional bounding box {left, top, width, height}
        
        Returns:
            List of detected elements with metadata
        """
        if not TESSERACT_AVAILABLE:
            return []
        
        try:
            # Capture screen/window
            with mss.mss() as sct:
                if bbox is None:
                    monitor = sct.monitors[1]
                    bbox = {
                        "left": monitor["left"],
                        "top": monitor["top"],
                        "width": monitor["width"],
                        "height": monitor["height"],
                    }
                img = sct.grab(bbox)
            
            pil_image = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            
            # Get detailed OCR data
            data = pytesseract.image_to_data(pil_image, output_type=pytesseract.Output.DICT, config="--psm 6")
            
            elements = []
            count = len(data.get("text", []))
            
            for i in range(count):
                text = (data["text"][i] or "").strip()
                if not text:
                    continue
                
                conf = float(data["conf"][i]) if data["conf"][i] != -1 else 0
                if conf < 30:  # Skip low-confidence detections
                    continue
                
                element = {
                    "text": text,
                    "type": self._classify_element(text, data, i),
                    "position": {
                        "x": bbox["left"] + int(data["left"][i]),
                        "y": bbox["top"] + int(data["top"][i]),
                        "width": int(data["width"][i]),
                        "height": int(data["height"][i])
                    },
                    "confidence": conf,
                    "block": data["block_num"][i],
                    "line": data["line_num"][i]
                }
                
                elements.append(element)
            
            self.cached_elements = elements
            return elements
            
        except Exception as e:
            print(f"UI scan error: {e}")
            return []
    
    def _classify_element(self, text: str, data: Dict, index: int) -> str:
        """
        Classify an element based on its text and context.
        
        Returns:
            Element type: button, link, label, input, heading, etc.
        """
        text_lower = text.lower()
        
        # Button indicators
        button_keywords = ["button", "submit", "ok", "cancel", "save", "delete", "add", "create", "update", "edit", "confirm"]
        if any(keyword in text_lower for keyword in button_keywords):
            return "button"
        
        # Link indicators
        if text.startswith("http") or ".com" in text_lower or ".org" in text_lower:
            return "link"
        
        # Input field labels (usually followed by a colon)
        if text.endswith(":"):
            return "label"
        
        # Heading indicators (often all caps or title case)
        if text.isupper() and len(text) > 3:
            return "heading"
        
        # Check height - taller elements might be buttons
        height = int(data["height"][index])
        if height > 30:
            return "button"
        
        return "text"
    
    def find_element(self, target_text: str, element_type: Optional[str] = None) -> Optional[Dict]:
        """
        Find a UI element by text and optional type.
        
        Args:
            target_text: Text to search for
            element_type: Optional filter by element type
        
        Returns:
            Best matching element or None
        """
        if not self.cached_elements:
            self.scan_ui_elements()
        
        target_norm = self._normalize_text(target_text)
        
        candidates = []
        for element in self.cached_elements:
            if element_type and element["type"] != element_type:
                continue
            
            element_text_norm = self._normalize_text(element["text"])
            
            # Calculate similarity
            if target_norm in element_text_norm:
                similarity = len(target_norm) / len(element_text_norm)
                candidates.append((similarity, element))
            elif element_text_norm in target_norm:
                similarity = len(element_text_norm) / len(target_norm)
                candidates.append((similarity * 0.8, element))
        
        if not candidates:
            return None
        
        # Return best match
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    
    def find_buttons(self) -> List[Dict]:
        """Find all button elements."""
        if not self.cached_elements:
            self.scan_ui_elements()
        
        return [e for e in self.cached_elements if e["type"] == "button"]
    
    def find_clickable_near(self, text: str, max_distance: int = 200) -> List[Dict]:
        """
        Find clickable elements near a text label.
        
        Useful for finding buttons next to labels.
        
        Args:
            text: Label text
            max_distance: Maximum pixel distance
        
        Returns:
            List of nearby clickable elements
        """
        label = self.find_element(text, "label")
        if not label:
            return []
        
        label_pos = label["position"]
        label_center_x = label_pos["x"] + label_pos["width"] // 2
        label_center_y = label_pos["y"] + label_pos["height"] // 2
        
        clickables = []
        for element in self.cached_elements:
            if element["type"] not in ["button", "link"]:
                continue
            
            elem_pos = element["position"]
            elem_center_x = elem_pos["x"] + elem_pos["width"] // 2
            elem_center_y = elem_pos["y"] + elem_pos["height"] // 2
            
            distance = ((label_center_x - elem_center_x) ** 2 + 
                        (label_center_y - elem_center_y) ** 2) ** 0.5
            
            if distance <= max_distance:
                clickables.append({**element, "distance": distance})
        
        clickables.sort(key=lambda x: x["distance"])
        return clickables
    
    def get_screen_layout(self) -> Dict:
        """
        Analyze screen layout and return structured information.
        
        Returns:
            Layout analysis: regions, buttons, inputs, hierarchy
        """
        if not self.cached_elements:
            self.scan_ui_elements()
        
        # Group elements by blocks (visual regions)
        blocks = {}
        for element in self.cached_elements:
            block_id = element["block"]
            if block_id not in blocks:
                blocks[block_id] = []
            blocks[block_id].append(element)
        
        # Analyze each block
        regions = []
        for block_id, elements in blocks.items():
            region = {
                "id": block_id,
                "elements": elements,
                "buttons": [e for e in elements if e["type"] == "button"],
                "links": [e for e in elements if e["type"] == "link"],
                "labels": [e for e in elements if e["type"] == "label"],
                "headings": [e for e in elements if e["type"] == "heading"]
            }
            regions.append(region)
        
        return {
            "total_elements": len(self.cached_elements),
            "regions": regions,
            "buttons": self.find_buttons(),
            "has_form": any(e["type"] == "label" for e in self.cached_elements)
        }
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        return " ".join(text.lower().split())


# Global instance
_ui_recognizer = None


def get_ui_recognizer() -> UIElementRecognizer:
    """Get the global UI recognizer instance."""
    global _ui_recognizer
    if _ui_recognizer is None:
        _ui_recognizer = UIElementRecognizer()
    return _ui_recognizer


def smart_click_element(target_text: str, element_type: Optional[str] = None) -> bool:
    """
    Intelligently click a UI element using Vision 2.0.
    
    Args:
        target_text: Text of the element to click
        element_type: Optional element type filter
    
    Returns:
        True if clicked successfully
    """
    import pyautogui
    
    recognizer = get_ui_recognizer()
    element = recognizer.find_element(target_text, element_type)
    
    if not element:
        return False
    
    # Click the center of the element
    pos = element["position"]
    center_x = pos["x"] + pos["width"] // 2
    center_y = pos["y"] + pos["height"] // 2
    
    pyautogui.click(center_x, center_y)
    return True
