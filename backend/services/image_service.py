"""Image generation agent using ModelScope API (Qwen-Image)."""

import asyncio
from typing import Dict, Optional

import httpx

MODELSCOPE_BASE_URL = "https://api-inference.modelscope.cn/"
MODEL = "Qwen/Qwen-Image-2512"

# Base scene descriptions for image prompts
SCENE_PROMPTS: Dict[str, str] = {
    "宴会厅": (
        "Grand dining hall in an ancient Chinese mansion at night, "
        "dim chandelier casting warm golden light, long carved mahogany table, "
        "ornate wooden screens, silk curtains, porcelain tableware, "
        "shadows dancing on traditional painted walls"
    ),
    "书房": (
        "Traditional Chinese study room in an old mansion, "
        "wooden bookshelves with ancient scrolls and leather-bound volumes, "
        "calligraphy brush set on a rosewood desk, dim brass desk lamp, "
        "ink paintings on the wall, mysterious atmosphere"
    ),
    "花园": (
        "Chinese courtyard garden at night under moonlight, "
        "twisted plum blossom trees, ornamental rocks, "
        "stone pathway winding through bamboo groves, "
        "classical pavilion with curved roof in the distance, "
        "light mist floating above a koi pond"
    ),
    "酒窖": (
        "Dark underground wine cellar beneath a Chinese mansion, "
        "rows of aged wine barrels and dusty bottles on stone shelves, "
        "single flickering lantern casting long shadows, "
        "cobwebs in the corners, heavy wooden door ajar, "
        "damp stone walls with mysterious markings"
    ),
    "走廊": (
        "Long dimly lit corridor in an ancient Chinese mansion, "
        "ornate wooden doors on both sides, carved lattice windows, "
        "antique wall sconces with flickering candles, "
        "red lacquered pillars, polished stone floor reflecting light, "
        "a shadow disappearing around the corner"
    ),
}

# Tension-based atmosphere modifiers
TENSION_MODIFIERS = {
    "low": "peaceful and contemplative mood, soft warm lighting, serene",
    "mid": "growing unease, dramatic shadows, mysterious atmosphere, suspenseful",
    "high": "intense and dangerous atmosphere, harsh contrasting light, ominous shadows, thriller mood",
}

# Phase-based style modifiers
PHASE_MODIFIERS: Dict[str, str] = {
    "自由试探": "exploratory mood, curious atmosphere, gentle mystery",
    "深入调查": "investigative mood, focused lighting on details, noir detective atmosphere",
    "高压对峙": "confrontational atmosphere, dramatic tension, faces in shadow, thriller",
    "终局逼近": "climactic atmosphere, red-tinged lighting, everything coming to a head, intense",
    "公开对峙": "open confrontation, spotlight effect, dramatic showdown, theatrical",
}


class ImageAgent:
    """Generates scene illustrations using ModelScope's Qwen-Image model."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._cache: Dict[str, str] = {}  # scene+tension_level -> image_url

    def _build_prompt(
        self, scene: str, narration: str, tension: int, phase: str
    ) -> str:
        """Build an image generation prompt from game context."""
        # Base scene description
        base = SCENE_PROMPTS.get(scene, SCENE_PROMPTS["宴会厅"])

        # Tension modifier
        if tension >= 60:
            tension_mod = TENSION_MODIFIERS["high"]
        elif tension >= 30:
            tension_mod = TENSION_MODIFIERS["mid"]
        else:
            tension_mod = TENSION_MODIFIERS["low"]

        # Phase modifier
        phase_mod = PHASE_MODIFIERS.get(phase, "")

        prompt = (
            f"{base}, {tension_mod}, {phase_mod}, "
            "cinematic composition, atmospheric lighting, "
            "high quality illustration, detailed environment art, "
            "dark mystery game scene, widescreen aspect ratio"
        )
        return prompt

    def _cache_key(self, scene: str, tension: int) -> str:
        """Create a cache key based on scene and tension level."""
        if tension >= 60:
            level = "high"
        elif tension >= 30:
            level = "mid"
        else:
            level = "low"
        return f"{scene}_{level}"

    # ── Character portrait prompts ──
    CHARACTER_PORTRAIT_PROMPTS = {
        "linlan": (
            "Portrait of a Chinese woman, age 28, professional secretary, "
            "wearing dark formal suit, hair pulled back neatly, "
            "cold and composed expression, slight head tilt, "
            "piercing intelligent eyes, subtle tension in jaw, "
            "dim warm lighting, dark background, "
            "cinematic portrait, film noir style, mystery atmosphere, "
            "photorealistic, upper body shot"
        ),
        "zhoumu": (
            "Portrait of a Chinese man, age 32, casual wealthy look, "
            "unbuttoned collar on dress shirt, slightly disheveled, "
            "forced smile that doesn't reach his eyes, "
            "holding a whiskey glass, nervous energy, "
            "handsome but anxious, sweat on forehead, "
            "dim warm lighting, dark background, "
            "cinematic portrait, film noir style, mystery atmosphere, "
            "photorealistic, upper body shot"
        ),
        "songzhi": (
            "Portrait of a young Chinese woman, age 26, journalist, "
            "wearing thin-frame glasses, sharp observant eyes, "
            "holding a small black notebook and pen, "
            "confident slight smirk, analytical expression, "
            "smart casual outfit, press badge visible, "
            "dim warm lighting, dark background, "
            "cinematic portrait, film noir style, mystery atmosphere, "
            "photorealistic, upper body shot"
        ),
    }

    async def generate_character_portrait(
        self, character_id: str, use_cache: bool = True
    ) -> Optional[str]:
        """Generate a character portrait image. Returns URL or None."""
        cache_key = f"portrait_{character_id}"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        prompt = self.CHARACTER_PORTRAIT_PROMPTS.get(character_id)
        if not prompt:
            return None

        try:
            image_url = await self._call_modelscope(prompt)
            if image_url:
                self._cache[cache_key] = image_url
                print(f"[ImageAgent] Portrait generated for {character_id}: {image_url[:60]}...")
            return image_url
        except Exception as e:
            print(f"[ImageAgent] Portrait generation failed for {character_id}: {e}")
            return None

    async def generate_all_portraits(self) -> dict:
        """Generate portraits for all characters. Returns {char_id: url}."""
        import asyncio
        results = {}
        tasks = {
            cid: self.generate_character_portrait(cid)
            for cid in self.CHARACTER_PORTRAIT_PROMPTS
        }
        for cid, task in tasks.items():
            url = await task
            if url:
                results[cid] = url
        return results

    async def generate_scene_image(
        self,
        scene: str,
        narration: str = "",
        tension: int = 20,
        phase: str = "自由试探",
        use_cache: bool = True,
    ) -> Optional[str]:
        """
        Generate a scene illustration.

        Returns the image URL or None if generation fails.
        """
        # Check cache
        cache_key = self._cache_key(scene, tension)
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        prompt = self._build_prompt(scene, narration, tension, phase)

        try:
            image_url = await self._call_modelscope(prompt)
            if image_url:
                self._cache[cache_key] = image_url
            return image_url
        except Exception as e:
            print(f"[ImageAgent] Generation failed: {e}")
            return None

    async def _call_modelscope(self, prompt: str) -> Optional[str]:
        """Submit image generation task and poll for result."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-ModelScope-Async-Mode": "true",
        }

        payload = {
            "model": MODEL,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            # 1. Submit task
            resp = await client.post(
                f"{MODELSCOPE_BASE_URL}v1/images/generations",
                headers=headers,
                json=payload,
            )

            if resp.status_code != 200:
                print(f"[ImageAgent] Submit failed: {resp.status_code} {resp.text}")
                return None

            data = resp.json()
            task_id = data.get("task_id")
            if not task_id:
                print(f"[ImageAgent] No task_id in response: {data}")
                return None

            # Check if task already succeeded synchronously
            if data.get("task_status") == "SUCCEED" and data.get("output_images"):
                return data["output_images"][0]

            print(f"[ImageAgent] Task submitted: {task_id}, polling...")

            # 2. Poll for result — initial wait then check every 10s
            await asyncio.sleep(10)  # Image gen takes ~60-90s, don't poll too early

            poll_headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-ModelScope-Task-Type": "image_generation",
            }

            for i in range(15):  # max 150s (15 * 10s)
                status_resp = await client.get(
                    f"{MODELSCOPE_BASE_URL}v1/tasks/{task_id}",
                    headers=poll_headers,
                )

                if status_resp.status_code != 200:
                    await asyncio.sleep(10)
                    continue

                status_data = status_resp.json()
                task_status = status_data.get("task_status")

                if task_status == "SUCCEED":
                    output_images = status_data.get("output_images", [])
                    if output_images:
                        print(f"[ImageAgent] Image generated: {output_images[0][:80]}...")
                        return output_images[0]
                    return None
                elif task_status == "FAILED":
                    error_msg = (
                        status_data.get("error", {}).get("message", "Unknown error")
                    )
                    print(f"[ImageAgent] Task failed: {error_msg}")
                    return None
                else:
                    print(f"[ImageAgent] Poll {i+1}: {task_status}")

                await asyncio.sleep(10)

            print("[ImageAgent] Task timed out after 160s")
            return None
