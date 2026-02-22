"""
Mock AI providers for tests
"""
from src.models.internal import AIProviderHealth, AIResponse, LLMGenerateParams
from src.services.gemini_client import GeminiClient

class MockGeminiClient:
    """Mock Google Gemini AI client"""
    
    def __init__(self):
        self.provider_name = "Gemini (Mock)"
        self.model_name = "mock-gemini-model"

    async def generate_response(self, params: LLMGenerateParams) -> AIResponse:
        """Generate mock AI response"""
        # Return a simple mock response
        return AIResponse(
            text="This is a mock Gemini response.",
            token_count=10
        )

    async def transcribe_audio(self, audio_url: str) -> str:
        """Mock audio transcription"""
        return "This is a mock transcription of the audio."

    async def health_check(self) -> AIProviderHealth:
        """Mock health check"""
        return AIProviderHealth(status="up", latency_ms=10, error=None)

    async def close(self):
        """Mock close"""
        pass
