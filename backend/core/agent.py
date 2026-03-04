import json
import logging
import re
from typing import List, Dict, Any, Generator, Tuple, Optional
from .tool_registry import execute_tool
from .persistence import user_memory, prompt_cache, chat_store

logger = logging.getLogger(__name__)

def parse_thinking(raw: str) -> Tuple[str, str]:
    """Extract thinking content from model output."""
    tag_pairs = [
        ("<think>", "</think>"),
        ("<|thinking|>", "<|/thinking|>"),
    ]
    for open_tag, close_tag in tag_pairs:
        if close_tag in raw:
            if open_tag in raw:
                start = raw.index(open_tag) + len(open_tag)
                end = raw.index(close_tag)
                thought = raw[start:end].strip()
                answer = (raw[:raw.index(open_tag)] + raw[end + len(close_tag):]).strip()
                return thought, answer
            else:
                parts = raw.split(close_tag, 1)
                return parts[0].strip(), parts[1].strip()

    for open_tag, _ in tag_pairs:
        if open_tag in raw:
            start = raw.index(open_tag) + len(open_tag)
            return raw[start:].strip(), ""
            
    return "", raw.strip()

def extract_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Extract tool call JSON from <tool_call> tags."""
    try:
        match = re.search(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL | re.IGNORECASE)
        if match:
            return json.loads(match.group(1).strip())
    except Exception as e:
        logger.warning(f"Failed to parse tool call: {e}")
    return None

class Agent:
    # Rough chars-per-token estimate for context budgeting
    CHARS_PER_TOKEN = 3.5
    # Reserve tokens for generation output
    GENERATION_RESERVE = 4096
    # Max context window (conservative estimate for most models)
    MAX_CONTEXT_TOKENS = 28000

    def __init__(self, model_client, config):
        """
        model_client: object with a .stream_generate() method
        config: LoadedConfig from CartridgeLoader
        """
        self.model_client = model_client
        self.config = config

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token count estimate from character length."""
        return max(1, int(len(text) / Agent.CHARS_PER_TOKEN))

    def _trim_context(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Trim conversation history to fit within context budget.
        Strategy: Always keep system message + last N messages that fit.
        If tool results are very large, truncate them.
        """
        budget = self.MAX_CONTEXT_TOKENS - self.GENERATION_RESERVE - self.config.suggested_tokens

        # Always keep the system message (index 0)
        if not messages:
            return messages

        system_msg = messages[0] if messages[0]["role"] == "system" else None
        history = messages[1:] if system_msg else list(messages)

        # First pass: truncate very long tool result messages
        MAX_TOOL_RESULT_CHARS = 3000
        trimmed_history = []
        for msg in history:
            content = msg["content"]
            if msg["role"] == "user" and content.startswith("Tool result for ") and len(content) > MAX_TOOL_RESULT_CHARS:
                content = content[:MAX_TOOL_RESULT_CHARS] + "\n... (output truncated)"
            trimmed_history.append({**msg, "content": content})

        # Calculate system message cost
        system_cost = self._estimate_tokens(system_msg["content"]) if system_msg else 0
        remaining_budget = budget - system_cost

        if remaining_budget <= 0:
            logger.warning("System prompt alone exceeds context budget")
            remaining_budget = 2000  # fallback minimum

        # Build from most recent, adding messages until budget exhausted
        selected = []
        used = 0
        for msg in reversed(trimmed_history):
            msg_tokens = self._estimate_tokens(msg["content"])
            if used + msg_tokens > remaining_budget:
                break
            selected.insert(0, msg)
            used += msg_tokens

        # If we trimmed messages, try to include a summary of what was dropped
        dropped_msgs = trimmed_history[:len(trimmed_history) - len(selected)]
        dropped = len(dropped_msgs)
        result = []
        if system_msg:
            result.append(system_msg)
        if dropped > 0:
            # Check if we have a cached summary for these messages
            cached = prompt_cache.get_summary(dropped_msgs)
            if cached:
                summary_text = cached
            else:
                # Build a lightweight summary from dropped messages
                summary_parts = []
                for msg in dropped_msgs:
                    role = msg["role"]
                    content = msg["content"][:150]
                    if role == "user" and not content.startswith("Tool result"):
                        summary_parts.append(f"User: {content}")
                    elif role == "assistant":
                        summary_parts.append(f"Assistant: {content}")
                summary_text = "; ".join(summary_parts[-6:])  # Keep last 6 summaries
                if summary_text:
                    prompt_cache.store_summary(dropped_msgs, summary_text)

            context_note = f"[Earlier conversation summary ({dropped} messages): {summary_text}]" if summary_text else f"[{dropped} earlier messages trimmed]"
            result.append({
                "role": "system",
                "content": context_note
            })
            logger.info(f"Context trimmed: dropped {dropped} messages, keeping {len(selected)}")
        result.extend(selected)
        return result
        
    TOOL_DESCRIPTIONS = {
        "get_current_time": {"desc": "Get the current local date and time.", "params": {}},
        "list_directory": {"desc": "List directory contents with file sizes.", "params": {"path": "Directory path (default: '.')"}},
        "get_system_info": {"desc": "Get system overview: OS, hardware, disk, uptime.", "params": {}},
        "search_files": {"desc": "Search for files matching a glob pattern (max 50 results).", "params": {"pattern": "Glob pattern to match", "directory": "Directory to search (default: '~')"}},
        "read_file": {"desc": "Read a text file (max 200 lines / 50KB).", "params": {"path": "File path to read", "max_lines": "Max lines to read (default: 100)"}},
        "run_command": {"desc": "Run whitelisted read-only shell commands (30s timeout, pipes allowed).", "params": {"command": "Shell command to run"}},
        "calculate": {"desc": "Evaluate a math expression safely.", "params": {"expression": "Math expression to evaluate"}},
        "execute_python": {"desc": "Execute Python code in a sandbox. Captures stdout/stderr and matplotlib plots. pandas (pd), numpy (np), and matplotlib.pyplot (plt) are pre-imported.", "params": {"code": "Python code to execute"}},
    }

    def _build_system_message(self) -> Dict[str, str]:
        # Build detailed tool descriptions for the model
        tool_lines = []
        for t in self.config.tools:
            info = self.TOOL_DESCRIPTIONS.get(t, {"desc": t, "params": {}})
            params_str = ", ".join(f'{k}: {v}' for k, v in info["params"].items())
            tool_lines.append(f"- **{t}**({params_str}): {info['desc']}")
        
        tools_block = (
            "\n\n## Available Tools\n"
            "To use a tool, wrap the call in XML tags like this:\n"
            '<tool_call>{"name": "tool_name", "arguments": {"param": "value"}}</tool_call>\n\n'
            + "\n".join(tool_lines)
        )
        
        # Inject user memory if available
        memory_block = user_memory.get_context_block()
        
        return {"role": "system", "content": self.config.merged_prompt + tools_block + memory_block}

    def chat_stream(
        self, 
        history: List[Dict[str, str]], 
        image_path: str = None
    ) -> Generator[str, None, None]:
        """
        Executes a turn of conversation with multi-step tool loop.
        Yields JSON strings containing SSE events: { "type": "...", "data": ... }
        """
        base_history = [self._build_system_message()] + history
        
        # Trim context to fit within budget
        base_history = self._trim_context(base_history)
        
        # Emit context info for frontend
        total_chars = sum(len(m["content"]) for m in base_history)
        est_tokens = self._estimate_tokens(" ".join(m["content"] for m in base_history))
        yield json.dumps({
            "type": "context_info",
            "data": {
                "message_count": len(history),
                "estimated_tokens": est_tokens,
                "max_tokens": self.MAX_CONTEXT_TOKENS,
            }
        })
        
        # Max rounds of tool calling
        MAX_TOOL_ROUNDS = 8
        consecutive_failures = 0
        
        current_history = list(base_history)
        
        for tool_round in range(MAX_TOOL_ROUNDS):
            # 1. Stream Model Generation
            accumulated = ""
            thinking_done = False
            yield json.dumps({"type": "status", "data": "Generating..."})
            
            for chunk in self.model_client.stream_generate(
                messages=current_history,
                image=image_path if tool_round == 0 else None,
                max_tokens=self.config.suggested_tokens,
                thinking=self.config.suggested_thinking
            ):
                accumulated += chunk
                
                # Check for thinking completion to stream actual content
                if "</think>" in accumulated:
                    if not thinking_done:
                        thinking_done = True
                        yield json.dumps({"type": "think_end"})
                    
                    _, answer = parse_thinking(accumulated)
                    if answer.strip():
                        yield json.dumps({"type": "token", "data": chunk})
                elif self.config.suggested_thinking:
                    content = accumulated
                    if "<think>" in content:
                        content = content[content.index("<think>") + len("<think>"):]
                    if content.strip():
                        yield json.dumps({"type": "think_token", "data": chunk})
                else:
                    yield json.dumps({"type": "token", "data": chunk})

            # 2. Process complete generation
            thought, text = parse_thinking(accumulated)
            
            tool_req = extract_tool_call(text)
            if not tool_req:
                # Final answer reached
                yield json.dumps({"type": "done", "data": text})
                break
                
            # 3. Tool Execution Phase
            tool_name = tool_req.get("name", "")
            tool_args = tool_req.get("arguments", {})
            
            yield json.dumps({
                "type": "tool_start", 
                "data": {"name": tool_name, "args": tool_args}
            })
            
            if tool_name not in self.config.tools:
                tool_result = f"Error: Tool '{tool_name}' is not enabled in this cartridge."
                sandbox_images = []
            else:
                raw_result = execute_tool(tool_name, tool_args)
                # Sandbox returns a dict with 'output' and 'images'
                if isinstance(raw_result, dict) and "images" in raw_result:
                    tool_result = raw_result["output"]
                    sandbox_images = raw_result.get("images", [])
                else:
                    tool_result = str(raw_result)
                    sandbox_images = []
                
            yield json.dumps({
                "type": "tool_result", 
                "data": {"name": tool_name, "result": tool_result}
            })
            
            # Send sandbox images as separate events
            if sandbox_images:
                yield json.dumps({
                    "type": "sandbox_images",
                    "data": sandbox_images
                })
            
            # Failure tracking
            is_failure = tool_result in ("(no output)", "") or str(tool_result).startswith("Error:")
            consecutive_failures = consecutive_failures + 1 if is_failure else 0
            
            if consecutive_failures >= 2:
                yield json.dumps({"type": "status", "data": "Tool failed repeatedly. Generating final response..."})
                failure_note = "\nIMPORTANT: Multiple tools failed. Give your best final answer with the data you have."
            else:
                failure_note = ""
                
            # Append interaction to history for next synthesis step
            current_history.append({"role": "assistant", "content": text})
            current_history.append({"role": "user", "content": f"Tool result for {tool_name}: {tool_result}{failure_note}"})
            
            if consecutive_failures >= 2:
                # Do one last non-tool call to summarize
                final_res = self.model_client.generate(current_history, max_tokens=self.config.suggested_tokens, thinking=False)
                _, final_text = parse_thinking(final_res)
                yield json.dumps({"type": "token", "data": final_text})
                yield json.dumps({"type": "done", "data": final_text})
                break
        else:
            # Hit max rounds — do a final summarizing generation instead of erroring
            current_history.append({"role": "user", "content": "You have reached the maximum number of tool rounds. Please give your best final answer now with the information you have gathered so far."})
            final_res = self.model_client.generate(current_history, max_tokens=self.config.suggested_tokens, thinking=False)
            _, final_text = parse_thinking(final_res)
            yield json.dumps({"type": "token", "data": final_text})
            yield json.dumps({"type": "done", "data": final_text})
        
        # Post-conversation: extract user memories
        try:
            extracted = user_memory.extract_memories_from_conversation(history)
            new_memories = []
            for mem_type, mem_content in extracted:
                mem = user_memory.add(mem_content, memory_type=mem_type, source="auto")
                if mem.get("hits", 1) == 1:  # Only report newly created
                    new_memories.append(mem)
            if new_memories:
                yield json.dumps({
                    "type": "memory_update",
                    "data": [{"content": m["content"], "type": m["type"]} for m in new_memories]
                })
                logger.info(f"Extracted {len(new_memories)} new memories from conversation")
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}")
