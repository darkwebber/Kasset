"""
user_profiling.py — Lightweight user expertise detection.

Analyzes vocabulary and specificity in user messages to infer expertise level.
Injects tone hints into the system prompt so the model adapts its language.
"""

import re
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Vocabulary signals ──

# Technical terms that suggest above-average expertise
_EXPERT_TERMS = {
    # Programming
    "async", "await", "coroutine", "mutex", "semaphore", "deadlock",
    "polymorphism", "abstraction", "encapsulation", "inheritance",
    "dependency injection", "inversion of control", "singleton",
    "middleware", "ORM", "REST", "GraphQL", "gRPC", "websocket",
    "containerization", "kubernetes", "docker", "CI/CD", "pipeline",
    "microservice", "monorepo", "idempotent", "immutable", "memoization",
    "closure", "currying", "monad", "functor", "higher-order",
    "type inference", "generics", "variance", "covariance",
    "garbage collection", "heap", "stack", "syscall", "ABI",
    "SIMD", "vectorization", "cache line", "branch prediction",
    # Data / ML
    "gradient descent", "backpropagation", "epoch", "batch size",
    "learning rate", "overfitting", "regularization", "dropout",
    "attention mechanism", "transformer", "embedding", "tokenizer",
    "fine-tuning", "LoRA", "quantization", "RLHF", "PPO",
    "precision", "recall", "F1", "AUC", "ROC",
    "PCA", "t-SNE", "clustering", "dimensionality reduction",
    # Math / Science
    "eigenvalue", "eigenvector", "determinant", "jacobian",
    "fourier transform", "convolution", "laplacian",
    "bayesian", "posterior", "prior", "likelihood",
    "stochastic", "markov", "ergodic", "entropy",
    # Systems
    "TCP", "UDP", "TLS", "mTLS", "certificate pinning",
    "load balancer", "reverse proxy", "NAT", "CIDR",
    "inode", "filesystem", "page fault", "virtual memory",
}

# Indicators of beginner-level communication
_BEGINNER_PATTERNS = [
    r"\bhow do I\b",
    r"\bwhat is a?\b",
    r"\bcan you explain\b",
    r"\bI('m| am) (new|a beginner|learning|just starting)\b",
    r"\bELI5\b",
    r"\bin simple terms\b",
    r"\bstep by step\b",
    r"\bI don'?t (understand|know|get)\b",
]

_BEGINNER_COMPILED = [re.compile(p, re.IGNORECASE) for p in _BEGINNER_PATTERNS]


def _count_expert_terms(text: str) -> int:
    """Count how many expert-level terms appear in the text."""
    text_lower = text.lower()
    count = 0
    for term in _EXPERT_TERMS:
        if term in text_lower:
            count += 1
    return count


def _count_beginner_signals(text: str) -> int:
    """Count beginner-level patterns in the text."""
    count = 0
    for pattern in _BEGINNER_COMPILED:
        if pattern.search(text):
            count += 1
    return count


def _measure_specificity(text: str) -> float:
    """Score 0-1 based on how specific/detailed the message is.
    Higher = more specific (longer sentences, more technical detail)."""
    words = text.split()
    if not words:
        return 0.0

    word_count = len(words)
    # Average word length (longer words tend to be more technical)
    avg_word_len = sum(len(w) for w in words) / word_count

    # Presence of code-like tokens
    code_tokens = sum(1 for w in words if any(c in w for c in "{}()[];=<>./\\"))

    # Normalize to 0-1
    length_score = min(1.0, word_count / 100)  # caps at 100 words
    complexity_score = min(1.0, (avg_word_len - 3.0) / 4.0)  # avg word len 3-7
    code_score = min(1.0, code_tokens / 10)

    return (length_score * 0.3 + complexity_score * 0.4 + code_score * 0.3)


def detect_expertise(messages: List[dict]) -> str:
    """Analyze user messages and return expertise level: 'beginner', 'intermediate', or 'expert'.

    Only analyzes user messages. Returns 'intermediate' as default if insufficient signal.
    """
    user_texts = [m["content"] for m in messages if m.get("role") == "user"]
    if not user_texts:
        return "intermediate"

    # Only analyze last 5 messages for recency
    recent = user_texts[-5:]
    combined = " ".join(recent)

    expert_count = _count_expert_terms(combined)
    beginner_count = _count_beginner_signals(combined)
    specificity = _measure_specificity(combined)

    # Scoring
    expert_score = min(1.0, expert_count / 5)  # 5+ expert terms = max
    beginner_score = min(1.0, beginner_count / 3)  # 3+ beginner signals = max

    # Decision
    if expert_score > 0.6 and beginner_score < 0.3 and specificity > 0.4:
        return "expert"
    elif beginner_score > 0.5 or (specificity < 0.2 and expert_score < 0.2):
        return "beginner"
    else:
        return "intermediate"


def get_tone_hint(expertise: str) -> Optional[str]:
    """Return a system prompt hint based on detected expertise level.
    Returns None for intermediate (no adjustment needed)."""
    if expertise == "expert":
        return (
            "\n[User Expertise: Advanced] "
            "Use precise technical language. Skip basic explanations. "
            "Reference specific APIs, patterns, and trade-offs. "
            "Be direct and concise — the user knows the fundamentals."
        )
    elif expertise == "beginner":
        return (
            "\n[User Expertise: Beginner] "
            "Use clear, simple language. Define technical terms on first use. "
            "Provide concrete examples. Break complex topics into small steps. "
            "Offer to explain further if something might be unclear."
        )
    return None
