import os
import time
import json
from typing import Dict, Any, Optional
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
from models import Log
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class LogDiagnostician:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()
        self.model = os.getenv("LLM_MODEL")
        
        if self.provider == "groq":
            from groq import AsyncGroq
            self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
            self.model = self.model or "llama-3.3-70b-versatile"
        else:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = self.model or "gpt-4o-mini"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def diagnose_error(self, log_entry: Log) -> Dict[str, Any]:
        """
        Analyzes a log entry using LLM to provide root cause, fix, and prevention strategy.
        """
        start_time = time.time()
        
        # Prepare context for LLM
        context = {
            "service_name": log_entry.service_name,
            "timestamp": log_entry.timestamp,
            "log_level": log_entry.log_level,
            "message": log_entry.message,
            "metadata": log_entry.metadata_json
        }

        prompt = f"""You are a senior debugging assistant.
Analyze this error from a microservice and provide a structured diagnosis.

LOG CONTEXT:
{json.dumps(context, indent=2)}

Please provide your analysis in the following JSON format:
{{
  "root_cause": "Detailed explanation of why this error occurred",
  "suggested_fix": "Specific code changes or actions to fix the issue",
  "prevention": "Strategies to prevent this error from recurring",
  "confidence": "high/medium/low"
}}
"""

        try:
            if self.provider == "groq":
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are an expert software engineer and SRE specializing in root cause analysis."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
            else:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are an expert software engineer and SRE specializing in root cause analysis."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
            
            diagnosis_content = response.choices[0].message.content
            diagnosis = json.loads(diagnosis_content)
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                "log_id": log_entry.id,
                "error_message": log_entry.message,
                "diagnosis": diagnosis,
                "execution_time_ms": execution_time_ms
            }
            
        except Exception as e:
            logger.error(f"Error during LLM diagnosis ({self.provider}): {str(e)}")
            raise e

# Global instance
agent = LogDiagnostician()
