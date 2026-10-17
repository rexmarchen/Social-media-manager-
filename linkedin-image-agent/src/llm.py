"""
llm.py - Unified LLM wrapper for Text & Vision.
Supports Google Gemini, OpenAI, and Anthropic Claude using current provider model names.
Handles automated backoff, retry, and multi-modal image inputs.
"""

from __future__ import annotations

import base64
import io
import os
import time
from pathlib import Path
from typing import Optional, Union, List
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# Current official provider models (verified against provider docs)
# Google Gemini: gemini-flash-lite-latest, gemini-3.8-flash, gemini-3.7-flash
# OpenAI: gpt-4o, gpt-4o-mini
# Anthropic Claude: claude-3-7-sonnet-20250219, claude-3-5-sonnet-20241022
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-flash-lite-latest")
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
DEFAULT_CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-7-sonnet-20250219")


class LLMClient:
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize LLM Client.
        provider: 'gemini' | 'openai' | 'anthropic' | None (auto-detects from environment keys)
        """
        self.provider = provider or self._detect_provider()
        self.model = model or self._default_model_for_provider(self.provider)
        self._init_backend()

    def _detect_provider(self) -> str:
        if os.getenv("GEMINI_API_KEY"):
            return "gemini"
        elif os.getenv("OPENAI_API_KEY"):
            return "openai"
        elif os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        raise ValueError(
            "No API key detected in environment. Please set GEMINI_API_KEY, "
            "OPENAI_API_KEY, or ANTHROPIC_API_KEY in .env."
        )

    def _default_model_for_provider(self, provider: str) -> str:
        if provider == "gemini":
            return DEFAULT_GEMINI_MODEL
        elif provider == "openai":
            return DEFAULT_OPENAI_MODEL
        elif provider == "anthropic":
            return DEFAULT_CLAUDE_MODEL
        return DEFAULT_GEMINI_MODEL

    def _init_backend(self):
        if self.provider == "gemini":
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set.")
            self._client = genai.Client(api_key=api_key)
        elif self.provider == "openai":
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not set.")
            self._client = OpenAI(api_key=api_key)
        elif self.provider == "anthropic":
            from anthropic import Anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is not set.")
            self._client = Anthropic(api_key=api_key)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> str:
        """Generates text from prompt with automatic retries and exponential backoff."""
        delay = 2.0
        last_err = None

        for attempt in range(max_retries):
            try:
                if self.provider == "gemini":
                    full_prompt = f"System: {system_prompt}\n\nUser: {prompt}" if system_prompt else prompt
                    # Try primary model then fallback to backup model if 503
                    for candidate_model in [self.model, "gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-3.7-flash"]:
                        try:
                            resp = self._client.models.generate_content(
                                model=candidate_model,
                                contents=full_prompt,
                            )
                            return resp.text.strip()
                        except Exception as m_err:
                            if "503" in str(m_err) or "UNAVAILABLE" in str(m_err) or "404" in str(m_err):
                                continue
                            raise m_err

                elif self.provider == "openai":
                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({"role": "user", "content": prompt})
                    resp = self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=temperature,
                    )
                    return resp.choices[0].message.content.strip()

                elif self.provider == "anthropic":
                    kwargs = {
                        "model": self.model,
                        "max_tokens": 2048,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                    if system_prompt:
                        kwargs["system"] = system_prompt
                    resp = self._client.messages.create(**kwargs)
                    return resp.content[0].text.strip()

            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise RuntimeError(f"LLM text generation failed after {max_retries} attempts: {last_err}") from last_err

        return ""

    def analyze_image(
        self,
        image_input: Union[str, Path, Image.Image],
        prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 3,
    ) -> str:
        """Analyzes an image using Vision LLM."""
        if isinstance(image_input, (str, Path)):
            pil_image = Image.open(image_input).convert("RGB")
        else:
            pil_image = image_input.convert("RGB")

        delay = 2.0
        last_err = None

        for attempt in range(max_retries):
            try:
                if self.provider == "gemini":
                    contents: List[object] = [pil_image]
                    full_prompt = f"System: {system_prompt}\n\nTask: {prompt}" if system_prompt else prompt
                    contents.append(full_prompt)

                    for candidate_model in [self.model, "gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-3.7-flash"]:
                        try:
                            resp = self._client.models.generate_content(
                                model=candidate_model,
                                contents=contents,
                            )
                            return resp.text.strip()
                        except Exception as m_err:
                            if "503" in str(m_err) or "UNAVAILABLE" in str(m_err) or "404" in str(m_err):
                                continue
                            raise m_err

                elif self.provider == "openai":
                    # Convert to base64 jpeg
                    buffer = io.BytesIO()
                    pil_image.save(buffer, format="JPEG", quality=90)
                    b64_img = base64.b64encode(buffer.getvalue()).decode("utf-8")

                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                        ],
                    })
                    resp = self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                    )
                    return resp.choices[0].message.content.strip()

                elif self.provider == "anthropic":
                    buffer = io.BytesIO()
                    pil_image.save(buffer, format="JPEG", quality=90)
                    b64_img = base64.b64encode(buffer.getvalue()).decode("utf-8")

                    kwargs = {
                        "model": self.model,
                        "max_tokens": 2048,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": "image/jpeg",
                                            "data": b64_img,
                                        },
                                    },
                                    {"type": "text", "text": prompt},
                                ],
                            }
                        ],
                    }
                    if system_prompt:
                        kwargs["system"] = system_prompt
                    resp = self._client.messages.create(**kwargs)
                    return resp.content[0].text.strip()

            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise RuntimeError(f"Vision analysis failed after {max_retries} attempts: {last_err}") from last_err

        return ""


# Convenience singleton
_default_llm: Optional[LLMClient] = None

def get_llm() -> LLMClient:
    global _default_llm
    if _default_llm is None:
        _default_llm = LLMClient()
    return _default_llm
