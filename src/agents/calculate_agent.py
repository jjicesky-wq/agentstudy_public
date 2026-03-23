from agents.base_agent import AIAgentBase, AIAgentToolResult
from models.openai_model import OpenAIModel
from tools.base_tool import AIToolBase
from tools.add_tool import AddTool

from string import Template

# agent实现具体事情的Language Model
class AICalculateAgent(AIAgentBase):
    model: OpenAIModel = OpenAIModel(model_class="gpt-4")

    instruction: Template = Template(
        """
        You are a calculator. Use the provided tool to perform the math operation.
        You should perform a complicated math operation by:
        - First break that down to single computation based on math rules
        - Then use the tool to compute the single computation
        - Then repeat the steps above until you get the final result
        - Output the detailed computation steps
        - If you encounter any operation that is not defined in the tools, return no able to compute and point out where you have trouble
        """
    )

    tools: list[AIToolBase] = [
        AddTool()
    ]

    def _save_tool_run_result(self, result: AIAgentToolResult):
        return

    def hand_off_to_next_agent(self, agent: AIAgentBase):
        return

if __name__ == "__main__":
    agent = AICalculateAgent()
    prompt = "Wait for user input"
    current = None
    while True:
        current = agent.run_agent_conversation(user_prompt=prompt, current_conversation=current)
        print(current.last_model_response)
        prompt = input("> ")