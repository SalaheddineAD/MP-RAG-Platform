from typing import List, Literal
import spacy
from langchain_text_splitters import RecursiveCharacterTextSplitter


class Chunker:
    """Multi-strategy chunking for manufacturing documents."""
    
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.nlp = spacy.load("en_core_web_sm")
        
        self.recursive_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
    
    def recursive_chunk(self, text: str, source: str) -> List[dict]:
        """Standard recursive character splitting."""
        chunks = self.recursive_splitter.split_text(text)
        return [
            {
                "text": chunk,
                "source": source,
                "chunk_index": i,
                "strategy": "recursive"
            }
            for i, chunk in enumerate(chunks) if chunk.strip()
        ]
    
    def semantic_chunk(self, text: str, source: str) -> List[dict]:
        """Split on sentence boundaries using spaCy."""
        doc = self.nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sent in sentences:
            sent_len = len(sent.split())
            if current_length + sent_len > self.chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sent]
                current_length = sent_len
            else:
                current_chunk.append(sent)
                current_length += sent_len
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return [
            {
                "text": chunk,
                "source": source,
                "chunk_index": i,
                "strategy": "semantic"
            }
            for i, chunk in enumerate(chunks)
        ]
    
    def chunk(
        self, 
        text: str, 
        source: str, 
        strategy: Literal["recursive", "semantic", "agentic"] = "recursive"
    ) -> List[dict]:
        if strategy == "recursive":
            return self.recursive_chunk(text, source)
        elif strategy == "semantic":
            return self.semantic_chunk(text, source)
        elif strategy == "agentic":
            # For now, delegate to semantic. You'll upgrade this later.
            return self.semantic_chunk(text, source)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")