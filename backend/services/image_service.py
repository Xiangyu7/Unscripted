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

    # ── Character portrait base prompts ──
    _PORTRAIT_BASE = {
        "linlan": (
            "Portrait of a Chinese woman, age 28, professional secretary, "
            "wearing dark formal suit, hair pulled back neatly, "
            "piercing intelligent eyes, "
            "dim warm lighting, dark background, "
            "cinematic portrait, film noir style, mystery atmosphere, "
            "photorealistic, upper body shot"
        ),
        "zhoumu": (
            "Portrait of a Chinese man, age 32, casual wealthy look, "
            "unbuttoned collar on dress shirt, slightly disheveled, "
            "holding a whiskey glass, "
            "handsome, "
            "dim warm lighting, dark background, "
            "cinematic portrait, film noir style, mystery atmosphere, "
            "photorealistic, upper body shot"
        ),
        "songzhi": (
            "Portrait of a young Chinese woman, age 26, journalist, "
            "wearing thin-frame glasses, sharp observant eyes, "
            "holding a small black notebook and pen, "
            "smart casual outfit, press badge visible, "
            "dim warm lighting, dark background, "
            "cinematic portrait, film noir style, mystery atmosphere, "
            "photorealistic, upper body shot"
        ),
    }

    # ── Mood expression modifiers (appended to base prompt) ──
    _MOOD_EXPRESSIONS: Dict[str, Dict[str, str]] = {
        "linlan": {
            "calm":      "cold and composed expression, slight confident head tilt, icy demeanor",
            "guarded":   "guarded expression, slightly narrowed eyes, lips pressed together, wary",
            "nervous":   "micro-tension in jaw, slightly wider eyes, fingers gripping cuff, controlled anxiety",
            "fearful":   "fear breaking through composure, eyes darting, pale complexion, hand near throat",
            "angry":     "cold fury in eyes, sharp jawline tense, intimidating glare, controlled rage",
            "desperate": "red-rimmed eyes, hair coming loose, mascara slightly smeared, facade crumbling",
        },
        "zhoumu": {
            "calm":      "genuine relaxed smile, confident posture, at ease with drink in hand",
            "guarded":   "forced smile that doesn't reach eyes, nervous energy, sweat on forehead",
            "nervous":   "fidgeting with glass, biting lower lip, eyes avoiding contact, anxious",
            "fearful":   "wide frightened eyes, pale face, drink spilled, trembling hand, panicked",
            "angry":     "red face, veins visible on forehead, jaw clenched, aggressive stance, furious",
            "desperate": "disheveled hair, loosened tie, bloodshot eyes, tear streaks, broken man",
        },
        "songzhi": {
            "calm":      "confident slight smirk, analytical expression, glasses glinting, in control",
            "guarded":   "pushing glasses up nervously, guarded smile, notebook clutched to chest",
            "nervous":   "rapid blinking, pen tapping nervously, looking over shoulder, uneasy",
            "fearful":   "glasses askew, notebook dropped, genuine fear in eyes, backing away",
            "angry":     "sharp accusatory glare, pointing finger, righteous anger, journalist interrogating",
            "desperate": "glasses off, rubbing eyes, exhausted expression, dark circles, defeated",
        },
    }

    # Keep backward compat
    CHARACTER_PORTRAIT_PROMPTS = {
        k: f"{v}, cold and composed expression" for k, v in _PORTRAIT_BASE.items()
    }

    async def generate_character_portrait(
        self, character_id: str, mood: str = "calm", use_cache: bool = True
    ) -> Optional[str]:
        """Generate a character portrait for a specific mood. Returns URL or None."""
        cache_key = f"portrait_{character_id}_{mood}"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        base = self._PORTRAIT_BASE.get(character_id)
        if not base:
            return None

        # Get mood-specific expression
        expressions = self._MOOD_EXPRESSIONS.get(character_id, {})
        expression = expressions.get(mood, expressions.get("calm", "neutral expression"))

        prompt = f"{base}, {expression}"

        try:
            image_url = await self._call_modelscope(prompt)
            if image_url:
                self._cache[cache_key] = image_url
                print(f"[ImageAgent] Portrait generated for {character_id}/{mood}: {image_url[:60]}...")
            return image_url
        except Exception as e:
            print(f"[ImageAgent] Portrait generation failed for {character_id}/{mood}: {e}")
            return None

    async def generate_all_portraits(self, moods: Optional[Dict[str, str]] = None) -> dict:
        """Generate portraits for all characters. Returns {char_id: url}.

        If moods is provided ({char_id: mood}), generates mood-specific portraits.
        Otherwise generates default 'calm' portraits.
        """
        results = {}
        for cid in self._PORTRAIT_BASE:
            mood = (moods or {}).get(cid, "calm")
            url = await self.generate_character_portrait(cid, mood)
            if url:
                results[cid] = url
        return results

    async def generate_all_mood_variants(self) -> Dict[str, Dict[str, str]]:
        """Pre-generate all mood variants for all characters.

        Returns {char_id: {mood: url}}.
        Call this at game start to pre-cache all expression variants.
        """
        all_variants: Dict[str, Dict[str, str]] = {}
        tasks = []

        for cid in self._PORTRAIT_BASE:
            all_variants[cid] = {}
            expressions = self._MOOD_EXPRESSIONS.get(cid, {})
            for mood in expressions:
                tasks.append((cid, mood, self.generate_character_portrait(cid, mood, use_cache=True)))

        for cid, mood, coro in tasks:
            url = await coro
            if url:
                all_variants[cid][mood] = url

        print(f"[ImageAgent] Pre-generated {sum(len(v) for v in all_variants.values())} mood variants")
        return all_variants

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
