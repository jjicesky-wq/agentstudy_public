import asyncio
import json
import os

import data
from models.openai_model import OpenAIModel


async def interactive_mode():
    current_conversation = None
    model = OpenAIModel(model_class="gpt-5-mini")
    print("Start OpenAI model in interactive mode (threaded conversation)!")

    data_path = data.__path__[0]
    filepath = os.path.join(data_path, "meta.txt")
    print(filepath)
    with open(filepath, encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    current_title = None
    current_content = []
    sections = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Detect dashed separator
        if line.strip().startswith("-----"):
            # Title is the line BEFORE -----
            current_title = lines[i - 1].strip()
            current_content = []

            i += 1

            # Skip blank line(s) after -----
            while i < n and lines[i].strip() == "":
                i += 1

            # Collect content until we see:
            #   a line followed by -----
            while i < n and not (
                i + 1 < n and lines[i + 1].strip().startswith("-----")
            ):
                current_content.append(lines[i])
                i += 1

            sections.append((current_title, "\n".join(current_content).strip()))
        else:
            i += 1

    # Example usage
    i = 0
    to_process = ""
    for j in range(0, len(sections)):
        title, content = sections[j]
        current_conversation = model.create_conversation(
            system_prompt="""
我会给你传网站上提前的文字，我需要你提取里面的leetcode题目数字，注意这个题目有可能是中文谐音，同时你要注意不要把其他数字错认成题目，比如数字后面有时间单位。你必须返回一个JSON格式list，里面包括:
{
    \"leet_code\": [list of leet code numbers],
    \"leet_code_raw\": [list of leet code numbers in the original text form]
    \"notes\": other notes that the post contains,
    \"title\": post title,
    \"url\": post url
}

For each post, you should have one dictionary above in the list

Wait for user input and return JSON string only, without any markdown prefixes or quotes.
""",
            thread_mode=False,
        )
        if i == 0:
            to_process = ""

        to_process += f"Title: {title}\n{content}\n--------------------\n"
        i += 1
        if i == 1 or j == len(sections) - 1:
            retry = 3
            previous_problem = None
            while retry > 0:
                try:
                    prompt = f"process this: {to_process}"
                    if previous_problem:
                        prompt = f"previous attempt problem: {previous_problem}, retry process {to_process}"
                        previous_problem = None
                    response = await current_conversation.run_chat_completion_async(
                        user_prompt=prompt
                    )
                    response_dict = json.loads(response)
                    print(json.dumps(response_dict, indent=2))
                    break
                except Exception as e:
                    previous_problem = str(e)
                    retry -= 1
                    continue

            i = 0
            break


#     print(result)


#     while True:
#         user_prompt: str = ""
#         if current_conversation:
#             print("")
#             user_prompt = input("> ")
#             if user_prompt.lower() == "exit":
#                 exit()
#         if not current_conversation or user_prompt.lower() == "new":
#             current_conversation = model.create_conversation(
#                 system_prompt="You are a helpful agent that answers any user questions",
#                 thread_mode=True,  # Enable threaded conversation mode
#             )
#             print(
#                 """
# *******************************************************************************
# *                    New threaded conversation started!                       *
# * Commands:                                                                   *
# *   exit  - quit the interactive mode                                         *
# *   new   - start a new conversation                                          *
# *******************************************************************************
# """
#             )
#             continue
#         # Use async threaded conversation
#         response = await current_conversation.run_chat_completion_async(
#             user_prompt=user_prompt
#         )
#         print(f"Agent: {response}")

asyncio.run(interactive_mode())
