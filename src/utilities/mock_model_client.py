"""
Mock AI Model Client for Testing/Development

This module provides mock implementations of AI model API clients (OpenAI, Anthropic/Claude)
that return pre-defined responses without making actual API calls, saving costs during development.

Usage:
    Set environment variable USE_MOCK_MODEL=true to enable mocking.

Example:
    import os
    os.environ["USE_MOCK_MODEL"] = "true"

    from utilities.mock_model_client import MockOpenAI, MockAnthropic
    openai_client = MockOpenAI()  # Mock OpenAI client
    claude_client = MockAnthropic()  # Mock Anthropic/Claude client
"""

import asyncio
from typing import Optional


class MockChatCompletion:
    """Mock chat completion response"""

    def __init__(self, content: str, model: str = "gpt-4"):
        self.id = "mock-completion-id"
        self.choices = [MockChoice(content)]
        self.created = 1234567890
        self.model = model
        self.object = "chat.completion"
        self.usage = MockUsage()


class MockChoice:
    """Mock choice in completion response"""

    def __init__(self, content: str):
        self.finish_reason = "stop"
        self.index = 0
        self.message = MockMessage(content)


class MockMessage:
    """Mock message in choice"""

    def __init__(self, content: str):
        self.content = content
        self.role = "assistant"
        self.tool_calls = None  # Mock doesn't support tool calls


class MockUsage:
    """Mock token usage"""

    def __init__(self):
        self.completion_tokens = 100
        self.prompt_tokens = 50
        self.total_tokens = 150


class MockChatCompletions:
    """Mock chat completions endpoint"""

    # Default responses for common prompts
    DEFAULT_RESPONSES = {
        "distill": """Artificial intelligence has become a significant focus in today's technology-driven world. At its core, artificial intelligence involves developing systems that can perform tasks that typically require human intelligence. This includes reasoning, problem-solving, learning from experience, and understanding natural language.

One of the primary goals of artificial intelligence is effective reasoning and problem-solving. These systems are designed to evaluate situations and make decisions based on available information. Machine learning plays a crucial role here, allowing AI systems to improve their performance over time through experience.

Natural language processing is another key component, enabling computers to understand and generate human language. This technology powers applications like virtual assistants, language translation services, and chatbots that can engage in meaningful conversations with users.

AI has found applications across numerous industries including healthcare, finance, transportation, and entertainment. In healthcare, AI assists in diagnosing diseases and recommending treatment plans. In finance, it helps detect fraud and make investment predictions. Self-driving cars represent a major application in transportation.

However, the development of artificial intelligence also raises important ethical questions about privacy, job displacement, and decision-making transparency. As AI systems become more sophisticated, addressing these concerns becomes increasingly important for society.""",
        "translate": """人工智能，通常缩写为AI，是计算机科学的一个领域，旨在创建能够执行通常需要人类智能的任务的系统。这包括推理、解决问题和理解自然语言等各种能力。人工智能的目标各不相同，从简单的决策到更复杂的数据学习过程。

人工智能的一个关键方面是其有效表示知识的能力。这涉及将信息结构化，以便机器能够理解和处理。此外，规划和决策对人工智能系统至关重要，使它们能够实现特定目标。

机器学习是人工智能的一个子集，专注于开发能够从数据中学习并随着时间推移改进的算法。这种方法已被证明在图像识别、自然语言处理和预测建模等任务中非常有效。

人工智能的应用范围广泛，从医疗诊断到金融预测。在医疗保健领域，人工智能可以帮助分析医学图像并建议治疗方案。在金融领域，它用于检测欺诈活动和预测市场趋势。

随着人工智能技术的不断发展，关于伦理考虑、隐私问题和工作岗位流失的讨论也变得越来越重要。社会必须解决这些挑战，以确保人工智能的负责任发展和部署。""",
        "name": "Understanding Artificial Intelligence and Its Impact",
        "description": "Explore how artificial intelligence mimics human intelligence through reasoning, learning, and natural language processing, impacting various industries.",
        "name_chinese": "人工智能的基础与应用前景",
        "description_chinese": "人工智能（AI）是模拟人类智能的计算机系统，广泛应用于医疗、金融和游戏等领域。随着技术的进步， AI 的伦理问题和社会影响也受到越来越多的关注。",
        # Ingest service URL scoring response (format: "N: SCORE=X.X REASON=...")
        "url_scoring": lambda num_urls: "\n".join(
            [
                f"{i+1}: SCORE=0.8 REASON=Specific article about AI and technology"
                for i in range(num_urls)
            ]
        ),
        # Ingest service content verification response (JSON format) - legacy combined call
        "content_verification": lambda num_urls: (
            '{"page_type": "CONCRETE", "url_scores": ['
            + ", ".join(["0.85"] * num_urls)
            + "]}"
        )
        if num_urls > 0
        else '{"page_type": "CONCRETE", "url_scores": []}',
        # Ingest service page classification response (JSON format) - new separate call
        "page_classification": '{"page_type": "COLLECTION"}',
        # Ingest service URL scoring response (JSON format) - new separate call with enhanced metadata
        "url_scoring_json": lambda num_urls: (
            '{"urls": ['
            + ", ".join(
                [
                    f'{{"score": 0.85, "title": "Mock Article Title {i+1}", "category": "content"}}'
                    for i in range(num_urls)
                ]
            )
            + "]}"
        )
        if num_urls > 0
        else '{"urls": []}',
        # Exam extraction response (JSON format) - for educational exam ingestion
        "exam_extraction": lambda: """[
  {"problem_number": "1", "preamble": null, "question_body": "What is the derivative of f(x) = x^2 + 3x + 5?", "choices": ["2x + 3", "x^2 + 3", "2x + 5", "x + 3"], "answer": "2x + 3", "answer_choice_index": 0, "explanation": "Using the power rule, the derivative of x^2 is 2x, the derivative of 3x is 3, and the derivative of a constant is 0.", "type": "multiple_choice", "category": "calculus derivatives"},
  {"problem_number": "2", "preamble": null, "question_body": "Solve for x: 2x + 5 = 15", "answer": "x = 5", "answer_choice_index": null, "explanation": "Subtract 5 from both sides to get 2x = 10, then divide by 2 to get x = 5.", "type": "short_answer", "category": "algebra linear equations"},
  {"problem_number": "3", "preamble": null, "question_body": "True or False: The slope of a horizontal line is zero.", "answer": "True", "answer_choice_index": null, "explanation": "A horizontal line has no vertical change (rise = 0), so slope = rise/run = 0/run = 0.", "type": "true_false", "category": "geometry slopes"},
  {"problem_number": "4", "preamble": null, "question_body": "What is the chemical formula for water?", "choices": ["H2O", "CO2", "NaCl", "O2"], "answer": "H2O", "answer_choice_index": 0, "explanation": "Water is composed of two hydrogen atoms and one oxygen atom, hence H2O.", "type": "multiple_choice", "category": "chemistry molecular formulas"},
  {"problem_number": "5", "preamble": null, "question_body": "Explain the difference between mitosis and meiosis.", "answer": "Mitosis produces two identical diploid cells for growth and repair, while meiosis produces four non-identical haploid cells for reproduction.", "answer_choice_index": null, "explanation": "Mitosis maintains chromosome number and genetic identity, whereas meiosis halves the chromosome number and creates genetic diversity through crossing over and independent assortment.", "type": "essay", "category": "biology cell division"},
  {"problem_number": "6", "preamble": null, "question_body": "The process by which plants make their own food is called __________.", "answer": "photosynthesis", "answer_choice_index": null, "explanation": "Photosynthesis uses sunlight, carbon dioxide, and water to produce glucose and oxygen.", "type": "fill_in_the_blank", "category": "biology plant processes"},
  {"problem_number": "7", "preamble": null, "question_body": "When did the Industrial Revolution begin?", "choices": ["Early 17th century", "Late 18th century", "Early 19th century", "Late 19th century"], "answer": "Late 18th century", "answer_choice_index": 1, "explanation": "The passage explicitly states 'The Industrial Revolution began in Britain in the late 18th century.'", "type": "multiple_choice", "category": "history industrial revolution"},
  {"problem_number": "8", "preamble": null, "question_body": "What were two key technologies mentioned in the passage?", "answer": "Steam power and railway system", "answer_choice_index": null, "explanation": "The passage mentions 'steam power' and 'development of the railway system' as key technological developments.", "type": "short_answer", "category": "history technology"},
  {"problem_number": "9", "preamble": null, "question_body": "According to the passage, the Industrial Revolution had both positive and negative impacts. True or False?", "answer": "True", "answer_choice_index": null, "explanation": "The passage mentions economic growth (positive) and social challenges like poor working conditions (negative).", "type": "true_false", "category": "history social impact"},
  {"problem_number": "10", "preamble": null, "question_body": "Describe one social challenge created by the Industrial Revolution mentioned in the passage.", "answer": "Poor working conditions or urbanization problems", "answer_choice_index": null, "explanation": "The passage states the Industrial Revolution 'created social challenges including poor working conditions and urbanization problems.'", "type": "short_answer", "category": "history social challenges"}
]""",
    }

    def _get_response_content(self, messages: list[dict[str, str]]) -> str:
        """Helper to determine which response to use based on messages"""
        # Get the last user message
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        user_message_lower = user_message.lower()

        # Check for context-aware prompts (for testing conversation context)
        if (
            "what is my name" in user_message_lower
            or "my name is" in user_message_lower
        ):
            # Look for a name in previous messages
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "").lower()
                    if "my name is" in content:
                        # Extract name after "my name is"
                        try:
                            name_part = content.split("my name is")[1].strip()
                            name = name_part.split()[0].strip(".,!?").capitalize()
                            if "what is my name" in user_message_lower:
                                return f"Your name is {name}."
                        except (IndexError, AttributeError):
                            pass
            # If asking for name but no name was provided
            if "what is my name" in user_message_lower:
                return "I don't recall you telling me your name."

        # Check for ingest service URL scoring prompt (URLs TO EVALUATE)
        if "urls to evaluate" in user_message_lower or (
            "score=" in user_message_lower and "reason=" in user_message_lower
        ):
            # Count how many URLs are in the prompt (look for numbered lines like "1. URL:")
            import re

            url_count = len(re.findall(r"\d+\.\s+url:", user_message_lower))
            if url_count > 0:
                return self.DEFAULT_RESPONSES["url_scoring"](url_count)
            # Default to 10 URLs if we can't count
            return self.DEFAULT_RESPONSES["url_scoring"](10)

        # Check for ingest service page classification prompt (only page_type, no url_scores)
        # New separate classification call
        if (
            ("concrete" in user_message_lower or "collection" in user_message_lower)
            and "page_type" in user_message_lower
            and "url_scores" not in user_message_lower
            and "score these urls" not in user_message_lower
        ):
            return self.DEFAULT_RESPONSES["page_classification"]

        # Check for ingest service URL scoring prompt (only url_scores or urls, no page_type about classification)
        # New separate scoring call
        if "score these urls" in user_message_lower and (
            "url_scores" in user_message_lower or '"urls"' in user_message_lower
        ):
            import re

            url_count = len(re.findall(r"^\s*\d+\.\s+http", user_message, re.MULTILINE))
            if url_count == 0:
                # Try alternative pattern for URL counting
                url_count = len(re.findall(r"\d+\.\s+.*?http", user_message_lower))

            # Check if keywords match the mock AI content
            # The mock content is about AI, machine learning, etc.
            # Non-matching keywords: quantum computing, blockchain, etc.
            non_matching_keywords = [
                "quantum",
                "blockchain",
                "cryptocurrency",
                "bitcoin",
            ]
            has_non_matching_keyword = any(
                kw in user_message_lower for kw in non_matching_keywords
            )

            # If keywords don't match AI content, return low scores (below 0.5 threshold)
            if has_non_matching_keyword:
                urls_list = (
                    ", ".join(
                        [
                            f'{{"score": 0.2, "title": "Unrelated Article {i+1}", "category": "content"}}'
                            for i in range(url_count)
                        ]
                    )
                    if url_count > 0
                    else ""
                )
                return f'{{"urls": [{urls_list}]}}'

            return self.DEFAULT_RESPONSES["url_scoring_json"](url_count)

        # Check for exam extraction prompt (JSON format with question extraction)
        # Look for system message about extracting exam questions
        system_message = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg.get("content", "").lower()
                break

        # Check if this is a question boundary split request
        is_boundary_split = (
            "identify" in system_message and "boundaries" in system_message
        ) or ("character indices" in system_message and "starts/ends" in system_message)

        if is_boundary_split:
            # Return mock question boundaries
            return """{
  "questions": [
    {"start": 0, "end": 1000, "number": "1"},
    {"start": 1000, "end": 2000, "number": "2"},
    {"start": 2000, "end": 2979, "number": "3"}
  ],
  "incomplete": null
}"""

        # Check if this is a line-by-line tagging request (new format)
        is_line_tagging = (
            "tag each line" in system_message or "tag each line" in user_message_lower
        )

        if is_line_tagging:
            # Extract lines from the prompt
            import json as json_module
            import re

            # Try to extract lines from JSON array format
            lines = []
            try:
                # Find JSON array in the message
                array_match = re.search(r"\[[\s\S]*?\]", user_message)
                if array_match:
                    array_json = array_match.group(0)
                    parsed_array = json_module.loads(array_json)
                    if isinstance(parsed_array, list):
                        for item in parsed_array:
                            if isinstance(item, dict) and "line" in item:
                                # Format: [{"line": "text"}]
                                lines.append(item["line"])
                            elif isinstance(item, str):
                                # Format: ["text1", "text2"]
                                lines.append(item)
            except:
                # Fallback: try regex extraction
                lines = re.findall(r'"line":\s*"([^"]+)"', user_message)

            if not lines:
                # Try alternative format: numbered lines
                lines_match = re.search(
                    r"LINES TO TAG:\n(.+?)(?:\n\n|$)", user_message, re.DOTALL
                )
                if lines_match:
                    lines_text = lines_match.group(1)
                    lines = [
                        line.strip() for line in lines_text.split("\n") if line.strip()
                    ]

            # Generate mock tags for each line
            tags = []
            problem_num = 1
            table_header_nums = []  # Track problem numbers from table headers
            in_explanation_section = False  # Track if we're in an explanation section

            for i, line in enumerate(lines):
                line_lower = line.lower()

                # Determine tag based on content
                # Check for answer section marker first (most specific)
                if re.match(r"^\s*参考答案\s*$", line) or re.match(
                    r"^\s*\w+参考答案\s*$", line
                ):
                    tag = "z"  # Answer section marker
                    in_explanation_section = False  # Reset explanation state
                elif (
                    line_lower.strip() == "answer key"
                    or line_lower.strip() == "answers"
                ):
                    tag = "z"  # Answer section marker (English)
                    in_explanation_section = False  # Reset explanation state
                # Check for table header row with problem numbers
                elif re.match(r"^\s*\|.*\|.*\|\s*$", line):
                    # Table format line
                    cells = [c.strip() for c in line.split("|") if c.strip()]

                    # Check if this is a header row with numbers (e.g., |1|2|3|4|)
                    if all(c.isdigit() for c in cells):
                        table_header_nums = [int(c) for c in cells]
                        tag = "s"  # Skip table header
                    # Check if previous line was a table header with numbers
                    elif table_header_nums and len(cells) == len(table_header_nums):
                        # This is likely an answer row - parse as 'aa' tag
                        answers = []
                        for prob_num, cell in zip(table_header_nums, cells):
                            # Check if cell is a letter (A-H) for multiple choice
                            if re.match(r"^[A-H]$", cell.upper()):
                                choice_idx = ord(cell.upper()) - ord("A")
                                answers.append(
                                    f'{{"tag": "a[{prob_num}]", "answer": {{"choice": {choice_idx}}}}}'
                                )
                            else:
                                # Free response answer
                                answers.append(
                                    f'{{"tag": "a[{prob_num}]", "answer": "{cell}"}}'
                                )

                        tag = f'{{"tag": "aa", "answers": [{", ".join(answers)}]}}'
                        table_header_nums = []  # Reset after using
                    else:
                        # Regular table row, not an answer row
                        tag = "s"
                        table_header_nums = []  # Reset
                elif any(
                    marker in line_lower
                    for marker in [
                        "一、",
                        "二、",
                        "三、",
                        "第i卷",
                        "考试时间",
                        "试题分数",
                        "mathematics midterm",
                        "science section",
                        "reading comprehension",
                    ]
                ):
                    tag = "s"  # Skip generic headers
                elif re.match(r"^\s*\d+\.", line):
                    # Line starts with number
                    if in_explanation_section:
                        # In explanation section - numbered lines are explanations
                        # Extract the problem number from the line (e.g., "1. 2 + 2 = 4" -> problem 1)
                        match = re.match(r"^\s*(\d+)\.", line)
                        if match:
                            expl_problem_num = int(match.group(1))
                            tag = f"e[{expl_problem_num}]"
                        else:
                            tag = "s"  # Skip if we can't extract problem number
                    elif "）" in line or ")" in line:
                        # Check if it's a choice (A) B) C) etc.)
                        if re.match(r"^\s*[A-H][）)]", line):
                            # Extract choice letter and text
                            choice_match = re.match(r"^\s*([A-H])[）)]\s*(.+)", line)
                            if choice_match:
                                choice_letter = choice_match.group(1).upper()
                                choice_match.group(2).strip()
                                choice_idx = ord(choice_letter) - ord("A")
                                # Escape the line text for JSON
                                import json as json_module

                                escaped_line = json_module.dumps(line)
                                tag = f'{{"tag": "c[{problem_num}]", "choices": {{"{choice_idx}": {escaped_line}}}}}'
                            else:
                                tag = f"c[{problem_num}]"
                        else:
                            tag = f"q[{problem_num}]"
                            problem_num += 1
                    else:
                        tag = f"q[{problem_num}]"
                        problem_num += 1
                elif "【答案】" in line or "answer:" in line_lower:
                    tag = f"a[{max(1, problem_num-1)}]"
                elif "【解析】" in line:
                    # Only set explanation section for Chinese marker, not English
                    tag = "s"  # Skip the header itself
                    in_explanation_section = True  # Mark that we're now in explanations
                elif "explanation:" in line_lower:
                    tag = "s"  # Skip explanation headers but don't enter section mode
                elif re.match(r"^\s*[A-H][）)]", line):
                    # Extract choice letter and text
                    choice_match = re.match(r"^\s*([A-H])[）)]\s*(.+)", line)
                    if choice_match:
                        choice_letter = choice_match.group(1).upper()
                        choice_match.group(2).strip()
                        choice_idx = ord(choice_letter) - ord("A")
                        # Escape the line text for JSON
                        import json as json_module

                        escaped_line = json_module.dumps(line)
                        tag = f'{{"tag": "c[{max(1, problem_num-1)}]", "choices": {{"{choice_idx}": {escaped_line}}}}}'
                    else:
                        tag = f"c[{max(1, problem_num-1)}]"
                else:
                    # Default to question continuation or skip
                    if problem_num > 1:
                        tag = f"q[{max(1, problem_num-1)}]"
                    else:
                        tag = "s"

                # Handle JSON object tags differently (already JSON formatted)
                # These include 'aa' tags and choice tags with embedded data
                if isinstance(tag, str) and tag.startswith("{"):
                    tags.append(tag)
                else:
                    tags.append(f'"{tag}"')

            # Return JSON array of tags
            return f'[{", ".join(tags)}]'

        # Check if this is an exam extraction request (old format)
        # Can detect from either system prompt OR user message pattern
        is_exam_extraction = (
            "extract" in system_message and "question" in system_message
        ) or "text to extract from" in user_message_lower

        if is_exam_extraction:
            # This is an exam extraction prompt - return structured problems
            return self.DEFAULT_RESPONSES["exam_extraction"]()

        # Check for ingest service content verification prompt (JSON format)
        # Legacy combined call - Look for both page_type and url_scores
        if (
            ("concrete" in user_message_lower or "collection" in user_message_lower)
            and "page_type" in user_message_lower
            and "url_scores" in user_message_lower
        ):
            # Count how many URLs are in the prompt (look for numbered lines)
            import re

            url_count = len(re.findall(r"^\s*\d+\.\s+http", user_message, re.MULTILINE))
            if url_count == 0:
                # Try alternative pattern for URL counting
                url_count = len(re.findall(r"\d+\.\s+.*?http", user_message_lower))
            return self.DEFAULT_RESPONSES["content_verification"](url_count)

        # Check for problem refinement prompt (from exam_refine_service)
        if "expert at refining exam problems" in system_message:
            # This is a problem refinement request
            # Extract the original problem JSON from the prompt
            import json as json_module
            import re

            # Try to extract the problem data from EXTRACTED PROBLEM section
            problem_match = re.search(
                r"EXTRACTED PROBLEM:\n(.+?)(?:\n\nORIGINAL CONTEXT|$)",
                user_message,
                re.DOTALL,
            )

            if problem_match:
                # Parse the problem to extract fields
                problem_text = problem_match.group(1)

                # Extract problem number
                num_match = re.search(r"Problem Number:\s*(\d+)", problem_text)
                problem_num = int(num_match.group(1)) if num_match else 1

                # Extract question
                question_match = re.search(
                    r"Question:\n(.+?)(?:\n\n|$)", problem_text, re.DOTALL
                )
                question = question_match.group(1).strip() if question_match else ""

                # Extract choices (dict format with integer keys)
                choices = None
                choices_match = re.search(
                    r"Choices:\n(.+?)(?:\n\n|$)", problem_text, re.DOTALL
                )
                if choices_match:
                    choices = {}
                    choice_lines = choices_match.group(1).strip().split("\n")
                    for line in choice_lines:
                        # Match format: "  0: A) 3"
                        choice_match = re.match(r"\s*(\d+):\s*(.+)", line)
                        if choice_match:
                            choices[int(choice_match.group(1))] = choice_match.group(2)

                # Extract answer
                answer_match = re.search(r"Answer:\s*(.+?)(?:\n|$)", problem_text)
                answer = None
                if answer_match:
                    answer_str = answer_match.group(1).strip()
                    # Check if it's a dict format like "{'choice': 1}"
                    if "choice" in answer_str:
                        try:
                            # Try to parse as JSON/dict
                            answer = json_module.loads(answer_str.replace("'", '"'))
                        except:
                            # If it's just a letter like "B", keep as is
                            answer = answer_str
                    else:
                        answer = answer_str

                # Extract explanation
                explanation_match = re.search(
                    r"Explanation:\n(.+?)(?:\n\n|$)", problem_text, re.DOTALL
                )
                explanation = (
                    explanation_match.group(1).strip() if explanation_match else None
                )

                # Return refined problem in correct JSON format
                refined_problem = {
                    "number": problem_num,
                    "question": question,
                    "sub_questions": None,
                    "choices": choices,
                    "answer": answer,
                    "sub_answers": None,
                    "explanation": explanation,
                    "sub_explanations": None,
                }

                return json_module.dumps(refined_problem, ensure_ascii=False)

        # Check for translate/Chinese content
        if (
            "translate" in user_message_lower
            or "chinese" in user_message_lower
            or "中文" in user_message
        ):
            return self.DEFAULT_RESPONSES["translate"]
        elif "name" in user_message_lower or "title" in user_message_lower:
            # Check if it's for Chinese content
            if (
                "chinese" in user_message_lower
                or "中文" in user_message
                or "人工智能" in user_message
            ):
                return self.DEFAULT_RESPONSES["name_chinese"]
            else:
                return self.DEFAULT_RESPONSES["name"]
        elif "description" in user_message_lower or "summarize" in user_message_lower:
            # Check if it's for Chinese content
            if (
                "chinese" in user_message_lower
                or "中文" in user_message
                or "人工智能" in user_message
            ):
                return self.DEFAULT_RESPONSES["description_chinese"]
            else:
                return self.DEFAULT_RESPONSES["description"]
        else:
            # Default to distillation response
            return self.DEFAULT_RESPONSES["distill"]

    def create(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> MockChatCompletion:
        """
        Mock create completion method (synchronous).

        Returns appropriate mock responses based on the prompt content.
        """
        content = self._get_response_content(messages)
        return MockChatCompletion(content=content, model=model)


class MockAsyncChatCompletions(MockChatCompletions):
    """Mock async chat completions endpoint"""

    async def create(  # type: ignore
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> MockChatCompletion:
        """
        Mock create completion method (asynchronous).

        Returns appropriate mock responses based on the prompt content.
        This is an async method that can be awaited.
        """
        # Simulate a small async delay to make it more realistic
        await asyncio.sleep(0.01)

        content = self._get_response_content(messages)
        return MockChatCompletion(content=content, model=model)


class MockChat:
    """Mock chat endpoint"""

    def __init__(self, async_mode: bool = False):
        if async_mode:
            self.completions = MockAsyncChatCompletions()
        else:
            self.completions = MockChatCompletions()


class MockImageData:
    """Mock image data in response"""

    def __init__(self, image_b64: str):
        self.b64_json = image_b64
        self.url = None
        self.revised_prompt = None


class MockEmbeddingData:
    """Mock embedding data in response"""

    def __init__(self, embedding: list[float]):
        self.embedding = embedding
        self.index = 0
        self.object = "embedding"


class MockEmbeddingsResponse:
    """Mock embeddings response"""

    def __init__(self, embedding: list[float], model: str = "text-embedding-3-small"):
        self.data = [MockEmbeddingData(embedding)]
        self.model = model
        self.object = "list"
        self.usage = {"prompt_tokens": 10, "total_tokens": 10}


class MockEmbeddings:
    """Mock embeddings endpoint"""

    def __init__(self, async_mode: bool = False):
        self.async_mode = async_mode

    def _generate_mock_embedding(self, input_text: str) -> list[float]:
        """
        Generate a mock embedding vector.

        Creates a deterministic embedding based on input hash for consistency.
        Returns a 1536-dimensional vector (OpenAI text-embedding-3-small default).
        """
        import hashlib

        # Generate deterministic hash from input
        hash_val = int(hashlib.md5(input_text.encode()).hexdigest(), 16)

        # Generate 1536 deterministic values between -1 and 1
        embedding = []
        for i in range(1536):
            # Use hash and index to generate deterministic float
            seed = (hash_val + i) % (2**31 - 1)
            normalized = (seed / (2**31 - 1)) * 2 - 1  # Scale to [-1, 1]
            embedding.append(normalized)

        return embedding

    def create(self, model: str, input: str, **kwargs):
        """Sync create method"""
        if self.async_mode:
            raise RuntimeError("Use async create for async mode")

        embedding = self._generate_mock_embedding(input)
        return MockEmbeddingsResponse(embedding, model)

    async def create_async(self, model: str, input: str, **kwargs):
        """Async create method"""
        # Simulate async operation
        await asyncio.sleep(0.01)
        embedding = self._generate_mock_embedding(input)
        return MockEmbeddingsResponse(embedding, model)


class MockAsyncEmbeddings(MockEmbeddings):
    """Mock async embeddings endpoint"""

    def __init__(self):
        super().__init__(async_mode=True)

    async def create(self, model: str, input: str, **kwargs):  # type: ignore
        """Async create method"""
        await asyncio.sleep(0.01)
        embedding = self._generate_mock_embedding(input)
        return MockEmbeddingsResponse(embedding, model)


class MockImagesResponse:
    """Mock images generation response"""

    def __init__(self, image_b64: str):
        self.created = 1234567890
        self.data = [MockImageData(image_b64)]


class MockResponseOutput:
    """Mock output in responses API"""

    def __init__(self, content: str, output_type: str = "image_generation_call"):
        self.type = output_type
        if output_type == "image_generation_call":
            self.result = content
        elif output_type == "text":
            self.text = content


class MockResponse:
    """Mock response from responses.create()"""

    def __init__(
        self,
        image_b64: Optional[str] = None,
        text_content: Optional[str] = None,
        response_id: str = "mock-response-id",
    ):
        self.id = response_id
        self.output = []

        if image_b64:
            self.output.append(
                MockResponseOutput(image_b64, output_type="image_generation_call")
            )
        elif text_content:
            self.output.append(MockResponseOutput(text_content, output_type="text"))

        # Additional properties for thread mode compatibility
        self.output_text = text_content or ""


class MockImages:
    """Mock images endpoint"""

    def _generate_mock_image(self) -> str:
        """Generate a tiny mock PNG image as base64"""
        import base64

        # Create a minimal 1x1 red PNG image (69 bytes)
        # PNG header + IHDR chunk + IDAT chunk + IEND chunk
        png_bytes = bytes(
            [
                0x89,
                0x50,
                0x4E,
                0x47,
                0x0D,
                0x0A,
                0x1A,
                0x0A,  # PNG signature
                0x00,
                0x00,
                0x00,
                0x0D,  # IHDR length
                0x49,
                0x48,
                0x44,
                0x52,  # IHDR type
                0x00,
                0x00,
                0x00,
                0x01,  # Width: 1
                0x00,
                0x00,
                0x00,
                0x01,  # Height: 1
                0x08,
                0x02,
                0x00,
                0x00,
                0x00,  # Bit depth, color type, etc.
                0x90,
                0x77,
                0x53,
                0xDE,  # IHDR CRC
                0x00,
                0x00,
                0x00,
                0x0C,  # IDAT length
                0x49,
                0x44,
                0x41,
                0x54,  # IDAT type
                0x08,
                0x99,
                0x63,
                0xF8,  # Compressed data (red pixel)
                0xCF,
                0xC0,
                0x00,
                0x00,
                0x00,
                0x03,
                0x00,
                0x01,
                0x2F,
                0xB3,
                0xEC,
                0xFA,  # IDAT CRC
                0x00,
                0x00,
                0x00,
                0x00,  # IEND length
                0x49,
                0x45,
                0x4E,
                0x44,  # IEND type
                0xAE,
                0x42,
                0x60,
                0x82,  # IEND CRC
            ]
        )
        return base64.b64encode(png_bytes).decode("utf-8")

    def generate(self, **kwargs) -> MockImagesResponse:
        """Mock image generation (synchronous)"""
        image_b64 = self._generate_mock_image()
        return MockImagesResponse(image_b64)


class MockAsyncImages(MockImages):
    """Mock async images endpoint"""

    async def generate(self, **kwargs) -> MockImagesResponse:  # type: ignore
        """Mock image generation (asynchronous)"""
        await asyncio.sleep(0.01)  # Simulate async delay
        image_b64 = self._generate_mock_image()
        return MockImagesResponse(image_b64)


class MockResponses:
    """Mock responses endpoint (newer API) - supports both image generation and threaded chat"""

    def _generate_mock_image(self) -> str:
        """Generate a tiny mock PNG image as base64 (same as MockImages)"""
        import base64

        png_bytes = bytes(
            [
                0x89,
                0x50,
                0x4E,
                0x47,
                0x0D,
                0x0A,
                0x1A,
                0x0A,
                0x00,
                0x00,
                0x00,
                0x0D,
                0x49,
                0x48,
                0x44,
                0x52,
                0x00,
                0x00,
                0x00,
                0x01,
                0x00,
                0x00,
                0x00,
                0x01,
                0x08,
                0x02,
                0x00,
                0x00,
                0x00,
                0x90,
                0x77,
                0x53,
                0xDE,
                0x00,
                0x00,
                0x00,
                0x0C,
                0x49,
                0x44,
                0x41,
                0x54,
                0x08,
                0x99,
                0x63,
                0xF8,
                0xCF,
                0xC0,
                0x00,
                0x00,
                0x00,
                0x03,
                0x00,
                0x01,
                0x2F,
                0xB3,
                0xEC,
                0xFA,
                0x00,
                0x00,
                0x00,
                0x00,
                0x49,
                0x45,
                0x4E,
                0x44,
                0xAE,
                0x42,
                0x60,
                0x82,
            ]
        )
        return base64.b64encode(png_bytes).decode("utf-8")

    def _get_response_content(self, messages: list[dict[str, str]]) -> str:
        """Helper to determine which response to use based on messages (same logic as MockChatCompletions)"""
        # Use the same response logic as MockChatCompletions
        completions = MockChatCompletions()
        return completions._get_response_content(messages)

    def create(self, **kwargs) -> MockResponse:
        """Mock responses.create() - supports both image generation and threaded chat (synchronous)"""
        # Check if this is a threaded chat request (has 'input' or 'model' parameter) or image generation
        if "input" in kwargs or "model" in kwargs:
            # Threaded chat mode
            input_data = kwargs.get("input", "")

            # Handle different input formats
            if isinstance(input_data, str):
                # Initial thread creation with text input
                messages = [{"role": "user", "content": input_data}]
            elif isinstance(input_data, list):
                # Subsequent messages in thread
                messages = input_data if input_data else []
            else:
                messages = []

            # Add system instructions if provided
            instructions = kwargs.get("instructions")
            if instructions:
                messages.insert(0, {"role": "system", "content": instructions})

            # Get appropriate response content
            text_content = (
                self._get_response_content(messages) if messages else "Mock response"
            )

            # Return mock response with text content
            return MockResponse(text_content=text_content)
        else:
            # Image generation mode (legacy behavior)
            image_b64 = self._generate_mock_image()
            return MockResponse(image_b64=image_b64)


class MockAsyncResponses(MockResponses):
    """Mock async responses endpoint"""

    async def create(self, **kwargs) -> MockResponse:  # type: ignore
        """Mock responses.create() - supports both image generation and threaded chat (asynchronous)"""
        await asyncio.sleep(0.01)  # Simulate async delay

        # Check if this is a threaded chat request (has 'input' or 'model' parameter) or image generation
        if "input" in kwargs or "model" in kwargs:
            # Threaded chat mode
            input_data = kwargs.get("input", "")

            # Handle different input formats
            if isinstance(input_data, str):
                # Initial thread creation with text input
                messages = [{"role": "user", "content": input_data}]
            elif isinstance(input_data, list):
                # Subsequent messages in thread
                messages = input_data if input_data else []
            else:
                messages = []

            # Add system instructions if provided
            instructions = kwargs.get("instructions")
            if instructions:
                messages.insert(0, {"role": "system", "content": instructions})

            # Get appropriate response content
            text_content = (
                self._get_response_content(messages) if messages else "Mock response"
            )

            # Return mock response with text content
            return MockResponse(text_content=text_content)
        else:
            # Image generation mode (legacy behavior)
            image_b64 = self._generate_mock_image()
            return MockResponse(image_b64=image_b64)


class MockOpenAI:
    """
    Mock OpenAI client that mimics the OpenAI Python SDK interface.

    This class provides the same interface as the real OpenAI client but returns
    pre-defined mock responses instead of making API calls.

    Can be used as both sync and async client.
    """

    def __init__(self, api_key: str = "mock-key", async_mode: bool = False, **kwargs):
        """Initialize mock client (API key is ignored)"""
        self.api_key = api_key
        self.chat = MockChat(async_mode=async_mode)

        # Add endpoints
        if async_mode:
            self.images = MockAsyncImages()
            self.responses = MockAsyncResponses()
            self.embeddings = MockAsyncEmbeddings()
        else:
            self.images = MockImages()
            self.responses = MockResponses()
            self.embeddings = MockEmbeddings()


def get_openai_client(api_key: Optional[str] = None):
    """
    Get OpenAI client (real or mock based on USE_MOCK_MODEL env var).

    Args:
        api_key: OpenAI API key (required for real client)

    Returns:
        OpenAI client (real or mock)

    Example:
        # With mocking enabled
        os.environ["USE_MOCK_MODEL"] = "true"
        client = get_openai_client()  # Returns MockOpenAI

        # With mocking disabled
        os.environ["USE_MOCK_MODEL"] = "false"
        client = get_openai_client(api_key="sk-...")  # Returns real OpenAI client
    """
    from env_vars import USE_MOCK_MODEL

    if USE_MOCK_MODEL:
        return MockOpenAI(api_key=api_key or "mock-key")
    else:
        from openai import OpenAI

        return OpenAI(api_key=api_key)


# ============================================================================
# Mock Anthropic/Claude Client
# ============================================================================


class MockClaudeTextBlock:
    """Mock text block in Claude response"""

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class MockClaudeToolUseBlock:
    """Mock tool use block in Claude response"""

    def __init__(self, tool_id: str, tool_name: str, tool_input: dict):
        self.type = "tool_use"
        self.id = tool_id
        self.name = tool_name
        self.input = tool_input


class MockClaudeMessage:
    """Mock Claude message response"""

    def __init__(
        self,
        content_text: str,
        model: str = "claude-3-5-sonnet-20241022",
        tool_calls: Optional[list] = None,
    ):
        self.id = "mock-msg-id"
        self.type = "message"
        self.role = "assistant"
        self.model = model
        self.stop_reason = "end_turn"
        self.stop_sequence = None
        self.usage = MockClaudeUsage()

        # Build content blocks
        self.content = []
        if content_text:
            self.content.append(MockClaudeTextBlock(content_text))
        if tool_calls:
            self.content.extend(tool_calls)


class MockClaudeUsage:
    """Mock token usage"""

    def __init__(self):
        self.input_tokens = 50
        self.output_tokens = 100


class MockClaudeMessages:
    """Mock Claude messages endpoint"""

    # Default responses (same as OpenAI for consistency)
    DEFAULT_RESPONSES = MockChatCompletions.DEFAULT_RESPONSES

    def _get_response_content(self, messages: list[dict]) -> str:
        """Helper to determine which response to use based on messages"""
        # Get the last user message
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                # Handle both string and list content
                if isinstance(content, str):
                    user_message = content
                elif isinstance(content, list):
                    # Extract text from content blocks
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            user_message += block.get("text", "")
                break

        user_message_lower = user_message.lower()

        # Check for system message (for exam extraction detection)
        system_message = ""
        for msg in messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if isinstance(content, str):
                    system_message = content.lower()
                break

        # Check if this is a question boundary split request
        is_boundary_split = (
            "identify" in system_message and "boundaries" in system_message
        ) or ("character indices" in system_message and "starts/ends" in system_message)

        if is_boundary_split:
            # Return mock question boundaries
            return """{
  "questions": [
    {"start": 0, "end": 1000, "number": "1"},
    {"start": 1000, "end": 2000, "number": "2"},
    {"start": 2000, "end": 2979, "number": "3"}
  ],
  "incomplete": null
}"""

        # Check if this is a line-by-line tagging request (new format)
        is_line_tagging = (
            "tag each line" in system_message or "tag each line" in user_message_lower
        )

        if is_line_tagging:
            # Extract lines from the prompt
            import json as json_module
            import re

            # Try to extract lines from JSON array format
            lines = []
            try:
                # Find JSON array in the message
                array_match = re.search(r"\[[\s\S]*?\]", user_message)
                if array_match:
                    array_json = array_match.group(0)
                    parsed_array = json_module.loads(array_json)
                    if isinstance(parsed_array, list):
                        for item in parsed_array:
                            if isinstance(item, dict) and "line" in item:
                                # Format: [{"line": "text"}]
                                lines.append(item["line"])
                            elif isinstance(item, str):
                                # Format: ["text1", "text2"]
                                lines.append(item)
            except:
                # Fallback: try regex extraction
                lines = re.findall(r'"line":\s*"([^"]+)"', user_message)

            if not lines:
                # Try alternative format: numbered lines
                lines_match = re.search(
                    r"LINES TO TAG:\n(.+?)(?:\n\n|$)", user_message, re.DOTALL
                )
                if lines_match:
                    lines_text = lines_match.group(1)
                    lines = [
                        line.strip() for line in lines_text.split("\n") if line.strip()
                    ]

            # Generate mock tags for each line
            tags = []
            problem_num = 1
            table_header_nums = []  # Track problem numbers from table headers
            in_explanation_section = False  # Track if we're in an explanation section

            for i, line in enumerate(lines):
                line_lower = line.lower()

                # Determine tag based on content
                # Check for answer section marker first (most specific)
                if re.match(r"^\s*参考答案\s*$", line) or re.match(
                    r"^\s*\w+参考答案\s*$", line
                ):
                    tag = "z"  # Answer section marker
                    in_explanation_section = False  # Reset explanation state
                elif (
                    line_lower.strip() == "answer key"
                    or line_lower.strip() == "answers"
                ):
                    tag = "z"  # Answer section marker (English)
                    in_explanation_section = False  # Reset explanation state
                # Check for table header row with problem numbers
                elif re.match(r"^\s*\|.*\|.*\|\s*$", line):
                    # Table format line
                    cells = [c.strip() for c in line.split("|") if c.strip()]

                    # Check if this is a header row with numbers (e.g., |1|2|3|4|)
                    if all(c.isdigit() for c in cells):
                        table_header_nums = [int(c) for c in cells]
                        tag = "s"  # Skip table header
                    # Check if previous line was a table header with numbers
                    elif table_header_nums and len(cells) == len(table_header_nums):
                        # This is likely an answer row - parse as 'aa' tag
                        answers = []
                        for prob_num, cell in zip(table_header_nums, cells):
                            # Check if cell is a letter (A-H) for multiple choice
                            if re.match(r"^[A-H]$", cell.upper()):
                                choice_idx = ord(cell.upper()) - ord("A")
                                answers.append(
                                    f'{{"tag": "a[{prob_num}]", "answer": {{"choice": {choice_idx}}}}}'
                                )
                            else:
                                # Free response answer
                                answers.append(
                                    f'{{"tag": "a[{prob_num}]", "answer": "{cell}"}}'
                                )

                        tag = f'{{"tag": "aa", "answers": [{", ".join(answers)}]}}'
                        table_header_nums = []  # Reset after using
                    else:
                        # Regular table row, not an answer row
                        tag = "s"
                        table_header_nums = []  # Reset
                elif any(
                    marker in line_lower
                    for marker in [
                        "一、",
                        "二、",
                        "三、",
                        "第i卷",
                        "考试时间",
                        "试题分数",
                        "mathematics midterm",
                        "science section",
                        "reading comprehension",
                    ]
                ):
                    tag = "s"  # Skip generic headers
                elif re.match(r"^\s*\d+\.", line):
                    # Line starts with number
                    if in_explanation_section:
                        # In explanation section - numbered lines are explanations
                        # Extract the problem number from the line (e.g., "1. 2 + 2 = 4" -> problem 1)
                        match = re.match(r"^\s*(\d+)\.", line)
                        if match:
                            expl_problem_num = int(match.group(1))
                            tag = f"e[{expl_problem_num}]"
                        else:
                            tag = "s"  # Skip if we can't extract problem number
                    elif "）" in line or ")" in line:
                        # Check if it's a choice (A) B) C) etc.)
                        if re.match(r"^\s*[A-H][）)]", line):
                            # Extract choice letter and text
                            choice_match = re.match(r"^\s*([A-H])[）)]\s*(.+)", line)
                            if choice_match:
                                choice_letter = choice_match.group(1).upper()
                                choice_match.group(2).strip()
                                choice_idx = ord(choice_letter) - ord("A")
                                # Escape the line text for JSON
                                import json as json_module

                                escaped_line = json_module.dumps(line)
                                tag = f'{{"tag": "c[{problem_num}]", "choices": {{"{choice_idx}": {escaped_line}}}}}'
                            else:
                                tag = f"c[{problem_num}]"
                        else:
                            tag = f"q[{problem_num}]"
                            problem_num += 1
                    else:
                        tag = f"q[{problem_num}]"
                        problem_num += 1
                elif "【答案】" in line or "answer:" in line_lower:
                    tag = f"a[{max(1, problem_num-1)}]"
                elif "【解析】" in line:
                    # Only set explanation section for Chinese marker, not English
                    tag = "s"  # Skip the header itself
                    in_explanation_section = True  # Mark that we're now in explanations
                elif "explanation:" in line_lower:
                    tag = "s"  # Skip explanation headers but don't enter section mode
                elif re.match(r"^\s*[A-H][）)]", line):
                    # Extract choice letter and text
                    choice_match = re.match(r"^\s*([A-H])[）)]\s*(.+)", line)
                    if choice_match:
                        choice_letter = choice_match.group(1).upper()
                        choice_match.group(2).strip()
                        choice_idx = ord(choice_letter) - ord("A")
                        # Escape the line text for JSON
                        import json as json_module

                        escaped_line = json_module.dumps(line)
                        tag = f'{{"tag": "c[{max(1, problem_num-1)}]", "choices": {{"{choice_idx}": {escaped_line}}}}}'
                    else:
                        tag = f"c[{max(1, problem_num-1)}]"
                else:
                    # Default to question continuation or skip
                    if problem_num > 1:
                        tag = f"q[{max(1, problem_num-1)}]"
                    else:
                        tag = "s"

                # Handle JSON object tags differently (already JSON formatted)
                # These include 'aa' tags and choice tags with embedded data
                if isinstance(tag, str) and tag.startswith("{"):
                    tags.append(tag)
                else:
                    tags.append(f'"{tag}"')

            # Return JSON array of tags
            return f'[{", ".join(tags)}]'

        # Check if this is an exam extraction request (same logic as OpenAI mock)
        # Can detect from either system prompt OR user message pattern
        is_exam_extraction = (
            "extract" in system_message and "question" in system_message
        ) or "text to extract from" in user_message_lower

        if is_exam_extraction:
            # This is an exam extraction prompt - return structured problems
            return self.DEFAULT_RESPONSES["exam_extraction"]()

        # Check for problem refinement prompt (from exam_refine_service)
        if "expert at refining exam problems" in system_message:
            # This is a problem refinement request
            # Extract the original problem JSON from the prompt
            import json as json_module
            import re

            # Try to extract the problem data from EXTRACTED PROBLEM section
            problem_match = re.search(
                r"EXTRACTED PROBLEM:\n(.+?)(?:\n\nORIGINAL CONTEXT|$)",
                user_message,
                re.DOTALL,
            )

            if problem_match:
                # Parse the problem to extract fields
                problem_text = problem_match.group(1)

                # Extract problem number
                num_match = re.search(r"Problem Number:\s*(\d+)", problem_text)
                problem_num = int(num_match.group(1)) if num_match else 1

                # Extract question
                question_match = re.search(
                    r"Question:\n(.+?)(?:\n\n|$)", problem_text, re.DOTALL
                )
                question = question_match.group(1).strip() if question_match else ""

                # Extract choices (dict format with integer keys)
                choices = None
                choices_match = re.search(
                    r"Choices:\n(.+?)(?:\n\n|$)", problem_text, re.DOTALL
                )
                if choices_match:
                    choices = {}
                    choice_lines = choices_match.group(1).strip().split("\n")
                    for line in choice_lines:
                        # Match format: "  0: A) 3"
                        choice_match = re.match(r"\s*(\d+):\s*(.+)", line)
                        if choice_match:
                            choices[int(choice_match.group(1))] = choice_match.group(2)

                # Extract answer
                answer_match = re.search(r"Answer:\s*(.+?)(?:\n|$)", problem_text)
                answer = None
                if answer_match:
                    answer_str = answer_match.group(1).strip()
                    # Check if it's a dict format like "{'choice': 1}"
                    if "choice" in answer_str:
                        try:
                            # Try to parse as JSON/dict
                            answer = json_module.loads(answer_str.replace("'", '"'))
                        except:
                            # If it's just a letter like "B", keep as is
                            answer = answer_str
                    else:
                        answer = answer_str

                # Extract explanation
                explanation_match = re.search(
                    r"Explanation:\n(.+?)(?:\n\n|$)", problem_text, re.DOTALL
                )
                explanation = (
                    explanation_match.group(1).strip() if explanation_match else None
                )

                # Return refined problem in correct JSON format
                refined_problem = {
                    "number": problem_num,
                    "question": question,
                    "sub_questions": None,
                    "choices": choices,
                    "answer": answer,
                    "sub_answers": None,
                    "explanation": explanation,
                    "sub_explanations": None,
                }

                return json_module.dumps(refined_problem, ensure_ascii=False)

        # Use same logic as OpenAI mock for consistency
        # Check for translate/Chinese content
        if (
            "translate" in user_message_lower
            or "chinese" in user_message_lower
            or "中文" in user_message
        ):
            return self.DEFAULT_RESPONSES["translate"]
        elif "name" in user_message_lower or "title" in user_message_lower:
            if (
                "chinese" in user_message_lower
                or "中文" in user_message
                or "人工智能" in user_message
            ):
                return self.DEFAULT_RESPONSES["name_chinese"]
            else:
                return self.DEFAULT_RESPONSES["name"]
        elif "description" in user_message_lower or "summarize" in user_message_lower:
            if (
                "chinese" in user_message_lower
                or "中文" in user_message
                or "人工智能" in user_message
            ):
                return self.DEFAULT_RESPONSES["description_chinese"]
            else:
                return self.DEFAULT_RESPONSES["description"]
        else:
            # Default to distillation response
            return self.DEFAULT_RESPONSES["distill"]

    def create(
        self,
        model: str,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        tools: Optional[list] = None,
        **kwargs,
    ) -> MockClaudeMessage:
        """
        Mock create message method (synchronous).

        Returns appropriate mock responses based on the prompt content.
        """
        content = self._get_response_content(messages)
        return MockClaudeMessage(content_text=content, model=model)


class MockAsyncClaudeMessages(MockClaudeMessages):
    """Mock async Claude messages endpoint"""

    async def create(  # type: ignore
        self,
        model: str,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        tools: Optional[list] = None,
        **kwargs,
    ) -> MockClaudeMessage:
        """
        Mock create message method (asynchronous).

        Returns appropriate mock responses based on the prompt content.
        This is an async method that can be awaited.
        """
        # Simulate a small async delay to make it more realistic
        await asyncio.sleep(0.01)

        content = self._get_response_content(messages)
        return MockClaudeMessage(content_text=content, model=model)


class MockAnthropic:
    """
    Mock Anthropic client that mimics the Anthropic Python SDK interface.

    This class provides the same interface as the real Anthropic client but returns
    pre-defined mock responses instead of making API calls.

    Can be used as both sync and async client.
    """

    def __init__(self, api_key: str = "mock-key", async_mode: bool = False, **kwargs):
        """Initialize mock client (API key is ignored)"""
        self.api_key = api_key
        if async_mode:
            self.messages = MockAsyncClaudeMessages()
        else:
            self.messages = MockClaudeMessages()

    async def close(self):
        """Mock close method for async client cleanup"""


def get_anthropic_client(api_key: Optional[str] = None):
    """
    Get Anthropic client (real or mock based on USE_MOCK_MODEL env var).

    Args:
        api_key: Anthropic API key (required for real client)

    Returns:
        Anthropic client (real or mock)

    Example:
        # With mocking enabled
        os.environ["USE_MOCK_MODEL"] = "true"
        client = get_anthropic_client()  # Returns MockAnthropic

        # With mocking disabled
        os.environ["USE_MOCK_MODEL"] = "false"
        client = get_anthropic_client(api_key="sk-ant-...")  # Returns real Anthropic client
    """
    from env_vars import USE_MOCK_MODEL

    if USE_MOCK_MODEL:
        return MockAnthropic(api_key=api_key or "mock-key")
    else:
        from anthropic import Anthropic

        return Anthropic(api_key=api_key)
