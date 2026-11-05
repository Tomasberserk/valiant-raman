"""Image Generation Providers for Cinematic Visual Orchestrator.

Provides abstract interface and concrete implementations for generating high-definition
keyframes:
- MockImageProvider: Offline deterministic keyframes with visual diagnostics.
- ProceduralCanvasProvider: High-aesthetic vertical canvas generation with Pillow.
- OpenAIImageProvider: DALL-E 3 / OpenAI image API integration with fail-fast validation.
- ComfyUIProvider: Local/remote ComfyUI endpoint connector for FLUX / SDXL.
"""

from abc import ABC, abstractmethod
import hashlib
import json
import logging
import os
from pathlib import Path
import random
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class VisualProviderError(Exception):
    """Base exception for all visual generation provider errors."""
    pass


class ProviderUnavailableError(VisualProviderError):
    """Raised when an external visual provider is unconfigured, unreachable, or missing credentials."""
    pass


class PromptContentFilteredError(VisualProviderError):
    """Raised when an external provider rejects the prompt due to safety policy."""
    pass


class ImageProvider(ABC):
    """Abstract interface for keyframe visual generation."""

    @abstractmethod
    def generate_keyframe(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1080,
        height: int = 1920,
        seed: Optional[int] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Generate a still keyframe image matching the requested dimensions and prompt."""
        pass


class MockImageProvider(ImageProvider):
    """Deterministic, offline visual generator for testing and fast local iteration."""

    def __init__(self, watermark_text: str = "CINEMATIC PROTOTYPE"):
        self.watermark_text = watermark_text

    def generate_keyframe(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1080,
        height: int = 1920,
        seed: Optional[int] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        if output_path is None:
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:12]
            output_path = Path(f"storage/cache/visuals/mock_{prompt_hash}.png")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Seeded deterministic color selection
        rng = random.Random(seed if seed is not None else hash(prompt))
        
        # Determine background mood based on prompt keywords
        prompt_lower = prompt.lower()
        if any(w in prompt_lower for w in ["bosque", "forest", "dark", "lightning", "espada", "sword"]):
            top_color = (rng.randint(10, 25), rng.randint(15, 35), rng.randint(20, 45))
            bottom_color = (rng.randint(5, 12), rng.randint(8, 18), rng.randint(12, 25))
            accent_color = (80, 200, 240) if "lightning" in prompt_lower else (230, 160, 40)
        elif any(w in prompt_lower for w in ["space", "galaxy", "telescope", "star", "cosmos"]):
            top_color = (8, 12, 28)
            bottom_color = (3, 4, 12)
            accent_color = (140, 100, 255)
        else:
            top_color = (25, 28, 35)
            bottom_color = (12, 14, 18)
            accent_color = (60, 180, 230)

        # Draw vertical gradient
        img = Image.new("RGB", (width, height), top_color)
        draw = ImageDraw.Draw(img)

        # Smooth vertical gradient fill
        for y in range(height):
            ratio = y / height
            r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
            g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
            b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Atmospheric particle noise
        for _ in range(rng.randint(60, 140)):
            px = rng.randint(0, width - 1)
            py = rng.randint(0, height - 1)
            p_rad = rng.randint(1, 4)
            p_alpha = rng.randint(30, 120)
            draw.ellipse(
                [(px - p_rad, py - p_rad), (px + p_rad, py + p_rad)],
                fill=(accent_color[0], accent_color[1], accent_color[2]),
            )

        # Cinematic letterbox bars
        letterbox_h = int(height * 0.08)
        draw.rectangle([(0, 0), (width, letterbox_h)], fill=(5, 5, 8))
        draw.rectangle([(0, height - letterbox_h), (width, height)], fill=(5, 5, 8))

        # Decorative cinematic frame borders
        pad = 40
        draw.rectangle(
            [(pad, pad), (width - pad, height - pad)],
            outline=(accent_color[0], accent_color[1], accent_color[2]),
            width=2,
        )

        # Header watermark
        draw.text((pad + 20, pad + 20), f"[ {self.watermark_text} ]", fill=(180, 180, 190))
        draw.text((width - pad - 180, pad + 20), f"{width}x{height}", fill=(140, 140, 150))

        # Center prompt overlay
        center_y = int(height * 0.45)
        draw.text((pad + 30, center_y - 60), "ACTION / SHOT PROMPT:", fill=accent_color)
        
        # Word wrap prompt
        words = prompt.split()
        lines = []
        cur_line = []
        for word in words:
            cur_line.append(word)
            if len(" ".join(cur_line)) > 35:
                lines.append(" ".join(cur_line))
                cur_line = []
        if cur_line:
            lines.append(" ".join(cur_line))

        y_offset = center_y - 20
        for line in lines[:8]:
            draw.text((pad + 30, y_offset), line, fill=(240, 240, 245))
            y_offset += 32

        # Footer diagnostics
        footer_y = height - pad - 60
        draw.text((pad + 30, footer_y), f"SEED: {seed or 'AUTO'} | TIER: MOCK_PROTOTYPE", fill=(130, 130, 140))

        img.save(str(output_path), "PNG")
        return output_path


class ProceduralCanvasProvider(ImageProvider):
    """High-definition procedural aesthetic keyframe generator using Pillow."""

    def generate_keyframe(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1080,
        height: int = 1920,
        seed: Optional[int] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        if output_path is None:
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:12]
            output_path = Path(f"storage/cache/visuals/procedural_{prompt_hash}.png")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        rng = random.Random(seed if seed is not None else hash(prompt))

        # Rich dark fantasy / sci-fi palettes
        img = Image.new("RGB", (width, height), (10, 12, 18))
        draw = ImageDraw.Draw(img)

        # Multi-stop vertical gradient
        for y in range(height):
            ratio = y / height
            r = int(12 * (1 - ratio) + 4 * ratio)
            g = int(24 * (1 - ratio) + 8 * ratio)
            b = int(38 * (1 - ratio) + 14 * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Radial light core
        center_x = width // 2
        center_y = int(height * 0.4)
        for r in range(400, 0, -20):
            alpha = int((1.0 - (r / 400)) * 60)
            glow_color = (20 + alpha, 40 + alpha, 70 + alpha)
            draw.ellipse(
                [(center_x - r, center_y - r), (center_x + r, center_y + r)],
                outline=glow_color,
                width=3,
            )

        # Cinematic letterbox
        bar_h = int(height * 0.07)
        draw.rectangle([(0, 0), (width, bar_h)], fill=(0, 0, 0))
        draw.rectangle([(0, height - bar_h), (width, height)], fill=(0, 0, 0))

        img.save(str(output_path), "PNG")
        return output_path


class OpenAIImageProvider(ImageProvider):
    """OpenAI DALL-E 3 / gpt-image API provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    def generate_keyframe(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1080,
        height: int = 1920,
        seed: Optional[int] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        if not self.api_key:
            raise ProviderUnavailableError(
                "OpenAIImageProvider requires OPENAI_API_KEY environment variable. "
                "Failing loud per anti-silent-fallback policy."
            )

        import httpx

        if output_path is None:
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:12]
            output_path = Path(f"storage/cache/visuals/openai_{prompt_hash}.png")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # DALL-E 3 native vertical size
        size = "1024x1792"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": "standard",
            "response_format": "url",
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                res = client.post("https://api.openai.com/v1/images/generations", headers=headers, json=payload)
                if res.status_code == 400 and "safety" in res.text.lower():
                    raise PromptContentFilteredError(f"Prompt content was rejected by OpenAI safety filters: {res.text}")
                res.raise_for_status()
                data = res.json()
                image_url = data["data"][0]["url"]

                img_res = client.get(image_url)
                img_res.raise_for_status()
                output_path.write_bytes(img_res.content)

                # Resize to target 1080x1920 if needed
                with Image.open(output_path) as im:
                    if im.size != (width, height):
                        resized = im.resize((width, height), Image.Resampling.LANCZOS)
                        resized.save(output_path)

                return output_path
        except (httpx.HTTPError, KeyError) as e:
            logger.error(f"OpenAI Image API call failed: {e}")
            raise ProviderUnavailableError(f"OpenAI Image generation failed: {e}") from e


class ComfyUIProvider(ImageProvider):
    """Local or remote ComfyUI workflow provider for FLUX or SDXL models."""

    def __init__(self, host: Optional[str] = None):
        self.host = host or os.getenv("COMFYUI_HOST", "http://127.0.0.1:8188")

    def generate_keyframe(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1080,
        height: int = 1920,
        seed: Optional[int] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        import httpx

        if output_path is None:
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:12]
            output_path = Path(f"storage/cache/visuals/comfy_{prompt_hash}.png")

        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.host}/system_stats")
                if res.status_code != 200:
                    raise ProviderUnavailableError(f"ComfyUI server at {self.host} returned {res.status_code}")
        except Exception as e:
            raise ProviderUnavailableError(f"ComfyUI host {self.host} is unreachable: {e}") from e

        # If reachable, ComfyUI queue submission logic would run here
        raise NotImplementedError("ComfyUI workflow execution pipeline requires configured graph template.")
