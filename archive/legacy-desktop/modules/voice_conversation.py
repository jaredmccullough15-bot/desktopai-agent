"""
Voice Conversation Module

Enables natural voice dialogue with the AI assistant, including voice responses.
"""

import os
import time
import threading
import importlib.util
from typing import Optional, Callable
import speech_recognition as sr
from dotenv import load_dotenv

load_dotenv()

try:
    import pyttsx3
    TTS_AVAILABLE = True
    _tts_engine = None
except Exception:
    TTS_AVAILABLE = False


def get_tts_engine():
    """Get or initialize the text-to-speech engine."""
    global _tts_engine
    if TTS_AVAILABLE and _tts_engine is None:
        try:
            _tts_engine = pyttsx3.init()
            # Configure voice properties
            _tts_engine.setProperty('rate', 175)  # Speed
            _tts_engine.setProperty('volume', 0.9)  # Volume (0-1)
        except Exception as e:
            print(f"TTS initialization error: {e}")
            return None
    return _tts_engine


class VoiceConversation:
    """Manages voice-based conversation with the AI."""
    
    def __init__(self, response_callback: Optional[Callable] = None, log_callback: Optional[Callable] = None):
        """
        Initialize voice conversation manager.
        
        Args:
            response_callback: Function to call with AI responses (text, audio)
            log_callback: Function to call with log messages
        """
        self.response_callback = response_callback
        self.log_callback = log_callback
        self.active = False
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 1.0  # Longer pause for natural conversation
        
        # Check PyAudio availability
        self.pyaudio_available = check_voice_input_available()
        if not self.pyaudio_available:
            self.log("⚠️ PyAudio not found - voice input will not work")
            self.log("For Python 3.14: Install Microsoft Visual C++ Build Tools")
            self.log("Then run: pip install pyaudio")
        
    def log(self, message: str):
        """Log a message."""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    def speak(self, text: str):
        """
        Speak text using text-to-speech.
        
        Args:
            text: Text to speak
        """
        if not TTS_AVAILABLE:
            self.log(f"AI (text-only): {text}")
            return
        
        try:
            engine = get_tts_engine()
            if engine:
                # Run in thread to not block
                def speak_thread():
                    try:
                        engine.say(text)
                        engine.runAndWait()
                    except Exception as e:
                        self.log(f"TTS error: {e}")
                
                threading.Thread(target=speak_thread, daemon=True).start()
                self.log(f"AI: {text}")
        except Exception as e:
            self.log(f"Speak error: {e}")
    
    def listen_once(self, timeout: int = 10) -> Optional[str]:
        """
        Listen for a single voice input.
        
        Args:
            timeout: Timeout in seconds
        
        Returns:
            Recognized text or None
        """
        # Check if PyAudio is available
        if not self.pyaudio_available:
            self.log("Voice input unavailable - PyAudio not installed")
            return None
        try:
            mic_index = os.getenv("MIC_INDEX")
            if mic_index and mic_index.strip().isdigit():
                mic = sr.Microphone(device_index=int(mic_index))
            else:
                mic = sr.Microphone()
            
            with mic as source:
                self.log("Listening...")
                
                # Adjust for ambient noise
                try:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                except Exception:
                    pass
                
                # Listen
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
                
                # Recognize
                self.log("Processing...")
                text = self.recognizer.recognize_google(audio)
                
                if text:
                    self.log(f"You: {text}")
                    return text
                
        except sr.WaitTimeoutError:
            self.log("No speech detected (timeout)")
        except sr.UnknownValueError:
            self.log("Could not understand speech")
        except Exception as e:
            self.log(f"Listen error: {e}")
        
        return None
    
    def start_conversation(self, process_callback: Callable, stop_event: threading.Event):
        """
        Start a continuous voice conversation.
        
        Args:
            process_callback: Function to process user input and return AI response
            stop_event: Event to signal conversation should stop
        """
        self.active = True
        self.speak("Hello! Jarvis here. I'm ready to assist you. What can I do for you?")
        
        while not stop_event.is_set() and self.active:
            # Listen for user input
            user_text = self.listen_once(timeout=30)
            
            if not user_text:
                continue
            
            # Check for exit commands
            if any(cmd in user_text.lower() for cmd in ["stop conversation", "exit conversation", "end conversation", "stop talking"]):
                self.speak("Understood! I'll be here whenever you need me. Take care!")
                break
            
            # Process with AI
            try:
                ai_response = process_callback(user_text)
                
                if ai_response:
                    self.speak(ai_response)
                    
                    # Brief pause before listening again
                    time.sleep(0.5)
            except Exception as e:
                self.log(f"Processing error: {e}")
                self.speak("Sorry, I encountered an error processing that.")
        
        self.active = False
        self.log("Conversation mode ended.")
    
    def stop(self):
        """Stop the conversation."""
        self.active = False


# Global instance
_conversation = None


def get_voice_conversation(response_callback: Optional[Callable] = None, 
                          log_callback: Optional[Callable] = None) -> VoiceConversation:
    """Get or create the global voice conversation instance."""
    global _conversation
    if _conversation is None:
        _conversation = VoiceConversation(response_callback, log_callback)
    return _conversation


def check_tts_available() -> bool:
    """Check if text-to-speech is available."""
    return TTS_AVAILABLE


def check_voice_input_available() -> bool:
    """Check if voice input (PyAudio) is available."""
    try:
        return importlib.util.find_spec("pyaudio") is not None
    except Exception:
        return False
