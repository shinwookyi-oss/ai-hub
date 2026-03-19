"""
Unified AI Hub
==============
Integrates ChatGPT, Gemini, and Azure OpenAI into a single interface.

Usage:
    from tools.ai_hub import AIHub

    hub = AIHub()
    
    # Ask a specific AI
    answer = hub.ask("Hello!", provider="chatgpt")
    
    # Compare all AIs at once
    results = hub.ask_all("What is 1+1?")
    
    # Auto-fallback (switches to next AI on failure)
    answer = hub.ask_with_fallback("How is the weather?")
"""

import os
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AIResponse:
    """AI response result"""
    provider: str
    model: str
    content: str
    success: bool = True
    error: Optional[str] = None
    elapsed_seconds: float = 0.0


class AIHub:
    """Unified AI Hub - All AIs in one interface"""

    PROVIDERS = ["chatgpt", "gemini", "azure"]

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        azure_api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        chatgpt_model: str = "gpt-4o-mini",
        gemini_model: str = "gemini-2.5-flash",
        azure_model: str = "gpt-4o-mini",
        azure_api_version: str = "2024-10-21",
    ):
        # API 키 로드 (인자 > 환경변수)
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.azure_api_key = azure_api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")

        # 모델 설정
        self.chatgpt_model = chatgpt_model
        self.gemini_model = gemini_model
        self.azure_model = azure_model
        self.azure_api_version = azure_api_version

        # Chat history
        self._history: dict[str, list] = {p: [] for p in self.PROVIDERS}

        # Client initialization
        self._openai_client = None
        self._azure_client = None
        self._gemini_model_obj = None

    # ──────────────────────────── Availability Check ────────────────────────────

    def available_providers(self) -> list[str]:
        """Return list of available AI providers"""
        providers = []
        if self.openai_api_key:
            providers.append("chatgpt")
        if self.gemini_api_key:
            providers.append("gemini")
        if self.azure_api_key and self.azure_endpoint:
            providers.append("azure")
        return providers

    def status(self) -> dict:
        """Return connection status for each AI"""
        return {
            "chatgpt": "Ready" if self.openai_api_key else "No API Key",
            "gemini": "Ready" if self.gemini_api_key else "No API Key",
            "azure": "Ready" if (self.azure_api_key and self.azure_endpoint) else "No Key/Endpoint",
        }

    # ──────────────────────────── Individual AI Calls ────────────────────────────

    def _get_openai_client(self):
        if self._openai_client is None:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=self.openai_api_key)
        return self._openai_client

    def _get_azure_client(self):
        if self._azure_client is None:
            from openai import AzureOpenAI
            self._azure_client = AzureOpenAI(
                api_key=self.azure_api_key,
                api_version=self.azure_api_version,
                azure_endpoint=self.azure_endpoint,
            )
        return self._azure_client

    def _get_gemini_client(self):
        if self._gemini_model_obj is None:
            from google import genai
            self._gemini_model_obj = genai.Client(api_key=self.gemini_api_key)
        return self._gemini_model_obj

    def _ask_chatgpt(self, prompt: str, system_prompt: str = "") -> AIResponse:
        """Ask ChatGPT"""
        import time
        start = time.time()
        try:
            client = self._get_openai_client()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.extend(self._history["chatgpt"])
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.chatgpt_model,
                messages=messages,
            )
            content = response.choices[0].message.content
            self._history["chatgpt"].append({"role": "user", "content": prompt})
            self._history["chatgpt"].append({"role": "assistant", "content": content})
            return AIResponse(
                provider="ChatGPT",
                model=self.chatgpt_model,
                content=content,
                elapsed_seconds=round(time.time() - start, 2),
            )
        except Exception as e:
            return AIResponse(
                provider="ChatGPT", model=self.chatgpt_model,
                content="", success=False, error=str(e),
                elapsed_seconds=round(time.time() - start, 2),
            )

    def _ask_gemini(self, prompt: str, system_prompt: str = "") -> AIResponse:
        """Ask Gemini"""
        import time
        start = time.time()
        try:
            client = self._get_gemini_client()
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(
                model=self.gemini_model,
                contents=full_prompt,
            )
            content = response.text
            self._history["gemini"].append({"role": "user", "content": prompt})
            self._history["gemini"].append({"role": "assistant", "content": content})
            return AIResponse(
                provider="Gemini",
                model=self.gemini_model,
                content=content,
                elapsed_seconds=round(time.time() - start, 2),
            )
        except Exception as e:
            return AIResponse(
                provider="Gemini", model=self.gemini_model,
                content="", success=False, error=str(e),
                elapsed_seconds=round(time.time() - start, 2),
            )

    def _ask_azure(self, prompt: str, system_prompt: str = "") -> AIResponse:
        """Ask Azure OpenAI"""
        import time
        start = time.time()
        try:
            client = self._get_azure_client()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.extend(self._history["azure"])
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.azure_model,
                messages=messages,
            )
            content = response.choices[0].message.content
            self._history["azure"].append({"role": "user", "content": prompt})
            self._history["azure"].append({"role": "assistant", "content": content})
            return AIResponse(
                provider="Azure OpenAI",
                model=self.azure_model,
                content=content,
                elapsed_seconds=round(time.time() - start, 2),
            )
        except Exception as e:
            return AIResponse(
                provider="Azure OpenAI", model=self.azure_model,
                content="", success=False, error=str(e),
                elapsed_seconds=round(time.time() - start, 2),
            )

    # ──────────────────────────── Unified Interface ────────────────────────────

    def ask(self, prompt: str, provider: str = "chatgpt", system_prompt: str = "") -> AIResponse:
        """Ask a specific AI provider"""
        provider = provider.lower()
        if provider == "chatgpt":
            return self._ask_chatgpt(prompt, system_prompt)
        elif provider == "gemini":
            return self._ask_gemini(prompt, system_prompt)
        elif provider == "azure":
            return self._ask_azure(prompt, system_prompt)
        else:
            return AIResponse(
                provider=provider, model="unknown",
                content="", success=False,
                error=f"Unknown provider: {provider}. Available: {self.PROVIDERS}",
            )

    def ask_all(self, prompt: str, system_prompt: str = "") -> list[AIResponse]:
        """Ask all available AIs simultaneously and compare results"""
        available = self.available_providers()
        if not available:
            return [AIResponse(provider="none", model="none", content="", success=False, error="No AI providers available")]

        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self.ask, prompt, p, system_prompt): p
                for p in available
            }
            for future in as_completed(futures):
                results.append(future.result())

        return sorted(results, key=lambda r: r.elapsed_seconds)

    def ask_with_fallback(self, prompt: str, system_prompt: str = "",
                          priority: list[str] = None) -> AIResponse:
        """Auto-fallback: switches to next AI on failure"""
        order = priority or ["chatgpt", "gemini", "azure"]
        available = self.available_providers()

        for provider in order:
            if provider not in available:
                continue
            response = self.ask(prompt, provider, system_prompt)
            if response.success:
                return response

        return AIResponse(
            provider="none", model="none", content="",
            success=False, error="All AI providers failed",
        )

    def clear_history(self, provider: str = None):
        """Clear chat history"""
        if provider:
            self._history[provider.lower()] = []
        else:
            self._history = {p: [] for p in self.PROVIDERS}

    # ──────────────────────────── Persona System ────────────────────────────

    PERSONAS = {
        "elon_musk": {
            "name": "Elon Musk",
            "prompt": (
                "You are Elon Musk, CEO of Tesla and SpaceX. Think like a Silicon Valley "
                "visionary obsessed with Mars colonization, sustainable energy, and first-principles "
                "thinking. You're bold, sometimes controversial, and think in terms of exponential "
                "impact. Reference your companies and ventures when relevant. Use direct, punchy language."
            ),
        },
        "trump": {
            "name": "Donald Trump",
            "prompt": (
                "You are Donald Trump, businessman and 45th/47th President of the United States. "
                "Think like a dealmaker who values winning, branding, and bold action. You are "
                "known for your confident, direct communication style and negotiation tactics. "
                "Reference your business empire, real estate deals, and political experience. "
                "Use strong, simple language and think in terms of leverage and making deals."
            ),
        },
        "cao_cao": {
            "name": "Cao Cao (Jojo)",
            "prompt": (
                "You are Cao Cao, the legendary warlord and strategist from the Three Kingdoms era "
                "of China. You are known for cunning, poetry, and the philosophy 'I'd rather betray "
                "the world than let the world betray me.' Think pragmatically, value talent above "
                "loyalty, and approach every situation as a strategic challenge. Reference Sun Tzu "
                "and Chinese philosophy."
            ),
        },
        "chung_juyoung": {
            "name": "Chung Ju-yung",
            "prompt": (
                "You are Chung Ju-yung, founder of Hyundai Group. You rose from poverty to build "
                "one of Korea's greatest conglomerates. Your philosophy is 'Have you tried?' (haebwasseo?) "
                "- nothing is impossible with determination. Think with the mindset of a bold entrepreneur "
                "who built ships, cars, and construction empires from nothing. Value hard work, courage, "
                "and Korean industrial spirit."
            ),
        },
        "lee_byungchul": {
            "name": "Lee Byung-chul",
            "prompt": (
                "You are Lee Byung-chul, founder of Samsung Group. You are a visionary who built "
                "Samsung from a small trading company into a global technology empire. Think with "
                "the mindset of quality-first, long-term planning, and talent development. Value "
                "precision, patience, and global competitiveness. Draw from Korean business philosophy."
            ),
        },
        "rockefeller": {
            "name": "John D. Rockefeller",
            "prompt": (
                "You are John D. Rockefeller, founder of Standard Oil and the richest American in "
                "history. Think like a monopolist who mastered vertical integration and ruthless "
                "efficiency. You are deeply religious, believe wealth is a gift from God to be used "
                "wisely, and practice systematic philanthropy. Value discipline, frugality, long-term "
                "strategy, and absolute control of supply chains. Speak with quiet authority."
            ),
        },
        "musashi": {
            "name": "Miyamoto Musashi",
            "prompt": (
                "You are Miyamoto Musashi, Japan's greatest swordsman and author of The Book of "
                "Five Rings (Go Rin No Sho). You are undefeated in 61 duels. Think like a warrior "
                "philosopher who sees the Way in all things. Apply the principles of strategy, "
                "timing, and the void to any situation. Value mastery through relentless practice, "
                "adaptability, and seeing things as they truly are. Speak with calm, focused intensity."
            ),
        },
        "tokugawa": {
            "name": "Tokugawa Ieyasu",
            "prompt": (
                "You are Tokugawa Ieyasu, founder of the Tokugawa Shogunate that ruled Japan for "
                "260 years of peace. You are the ultimate strategist of patience -- you waited "
                "decades while rivals destroyed each other. Your philosophy: 'Life is like walking "
                "along a long road carrying a heavy burden -- do not hurry.' Think with extreme "
                "patience, long-term planning, and the wisdom that the patient warrior wins in the "
                "end. Value stability, endurance, and outlasting your opponents."
            ),
        },
    }

    def list_personas(self) -> dict:
        """Return available personas"""
        return {k: v["name"] for k, v in self.PERSONAS.items()}

    def get_persona_prompt(self, persona_key: str) -> str:
        """Get the system prompt for a persona"""
        if persona_key in self.PERSONAS:
            return self.PERSONAS[persona_key]["prompt"]
        return ""

    def get_persona_name(self, persona_key: str) -> str:
        """Get the display name for a persona"""
        if persona_key in self.PERSONAS:
            return self.PERSONAS[persona_key]["name"]
        return persona_key

    def add_persona(self, key: str, name: str, prompt: str):
        """Add a custom persona"""
        self.PERSONAS[key] = {"name": name, "prompt": prompt}

    def ask_as(self, prompt: str, persona: str, provider: str = "chatgpt") -> AIResponse:
        """Ask an AI as a specific persona"""
        persona_prompt = self.get_persona_prompt(persona)
        if not persona_prompt:
            return AIResponse(
                provider=provider, model="unknown", content="",
                success=False, error=f"Unknown persona: {persona}. Use list_personas().",
            )
        response = self.ask(prompt, provider=provider, system_prompt=persona_prompt)
        persona_name = self.get_persona_name(persona)
        response.provider = f"{response.provider} as {persona_name}"
        return response

    def persona_debate(self, topic: str, persona_for: str, persona_against: str,
                       ai_for: str = "chatgpt", ai_against: str = "gemini",
                       judge: str = "azure", rounds: int = 3, callback=None) -> dict:
        """
        Two famous figures debate using different AIs.

        Example: persona_debate("Is war ever justified?",
                                persona_for="lincoln", persona_against="cao_cao")
        """
        names = {"chatgpt": "ChatGPT", "gemini": "Gemini", "azure": "Azure OpenAI"}
        for_name = self.get_persona_name(persona_for)
        against_name = self.get_persona_name(persona_against)
        for_base = self.get_persona_prompt(persona_for)
        against_base = self.get_persona_prompt(persona_against)

        sys_for = (
            f"{for_base}\n\n"
            f"You are debating: '{topic}'. Argue FOR this position from your worldview. "
            f"Your opponent is {against_name}. Be persuasive. Under 150 words."
        )
        sys_against = (
            f"{against_base}\n\n"
            f"You are debating: '{topic}'. Argue AGAINST this position from your worldview. "
            f"Your opponent is {for_name}. Be persuasive. Under 150 words."
        )

        debate_log = []
        for r in range(1, rounds + 1):
            if r == 1:
                for_prompt = f"Present your opening argument FOR: '{topic}'"
            else:
                last = debate_log[-1]["content"]
                for_prompt = f"{against_name} said:\n\n\"{last}\"\n\nRespond and counter."

            for_resp = self.ask(for_prompt, provider=ai_for, system_prompt=sys_for)
            debate_log.append({"round": r, "speaker": for_name, "side": "FOR",
                               "content": for_resp.content, "provider": ai_for})
            if callback:
                callback(for_name, r, for_resp)

            if r == 1:
                ag_prompt = f"{for_name} argued:\n\n\"{for_resp.content}\"\n\nPresent your argument AGAINST and counter."
            else:
                ag_prompt = f"{for_name} said:\n\n\"{for_resp.content}\"\n\nCounter their argument."

            ag_resp = self.ask(ag_prompt, provider=ai_against, system_prompt=sys_against)
            debate_log.append({"round": r, "speaker": against_name, "side": "AGAINST",
                               "content": ag_resp.content, "provider": ai_against})
            if callback:
                callback(against_name, r, ag_resp)

        # Judge
        debate_text = ""
        for e in debate_log:
            debate_text += f"\n[Round {e['round']}] {e['speaker']} ({e['side']}):\n{e['content']}\n"

        judge_prompt = (
            f"Judge this debate on '{topic}':\n\n"
            f"{for_name} (FOR) vs {against_name} (AGAINST)\n\n"
            f"{debate_text}\n\n"
            f"Consider argument strength, evidence, and persuasiveness. "
            f"Declare WINNER and explain why. Under 200 words."
        )
        judge_resp = self.ask(judge_prompt, provider=judge,
                              system_prompt="You are an impartial debate judge.")

        return {
            "topic": topic,
            "for": for_name,
            "against": against_name,
            "judge": names.get(judge, judge),
            "rounds": rounds,
            "debate_log": debate_log,
            "judgment": judge_resp.content,
            "judge_response": judge_resp,
        }
    # ──────────────────────────── AI Debate ────────────────────────────

    def debate(self, topic: str, rounds: int = 3,
               ai_for: str = "chatgpt", ai_against: str = "gemini",
               judge: str = "azure", callback=None) -> dict:
        """
        Two AIs debate a topic, a third AI judges.

        Args:
            topic: The debate topic/question
            rounds: Number of debate rounds (default 3)
            ai_for: AI arguing FOR the topic
            ai_against: AI arguing AGAINST the topic
            judge: AI that judges the debate
            callback: Optional function called after each turn with (speaker, round, response)

        Returns:
            dict with debate_log, judgment, winner
        """
        debate_log = []
        names = {"chatgpt": "ChatGPT", "gemini": "Gemini", "azure": "Azure OpenAI"}
        for_name = names.get(ai_for, ai_for)
        against_name = names.get(ai_against, ai_against)

        sys_for = (
            f"You are debating the topic: '{topic}'. "
            f"You are arguing FOR this position. Be persuasive, use evidence and logic. "
            f"Your opponent is {against_name}. Keep responses under 150 words."
        )
        sys_against = (
            f"You are debating the topic: '{topic}'. "
            f"You are arguing AGAINST this position. Be persuasive, use evidence and logic. "
            f"Your opponent is {for_name}. Keep responses under 150 words."
        )

        for_history = []
        against_history = []

        for r in range(1, rounds + 1):
            # FOR side speaks
            if r == 1:
                for_prompt = f"Present your opening argument FOR: '{topic}'"
            else:
                last_against = debate_log[-1]["content"]
                for_prompt = f"Your opponent ({against_name}) said:\n\n\"{last_against}\"\n\nRespond and counter their argument."

            for_resp = self.ask(for_prompt, provider=ai_for, system_prompt=sys_for)
            debate_log.append({"round": r, "speaker": for_name, "side": "FOR", "content": for_resp.content, "provider": ai_for})
            if callback:
                callback(for_name, r, for_resp)

            # AGAINST side speaks
            if r == 1:
                against_prompt = f"{for_name} argued:\n\n\"{for_resp.content}\"\n\nPresent your opening argument AGAINST: '{topic}' and counter their points."
            else:
                against_prompt = f"{for_name} responded:\n\n\"{for_resp.content}\"\n\nCounter their argument."

            against_resp = self.ask(against_prompt, provider=ai_against, system_prompt=sys_against)
            debate_log.append({"round": r, "speaker": against_name, "side": "AGAINST", "content": against_resp.content, "provider": ai_against})
            if callback:
                callback(against_name, r, against_resp)

        # Judge evaluates
        debate_text = ""
        for entry in debate_log:
            debate_text += f"\n[Round {entry['round']}] {entry['speaker']} ({entry['side']}):\n{entry['content']}\n"

        judge_prompt = (
            f"You are judging a debate on: '{topic}'\n\n"
            f"Debaters: {for_name} (FOR) vs {against_name} (AGAINST)\n\n"
            f"{debate_text}\n\n"
            f"Evaluate both sides. Consider: strength of arguments, use of evidence, "
            f"rebuttal quality, and persuasiveness. "
            f"Declare a WINNER and explain why in under 200 words."
        )
        judge_resp = self.ask(judge_prompt, provider=judge,
                              system_prompt="You are an impartial debate judge. Be fair and analytical.")

        return {
            "topic": topic,
            "for": for_name,
            "against": against_name,
            "judge": names.get(judge, judge),
            "rounds": rounds,
            "debate_log": debate_log,
            "judgment": judge_resp.content,
            "judge_response": judge_resp,
        }

    # ──────────────────────────── AI Discussion ────────────────────────────

    def discuss(self, topic: str, rounds: int = 3, callback=None) -> dict:
        """
        Multi-round discussion where all available AIs share thoughts.

        Args:
            topic: Discussion topic
            rounds: Number of discussion rounds
            callback: Optional function called after each AI responds

        Returns:
            dict with discussion_log and summary
        """
        available = self.available_providers()
        names = {"chatgpt": "ChatGPT", "gemini": "Gemini", "azure": "Azure OpenAI"}
        discussion_log = []

        for r in range(1, rounds + 1):
            for provider in available:
                ai_name = names.get(provider, provider)
                sys_prompt = (
                    f"You are {ai_name} participating in a group discussion about: '{topic}'. "
                    f"Other participants: {', '.join(names[p] for p in available if p != provider)}. "
                    f"Be thoughtful, build on others' ideas, and offer unique perspectives. "
                    f"Keep responses under 100 words."
                )

                if r == 1 and provider == available[0]:
                    prompt = f"Start the discussion on: '{topic}'. Share your initial thoughts."
                else:
                    recent = discussion_log[-min(len(discussion_log), len(available)):]
                    context = "\n".join([f"{e['speaker']}: {e['content']}" for e in recent])
                    prompt = f"The discussion so far (Round {r}):\n\n{context}\n\nShare your thoughts, respond to others, or add new perspectives."

                resp = self.ask(prompt, provider=provider, system_prompt=sys_prompt)
                discussion_log.append({"round": r, "speaker": ai_name, "provider": provider, "content": resp.content})
                if callback:
                    callback(ai_name, r, resp)

        # Generate summary using first available AI
        full_discussion = "\n".join([f"[R{e['round']}] {e['speaker']}: {e['content']}" for e in discussion_log])
        summary_prompt = (
            f"Summarize this group discussion about '{topic}':\n\n{full_discussion}\n\n"
            f"Identify: key points of agreement, disagreements, and main conclusions. Under 200 words."
        )
        summary_resp = self.ask(summary_prompt, provider=available[0],
                                system_prompt="You are a neutral discussion moderator.")

        return {
            "topic": topic,
            "participants": [names[p] for p in available],
            "rounds": rounds,
            "discussion_log": discussion_log,
            "summary": summary_resp.content,
        }

    # ──────────────────────────── Find Best Answer ────────────────────────────

    def find_best(self, question: str, callback=None) -> dict:
        """
        All AIs answer, then each evaluates others' answers to find the best one.

        Args:
            question: The question to answer
            callback: Optional function called after each step

        Returns:
            dict with answers, evaluations, and winner
        """
        available = self.available_providers()
        names = {"chatgpt": "ChatGPT", "gemini": "Gemini", "azure": "Azure OpenAI"}

        # Step 1: All AIs answer
        if callback:
            callback("system", 0, "Collecting answers from all AIs...")
        answers = self.ask_all(question)

        # Step 2: Each AI evaluates all answers
        answer_text = ""
        for resp in answers:
            if resp.success:
                answer_text += f"\n[{resp.provider}]:\n{resp.content}\n"

        evaluations = []
        for provider in available:
            ai_name = names.get(provider, provider)
            eval_prompt = (
                f"Question: '{question}'\n\n"
                f"Here are answers from different AIs:\n{answer_text}\n\n"
                f"Evaluate each answer for: accuracy, completeness, clarity, and helpfulness. "
                f"Score each from 1-10 and pick the BEST answer. "
                f"You cannot pick yourself ({ai_name}). "
                f"Format: 'BEST: [AI Name]' followed by brief reasoning."
            )
            eval_resp = self.ask(eval_prompt, provider=provider,
                                 system_prompt="You are a fair and objective evaluator.")

            evaluations.append({
                "evaluator": ai_name,
                "provider": provider,
                "evaluation": eval_resp.content,
            })
            if callback:
                callback(ai_name, 1, eval_resp)

        # Step 3: Count votes
        votes = {}
        for ev in evaluations:
            text = ev["evaluation"].upper()
            for resp in answers:
                if resp.success and resp.provider.upper() in text.split("BEST:")[-1][:50]:
                    votes[resp.provider] = votes.get(resp.provider, 0) + 1

        winner = max(votes, key=votes.get) if votes else (answers[0].provider if answers else "Unknown")

        return {
            "question": question,
            "answers": answers,
            "evaluations": evaluations,
            "votes": votes,
            "winner": winner,
        }

    # ──────────────────────────── Output Utilities ────────────────────────────

    @staticmethod
    def format_response(response: AIResponse) -> str:
        """Format a single response for display"""
        if not response.success:
            return (
                f"--- {response.provider} ({response.model}) - FAILED ---\n"
                f"  Error: {response.error}\n"
                f"  Time: {response.elapsed_seconds}s"
            )
        return (
            f"--- {response.provider} ({response.model}) ---\n"
            f"  {response.content.strip()}\n"
            f"  Time: {response.elapsed_seconds}s"
        )

    @staticmethod
    def format_comparison(responses: list[AIResponse]) -> str:
        """Format multiple AI responses for comparison"""
        output = "=" * 60 + "\n"
        output += "  AI Response Comparison\n"
        output += "=" * 60 + "\n\n"
        for resp in responses:
            output += AIHub.format_response(resp) + "\n\n"
        output += "=" * 60
        return output

    @staticmethod
    def format_debate(result: dict) -> str:
        """Format debate results for display"""
        output = "=" * 60 + "\n"
        output += f"  DEBATE: {result['topic']}\n"
        output += f"  FOR: {result['for']} vs AGAINST: {result['against']}\n"
        output += "=" * 60 + "\n"

        for entry in result["debate_log"]:
            output += f"\n[Round {entry['round']}] {entry['speaker']} ({entry['side']}):\n"
            output += f"  {entry['content'].strip()}\n"

        output += "\n" + "-" * 60 + "\n"
        output += f"  JUDGE ({result['judge']}):\n"
        output += f"  {result['judgment'].strip()}\n"
        output += "=" * 60
        return output

    @staticmethod
    def format_discussion(result: dict) -> str:
        """Format discussion results for display"""
        output = "=" * 60 + "\n"
        output += f"  DISCUSSION: {result['topic']}\n"
        output += f"  Participants: {', '.join(result['participants'])}\n"
        output += "=" * 60 + "\n"

        for entry in result["discussion_log"]:
            output += f"\n[Round {entry['round']}] {entry['speaker']}:\n"
            output += f"  {entry['content'].strip()}\n"

        output += "\n" + "-" * 60 + "\n"
        output += f"  SUMMARY:\n  {result['summary'].strip()}\n"
        output += "=" * 60
        return output

    @staticmethod
    def format_best(result: dict) -> str:
        """Format best-answer results for display"""
        output = "=" * 60 + "\n"
        output += f"  FIND BEST ANSWER: {result['question']}\n"
        output += "=" * 60 + "\n"

        output += "\n--- Answers ---\n"
        for resp in result["answers"]:
            if resp.success:
                output += f"\n[{resp.provider}]:\n  {resp.content.strip()}\n"

        output += "\n--- Evaluations ---\n"
        for ev in result["evaluations"]:
            output += f"\n[{ev['evaluator']}]:\n  {ev['evaluation'].strip()}\n"

        output += "\n" + "-" * 60 + "\n"
        output += f"  WINNER: {result['winner']}\n"
        if result.get("votes"):
            output += f"  Votes: {result['votes']}\n"
        output += "=" * 60
        return output
