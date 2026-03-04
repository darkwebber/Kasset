import json
import logging
import re
from typing import List, Dict, Any, Generator, Tuple
from .tool_registry import execute_tool

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
    def __init__(self, model_client, config):
        """
        model_client: object with a .stream_generate() method
        config: LoadedConfig from CartridgeLoader
        """
        self.model_client = model_client
        self.config = config
        
    def _build_system_message(self) -> Dict[str, str]:
        # Append available tools context to the base merged prompt
        tools_desc = "\nAvailable tools:\n" + "\n".join(f"- {t}" for t in self.config.tools)
        return {"role": "system", "content": self.config.merged_prompt + tools_desc}

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
        
        # Max rounds of tool calling
        MAX_TOOL_ROUNDS = 3
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
            else:
                tool_result = execute_tool(tool_name, tool_args)
                
            yield json.dumps({
                "type": "tool_result", 
                "data": {"name": tool_name, "result": tool_result}
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
            yield json.dumps({"type": "error", "data": "Max tool rounds reached."})
