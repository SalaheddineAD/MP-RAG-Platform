# How to Create a Golden Evaluation Set for RAG

A "golden set" is a collection of question-answer pairs where **you already know the correct answer** because you read the document yourself. It's called "golden" because it's the ground truth — the perfect standard you measure your AI against.

Think of it like a teacher's answer key. The teacher reads the textbook, writes questions, and knows the answers. Then they grade the student's test by comparing against this key. Your golden set is your answer key. Your RAG system is the student.

---

## The Exact Process (Do This Now)

### Step 1: Pick 3-5 Documents You Actually Read

Don't use documents you haven't read. You can't write questions about something you don't understand.

Pick documents that are:
- **Dense with facts** (specs, numbers, procedures)
- **5-15 pages each** (manageable to read fully)
- **Relevant to manufacturing** (battery specs, torque procedures, safety protocols)

Good sources:
- NASA technical reports on battery thermal management
- NIST manufacturing guidelines
- Any service manual PDF you have

### Step 2: Read One Document. Write Questions Immediately.

After reading ONE document, close it and write 3-5 questions from memory.

**Why from memory?** Because you want questions a real user would ask — not questions that copy-paste sentences from the text. If you copy-paste, your RAG will "cheat" by matching keywords instead of understanding meaning.

### Step 3: For Each Question, Write the Exact Answer

The answer should be:
- **Specific** ("45 N·m" not "the torque spec")
- **Verifiable** (you can point to the exact page/paragraph)
- **Short** (1-2 sentences max — this is a fact, not an essay)

### Step 4: Record the Source Location

Note:
- Which PDF file
- Which page number (or approximate location)
- Which chunk index (you'll fill this in after ingestion)

This lets you debug later: "The RAG retrieved chunk 5, but the answer was in chunk 12. Why?"

---

## Example Golden Set Entry

**Document:** `nasa_battery_thermal_mgmt.pdf` (read pages 1-8)

**Question:** What is the maximum operating temperature for lithium-ion cells before thermal runaway risk increases?

**Expected Answer:** 45°C

**Source:** Page 4, Section 3.2, paragraph 2

**Why this question is good:**
- It asks for a specific number (45°C)
- It requires understanding "thermal runaway" as a concept
- The answer is a single fact, not a summary
- A real engineer would ask this on the factory floor

**Why this question is bad (don't do this):**
- ❌ "What does Section 3.2 say about temperature?" (too broad, no single answer)
- ❌ "According to the document on page 4, what is the max temperature?" (gives away the location)
- ❌ "Summarize the thermal management section" (not a fact, hard to grade)

---

## Types of Questions to Include

| Type | Example | Why It Tests |
|------|---------|-------------|
| **Numerical fact** | "What is the torque spec?" | Can RAG find exact numbers? |
| **Comparative** | "Which material has higher conductivity, X or Y?" | Can RAG reason across chunks? |
| **Procedural** | "What is the first step in the safety shutdown?" | Can RAG follow sequences? |
| **Negative** | "What temperature should NOT be exceeded?" | Can RAG understand constraints? |
| **Cross-document** | "Do the battery spec and safety manual agree on max voltage?" | Advanced: requires multiple docs |

For your first golden set, focus on **numerical facts** and **procedural** questions. They're the easiest to grade and the most valuable for manufacturing.

---

## The JSONL Format

Each line is a separate JSON object. No commas between lines. No outer array.

```jsonl
{"question": "What is the maximum operating temperature for lithium-ion cells?", "expected_answer": "45°C", "source": "nasa_battery_thermal_mgmt.pdf", "page": 4, "difficulty": "easy"}
{"question": "What torque is specified for the battery mount bracket?", "expected_answer": "45 N·m (33 lb·ft)", "source": "battery_spec_2026.pdf", "page": 12, "difficulty": "easy"}
{"question": "Which cooling method is recommended for high-discharge scenarios?", "expected_answer": "Liquid cooling with glycol-water mixture", "source": "nasa_battery_thermal_mgmt.pdf", "page": 7, "difficulty": "medium"}
```

**Fields:**
- `question`: The exact question a user would type
- `expected_answer`: The ground-truth answer
- `source`: Which document contains the answer
- `page`: Approximate page (for your debugging)
- `difficulty`: `easy` (single fact), `medium` (requires synthesis), `hard` (cross-document)

---

## How Many Questions Do You Need?

| Goal | Minimum | Ideal |
|------|---------|-------|
| Proof of concept | 10 | 20 |
| Statistical significance | 30 | 50 |
| Production monitoring | 100+ | 500+ |

**For your resume: 20 is the sweet spot.**
- 10 easy (single fact)
- 7 medium (requires reading a paragraph)
- 3 hard (requires connecting two pieces of info)

This shows you understand that evaluation needs **variety**, not just volume.

---

## Common Mistakes

| Mistake | Why It Hurts |
|---------|-------------|
| Writing questions while looking at the text | Questions become keyword-matching exercises, not real user queries |
| Only easy questions | Your eval score will be artificially high (100% on trivia) |
| Vague expected answers | "It depends" is impossible to grade automatically |
| Not recording source location | When RAG fails, you can't debug why |
| Reusing the same document for all 20 | Doesn't test generalization across document types |

---

## Your Next 2 Hours

1. **Find 3 PDFs** (NASA reports, NIST docs, or any technical manual)
2. **Read one fully** (15 min)
3. **Write 5 questions from memory** (15 min)
4. **Repeat for docs 2 and 3** (30 min)
5. **Format as JSONL** (15 min)
6. **Ingest all 3 docs into your RAG** (15 min)
7. **Run /evaluate and record scores** (15 min)

Total: ~2 hours. You'll have a real golden set with real scores.
