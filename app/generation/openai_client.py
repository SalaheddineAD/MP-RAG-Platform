from typing import List, Dict
from openai import OpenAI
from app.config import get_settings


class OpenAIGenerator:
    """GPT-4o-mini for fast, cheap generation."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        self.model = self.settings.OPENAI_LLM_MODEL
    
    def generate(self, query: str, contexts: List[dict], max_tokens: int = 1024) -> Dict:
        context_text = "\n\n".join([
            f"[Source: {ctx['source']}, Chunk: {ctx.get('chunk_index', 0)}]\n{ctx['text']}"
            for ctx in contexts
        ])
        
        system_prompt = """You are a manufacturing engineering assistant. 
Answer based ONLY on the provided documentation.
Every factual claim must include a citation in the format [Source: filename, Chunk: N].
If the answer is not in the documentation, say "I don't have sufficient information."
Be concise and technical."""
        
        user_message = f"""Documentation:
{context_text}

Question: {query}

Answer with citations:"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=max_tokens,
            temperature=0.1
        )
        
        content = response.choices[0].message.content or ""
        usage = response.usage
        
        return {
            "answer": content,
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
            "model_id": self.model
        }